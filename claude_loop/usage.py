"""
usage.py - the "what does the CLI say" layer for Claude usage limits.

This module owns everything about *reading* `claude -p "/usage"`: running the
CLI round-trip, caching its raw text, and parsing the three quota figures the
report carries. It knows nothing about *policy* (which quota to gate on, what
ceiling to allow, when to pause) — that lives in limits.py, which consumes the
`Usage` snapshots this module produces.

`claude -p "/usage"` prints (roughly):

    Current session: 8% used · resets Jun 27, 5:50pm (Europe/Kiev)
    Current week (all models): 73% used · resets Jul 1, 4pm (Europe/Kiev)
    Current week (Sonnet only): 0% used

Each line becomes a `UsageReading` (percent + reset epoch); the three together,
plus the verbatim summary lines, make a `Usage` snapshot. Note the weekly reset
time may omit the minutes ("4pm", not "4:00pm"), so the reset parser treats them
as optional.
"""

import re
import subprocess
import time
from datetime import datetime
from typing import NamedTuple, Optional

from . import cyclecore

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 or missing tz database
    ZoneInfo = None


# `claude -p "/usage"` is itself a CLI round-trip, so we don't want to fire it on
# every loop turn. When caching is enabled the last reading is reused for up to
# USAGE_CACHE_TTL seconds, so the CLI is queried at most once per window.
USAGE_CACHE_TTL = 120  # seconds — at most one /usage query per 2 minutes


class UsageReading(NamedTuple):
    """One quota line from /usage: its "NN% used" figure and reset time.

    `percent` is None when the line was absent or unparsable. `reset_ts` is the
    epoch time the quota's window resets (None if not present / unparsable).
    """
    percent: Optional[float]
    reset_ts: Optional[float]


class Usage(NamedTuple):
    """A full parsed /usage snapshot: the three quota readings plus the verbatim
    summary lines (kept for logging exactly what the CLI reported).

      * session     — the ~5-hour "Current session" window.
      * week_all    — "Current week (all models)".
      * week_sonnet — "Current week (Sonnet only)".
    """
    session: UsageReading
    week_all: UsageReading
    week_sonnet: UsageReading
    summary_lines: list


_EMPTY_READING = UsageReading(None, None)
_EMPTY_USAGE = Usage(_EMPTY_READING, _EMPTY_READING, _EMPTY_READING, [])

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# "44% used"
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
# "resets Jun 24, 3:30am (Europe/Kiev)" — minutes and the zone are both optional
# ("resets Jul 1, 4pm").
_RESET_RE = re.compile(
    r"resets\s+([A-Za-z]{3,})\s+(\d{1,2}),\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*(?:\(([^)]+)\))?",
    re.IGNORECASE,
)


def _reset_to_ts(mon_s: str, day_s: str, hour_s: str, min_s: Optional[str],
                 ampm: str, zone: Optional[str]) -> Optional[float]:
    """Turn a parsed "resets <Mon> <day>, <h>[:<m>]<am/pm> (<zone>)" into an epoch.

    Resolves the 12-hour clock, applies the named timezone when available, and
    guards the year boundary: a reset is always in the near future, so a time
    that parsed into the distant past belongs to next year.
    """
    month = _MONTHS.get(mon_s[:3].lower())
    if not month:
        return None
    hour = int(hour_s) % 12
    if ampm.lower() == "pm":
        hour += 12
    minute = int(min_s) if min_s else 0
    tz = None
    if zone and ZoneInfo is not None:
        try:
            tz = ZoneInfo(zone.strip())
        except Exception:
            tz = None
    now = datetime.now(tz)
    try:
        dt = datetime(now.year, month, int(day_s), hour, minute, tzinfo=tz)
    except ValueError:
        return None
    ts = dt.timestamp()
    if ts < now.timestamp() - 24 * 3600:
        ts = dt.replace(year=now.year + 1).timestamp()
    return ts


def _reading_from_line(line: str) -> UsageReading:
    """Parse a single normalised /usage line into a UsageReading."""
    percent = None
    m = _PERCENT_RE.search(line)
    if m:
        percent = float(m.group(1))
    reset_ts = None
    r = _RESET_RE.search(line)
    if r:
        reset_ts = _reset_to_ts(*r.groups())
    return UsageReading(percent, reset_ts)


def parse_usage(text: str) -> Usage:
    """Parse raw /usage output into a Usage snapshot.

    Recognises the "Current session", "Current week (all models)" and "Current
    week (Sonnet only)" lines; any that are missing come back as an all-None
    UsageReading. `summary_lines` holds the matched lines verbatim (whitespace
    normalised), in the order they appeared, for logging.
    """
    session = week_all = week_sonnet = _EMPTY_READING
    summary = []
    for raw in text.splitlines():
        s = " ".join(raw.split())
        low = s.lower()
        if low.startswith("current session"):
            session = _reading_from_line(s)
            summary.append(s)
        elif low.startswith("current week (all models)"):
            week_all = _reading_from_line(s)
            summary.append(s)
        elif low.startswith("current week (sonnet only)"):
            week_sonnet = _reading_from_line(s)
            summary.append(s)
    return Usage(session, week_all, week_sonnet, summary)


class UsageSource:
    """Queries and caches `claude -p "/usage"`; hands out parsed Usage snapshots.

    The read-only counterpart to a LimitPolicy: the policy asks this for the
    current figures and decides what to do. A single CLI round-trip is cached for
    `cache_ttl` seconds and reused by every reader (the limit check and the
    bookend snapshots share it), so /usage is hit at most once per window.
    """

    def __init__(self, cache_ttl: float = USAGE_CACHE_TTL):
        self.cache_ttl = cache_ttl
        self._cached: Optional[Usage] = None
        self._cached_ts: float = 0.0

    def query_usage_text(self) -> str:
        """Run `claude -p "/usage"` and return its raw stdout (empty on failure)."""
        try:
            proc = subprocess.run(
                ["claude", "-p", "/usage"],
                cwd=cyclecore.project_dir(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
        except FileNotFoundError:
            print("  · could not query /usage: 'claude' not found on PATH.")
            return ""
        except subprocess.TimeoutExpired:
            print("  · could not query /usage: the command timed out.")
            return ""
        return proc.stdout or ""

    def get_usage(self, cache_value: bool = True) -> Usage:
        """Return the current Usage snapshot, reusing a cached reading when fresh.

        With `cache_value` True (default) a snapshot younger than `cache_ttl` is
        returned without invoking the CLI again; otherwise (or once stale) the CLI
        is queried and the result cached. Pass `cache_value=False` to force a
        fresh reading. A failed query (empty text) is not cached, so the next call
        retries instead of being stuck on an all-None snapshot.
        """
        now = time.time()
        if (cache_value and self._cached is not None
                and now - self._cached_ts < self.cache_ttl):
            return self._cached
        text = self.query_usage_text()
        if not text:
            return _EMPTY_USAGE
        usage = parse_usage(text)
        self._cached = usage
        self._cached_ts = now
        return usage

    def invalidate(self) -> None:
        """Drop the cached snapshot (e.g. after waiting out a window, when the old
        percentages are no longer meaningful)."""
        self._cached = None
        self._cached_ts = 0.0
