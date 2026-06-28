# claude-loop

A reusable engine for **autonomous Claude-CLI loops**: it repeatedly invokes the
`claude` CLI to grind through a unit of work, handling all the scaffolding —
command-line parsing, a rotating mirror log, a git-push policy, the
token-usage / session-window limit machinery, live stream-json rendering, and a
graceful stop file — so a host project only has to say *what work to do each
iteration*.

It ships two ready-made task shapes (and you can write your own `Driver`):

- **State machine** (`StateFileDriver`) — read the first line of a state file
  each iteration and run a fixed prompt against it; stop on an `error` state.
  Good for "follow this playbook until done" loops where progress lives in files.
- **Work queue** (`ListFileDriver`) — process the files listed in a list file
  one at a time (or N at a time, see `run_parallel`), striking each out of the
  list once its command succeeds. Idempotent: stop any time and relaunch.

Designed to be vendored as a **git submodule** under a host project. The code
location and the project root are kept separate: the engine anchors every
project-relative operation (git/claude cwd, the stop file, the relative paths a
Driver is handed) to the project root — the current working directory by
default, or `--project-dir`/`-C`.

## Layout

```
claude_loop/
  cyclecore.py   engine: parse_args, run_loop, the Driver protocol, usage limits,
                 git-push policy, mirror log, stream-json rendering
  drivers.py     StateFileDriver (state machine) and ListFileDriver (work queue)
  parallel.py    run_parallel: N concurrent claude workers over a list file
examples/
  runCycle.py            state-machine wrapper
  runFileList.py         per-file work-queue wrapper
  runFileListParallel.py parallel work-queue wrapper
```

## Use it from a host project

Add it as a submodule, then copy one of the [`examples/`](examples/) wrappers
into your project root and adjust the paths, prompt and model:

```bash
git submodule add <repo-url> tools/claude-loop
cp tools/claude-loop/examples/runFileList.py .   # then edit the constants
```

A wrapper is tiny — it only supplies the project-specific bits and calls into the
engine:

```python
# runFileList.py  (in your project root)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools", "claude-loop"))

from claude_loop import ListFileDriver, parse_args, run_loop

def build_prompt(source, target):
    return (f"Read {source} and write a Markdown summary to {target}. "
            f"Do not modify {source}.")

def main():
    args = parse_args(prog="runFileList.py")
    run_loop(
        ListFileDriver(
            list_file="files.md",
            prompt_fn=build_prompt,
            target_suffix=".summary.md",
            model="sonnet",
        ),
        args, app_name="runFileList",
    )

if __name__ == "__main__":
    main()
```

Run it from the project root so the working directory is the project root (or
pass `--project-dir <path>` from anywhere):

```
python runFileList.py            # drain the list, one file per iteration
python runFileList.py --max 5    # at most 5 iterations
python runFileList.py --dry-run  # print the commands, run nothing
```

### State-machine driver

```python
from claude_loop import StateFileDriver, parse_args, run_loop

def pick_model(state_first_line):
    return "opus"

run_loop(StateFileDriver(state_file="currentState.md", model_fn=pick_model),
         parse_args(prog="runCycle.py"), app_name="runCycle")
```

### Parallel work queue

```python
from claude_loop import ListFileDriver, run_parallel, parse_parallel_args

args = parse_parallel_args(prog="runFileListParallel.py")
run_parallel(ListFileDriver(list_file="files.md",
                            prompt_fn=build_prompt, model="sonnet"),
             args, app_name="runFileListParallel")
```

## Common options

| Option | Meaning |
|---|---|
| `-m, --max N` | stop after N iterations (sequential) / N files total (parallel) |
| `-d, --dry-run` | print the commands, run nothing |
| `-g, --git-push none\|after_new_commits\|each_hour` | when to `git push` |
| `-C, --project-dir DIR` | project root (default: cwd) |
| `-s, --startIn 29m` | wait before starting (sequential only) |
| `-S, --maxStrike 3h` | per-session work budget before a pre-emptive pause |
| `-j, --jobs N` | concurrent workers (parallel only) |

Create a file named `stop` in the project root to halt the loop at the next
iteration boundary; it is removed on stop so the next launch starts clean.

`pip install rich` enables live Markdown rendering of the assistant's output
(the loop works without it, just plainer).
