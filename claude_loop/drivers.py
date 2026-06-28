"""
drivers.py - reusable Driver implementations for the autonomous Claude-CLI loop.

These are the two task shapes the loop was originally built around, generalised
so a host project supplies its own paths, prompts and models instead of them
being hard-coded module constants:

  * StateFileDriver - a state machine: read the first line of a state file each
    iteration and run a fixed prompt against it, stopping on an `error` state.
  * ListFileDriver  - a work queue: hand out the files listed in a list file one
    at a time (at random, to spread evenly across a grouped list), striking each
    out once its command succeeds; stop when the list is empty.

Both resolve their relative paths against cyclecore.project_dir() (the project
root, set from --project-dir / cwd), so the same code drives any host project.
"""

import os
import random
from typing import Callable, Optional

from . import cyclecore
from .cyclecore import ClaudeCommand, Driver, LoopStop


def _abs_in_project(path: str) -> str:
    """Resolve a path against the project root; absolute paths pass through."""
    return path if os.path.isabs(path) else os.path.join(
        cyclecore.project_dir(), path)


# --- state-machine driver ------------------------------------------------------

class StateFileDriver(Driver):
    """Read the first line of a state file each iteration and run a fixed prompt.

    The loop never ends on its own (the state machine is meant to run forever);
    it stops only on an `error` state — which aborts the run with exit code 1 —
    or via the usual stop file / Ctrl+C / --max.

    Parameters:
      state_file   relative (to the project root) or absolute path to the state
                   file whose first line is the current state.
      prompt       the instruction sent to claude every iteration. Defaults to
                   "Follow the instructions in <state_file>".
      model        the model to use, unless model_fn is given.
      model_fn     optional callable(state_first_line) -> model name, to vary the
                   model by state (e.g. a heavier model for an "implementation"
                   state). Takes precedence over `model`.
      error_token  substring (case-insensitive) in the state line that aborts the
                   run for human intervention. Default: "error".
    """

    def __init__(self, state_file: str, prompt: Optional[str] = None,
                 model: str = "opus",
                 model_fn: Optional[Callable[[str], str]] = None,
                 error_token: str = "error"):
        self._state_file_rel = state_file
        self._prompt = prompt or f"Follow the instructions in {state_file}"
        self._model = model
        self._model_fn = model_fn
        self._error_token = error_token.lower()

    def _state_path(self) -> str:
        return _abs_in_project(self._state_file_rel)

    def first_line(self) -> str:
        """First line of the state file (empty string if the file is missing)."""
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                return f.readline().strip()
        except FileNotFoundError:
            return ""

    def model(self) -> str:
        if self._model_fn is not None:
            return self._model_fn(self.first_line())
        return self._model

    def next_command(self) -> Optional[ClaudeCommand]:
        state = self.first_line()
        # State-machine contract: on error we do not proceed.
        if self._error_token in state.lower():
            raise LoopStop(
                f"State '{state}' — error detected. Stopping, "
                f"human intervention required.",
                exit_code=1,
            )
        label = state or f"{self._state_file_rel} not found"
        return ClaudeCommand(self._prompt, self.model(), label)

    def final_summary(self) -> Optional[str]:
        return f"Final state: {self.first_line()}"


# --- list / work-queue driver --------------------------------------------------

def _read_list_lines(list_path: str) -> list:
    """All raw lines of the list file (without trailing newlines).

    Returns [] if the file is missing, so an absent/emptied list just ends the
    loop cleanly. utf-8-sig strips a leading BOM so it never corrupts the first
    path into a relative-looking name.
    """
    try:
        with open(list_path, "r", encoding="utf-8-sig") as f:
            return [ln.rstrip("\n") for ln in f]
    except FileNotFoundError:
        return []


