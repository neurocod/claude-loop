"""
Example wrapper: drive a state machine from a state file - currentState.md or another

This is the StateFileDriver pattern. Each iteration reads the first line of a
state file and runs a fixed prompt against it; on an `error` state the loop stops
for human intervention, otherwise it runs forever (until the stop file, --max, or
Ctrl+C). The state lives in files in your project, so each `claude` call starts
with fresh context and picks up where the last one left off — the canonical
"Ralph" pattern.

A typical setup: `currentState.md` names the current phase, and your prompt tells
claude to follow a playbook (e.g. read a TODO list, do one item, update the
state). Use `model_fn` to vary the model by state if you like.

Copy this into your host project root (next to the `tools/claude-loop` submodule),
adjust the constants, and run `python runCycle.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools", "claude-loop"))

from claude_loop import StateFileDriver, parse_args, run_loop

STATE_FILE_REL = "currentState.md"


def pick_model(state_first_line: str) -> str:
    """Choose the model from the current state (override as needed)."""
    if "implementation" in state_first_line.lower():
        return "opus"
    return "opus"


def main():
    args = parse_args(
        prog="runCycle.py",
        description=f"Autonomous loop driving the Claude CLI per {STATE_FILE_REL}.",
    )
    driver = StateFileDriver(state_file=STATE_FILE_REL, model_fn=pick_model)
    run_loop(driver, args, app_name="runCycle")


if __name__ == "__main__":
    main()
