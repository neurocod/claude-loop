# claude-loop

A reusable engine for **autonomous Claude-CLI loops**: it repeatedly invokes the
`claude` CLI to grind through a unit of work, handling all the scaffolding —
command-line parsing, a rotating mirror log, a git-push policy, the
token-usage / session-window limit machinery, live stream-json rendering, and a
graceful stop file — so a host project only has to say *what work to do each
iteration*.

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
```

## Use it from a host project

Add it as a submodule and write a thin wrapper that supplies your paths, prompt
and model:

```bash
git submodule add <repo-url> tools/claude-loop
```

```python
# runTranslate.py  (in your project root)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools", "claude-loop"))

from claude_loop import ListFileDriver, parse_args, run_loop

RULES = (
    "Translate {src} from English to Russian; write the result to {dst}. "
    "Keep numbers, units and `search:` strings verbatim. Do not touch {src}."
)

def main():
    args = parse_args(prog="runTranslate.py")
    run_loop(
        ListFileDriver(
            list_file="products/list.md",
            target_suffix=".ru.md",
            prompt_fn=lambda src, dst: RULES.format(src=src, dst=dst),
            model="sonnet",
        ),
        args, app_name="runTranslate",
    )

if __name__ == "__main__":
    main()
```

Run it from the project root so the working directory is the project root (or
pass `--project-dir <path>` from anywhere):

```
python runTranslate.py            # drain the list, one file per iteration
python runTranslate.py --max 5    # at most 5 iterations
python runTranslate.py --dry-run  # print the commands, run nothing
```

### State-machine driver

```python
from claude_loop import StateFileDriver, parse_args, run_loop

def pick_model(state_first_line):
    return "opus"

run_loop(StateFileDriver(state_file="products/currentState.md",
                         model_fn=pick_model),
         parse_args(prog="runCycle.py"), app_name="runCycle")
```

### Parallel list runner

```python
from claude_loop import ListFileDriver, run_parallel, parse_parallel_args

args = parse_parallel_args(prog="runTranslateParallel.py")
run_parallel(ListFileDriver(list_file="products/list.md",
                            prompt_fn=my_prompt, model="sonnet"),
             args, app_name="runTranslateParallel")
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