def _write_list_lines(list_path: str, lines: list) -> None:
    """Rewrite the list file: newline-joined, trailing newline iff non-empty."""
    with open(list_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")


class ListFileDriver(Driver):
    """Hand out files from a list file one at a time, striking each out of the
    list once its command succeeds.

    Progress lives in the list file itself (done paths are removed), so the run
    is idempotent: stop any time and relaunch — it picks up whatever paths are
    still listed. `next_command` re-reads the list and returns a random
    still-pending line (random, not the head, spreads the run evenly across a
    category-grouped list), and returns None — ending the loop — once nothing is
    pending. A failed iteration leaves its line in the list (on_success is what
    strikes it), so it gets retried on some later iteration.

    Parameters:
      list_file       relative (to the project root) or absolute path to the list.
      prompt_fn       callable(source_abs, target_abs) -> prompt for one file.
                      Receives absolute paths.
      model           the model to drive each command.
      target_suffix   output sibling suffix, e.g. ".ru.md"; lines already ending
                      in it are skipped as already-done / self-referential.
      source_ext      source extension replaced by target_suffix when deriving
                      the target path (default ".md": foo.md -> foo<suffix>).
    """

    def __init__(self, list_file: str,
                 prompt_fn: Callable[[str, str], str],
                 model: str = "sonnet",
                 target_suffix: str = ".ru.md",
                 source_ext: str = ".md"):
        self._list_file_rel = list_file
        self._prompt_fn = prompt_fn
        self._model = model
        self._target_suffix = target_suffix
        self._source_ext = source_ext
        self._current_line: Optional[str] = None  # raw list line being processed

    def list_path(self) -> str:
        return _abs_in_project(self._list_file_rel)

    @property
    def list_file_rel(self) -> str:
        return self._list_file_rel

    def is_pending(self, line: str) -> bool:
        """A list line that still names a file to process (skips blanks, `#`
        comments, and any path already pointing at a target_suffix output)."""
        s = line.strip()
        if not s or s.startswith("#"):
            return False
        if s.lower().endswith(self._target_suffix.lower()):
            return False
        return True

    def target_path(self, source: str) -> str:
        """`<name><target_suffix>` derived from the source path."""
        if source.lower().endswith(self._source_ext.lower()):
            return source[: -len(self._source_ext)] + self._target_suffix
        return source + self._target_suffix

    def pending_lines(self) -> list:
        """All raw list lines still naming work to do (re-read each call)."""
        return [ln for ln in _read_list_lines(self.list_path())
                if self.is_pending(ln)]

    def command_for(self, line: str) -> ClaudeCommand:
        """Build the command for one raw list line, without touching driver
        state — safe to call from any thread (used by the parallel runner)."""
        source = line.strip()
        source_abs = _abs_in_project(source)
        target_abs = self.target_path(source_abs)
        label = os.path.basename(source_abs)
        return ClaudeCommand(self._prompt_fn(source_abs, target_abs),
                             self._model, label)

    def strike(self, line: str) -> bool:
        """Remove the first list entry exactly matching `line`; rewrite the file.

        Returns True if a line was removed, False if it was already gone (e.g.
        hand-edited out). The list's single source of truth — both runners go
        through here so the file always keeps the same shape.
        """
        list_path = self.list_path()
        lines = _read_list_lines(list_path)
        for i, ln in enumerate(lines):
            if ln == line:
                del lines[i]
                break
        else:
            return False
        _write_list_lines(list_path, lines)
        return True

    def model(self) -> str:
        return self._model

    def next_command(self) -> Optional[ClaudeCommand]:
        pending = self.pending_lines()
        if not pending:
            self._current_line = None
            return None
        self._current_line = random.choice(pending)
        return self.command_for(self._current_line)

    def on_success(self, returncode: int) -> None:
        """Remove the just-processed path from the list (the list is the source of
        truth for what is left to do)."""
        if self._current_line is None:
            return
        if self.strike(self._current_line):
            self._current_line = None

    def final_summary(self) -> Optional[str]:
        remaining = len(self.pending_lines())
        if remaining == 0:
            return f"All items done — {self._list_file_rel} is empty."
        return f"{remaining} item(s) still pending in {self._list_file_rel}."
