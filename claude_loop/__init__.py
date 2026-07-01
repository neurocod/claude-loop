"""
claude_loop - a reusable engine for autonomous Claude-CLI loops.

Vendor this package as a git submodule under a host project, then write a thin
wrapper in the project that subclasses a Driver — supplying the project-specific
bits (which file to read, which prompt to send, which model to use) as class
attributes / overridden methods — and calls its `.main()`:

    # runTranslate.py (thin wrapper in the host project root)
    from claude_loop import ListFileDriver

    class TranslateDriver(ListFileDriver):
        list_file     = "products/list.md"
        target_suffix = ".ru.md"
        default_model = "sonnet"
        app_name      = "runTranslate"
        prog          = "runTranslate.py"

        def prompt(self, source, target):
            return f"Translate {source} to Russian, write {target}, keep search: verbatim ..."

    if __name__ == "__main__":
        TranslateDriver.main()          # or .main_parallel() for N concurrent workers

The engine anchors every project-relative operation (git/claude cwd, the stop
file, the Driver's relative paths) to the project root — the current working
directory by default, or --project-dir / set_project_root(). So the code can
live in a submodule subdirectory while still driving the host project's repo.

See cyclecore for the engine and the Driver protocol, drivers for the two ready
made Drivers, and parallel for the concurrent list runner.
"""

from .cyclecore import (
    ClaudeCommand,
    Driver,
    GitPushPolicy,
    LoopStop,
    UsageComputer,
    build_claude_argv,
    log_file_path,
    parse_args,
    parse_duration,
    project_dir,
    run_loop,
    set_project_root,
)
from .drivers import ListFileDriver, StateFileDriver
from .parallel import run_parallel
from .parallel import parse_args as parse_parallel_args

__all__ = [
    "ClaudeCommand",
    "Driver",
    "GitPushPolicy",
    "ListFileDriver",
    "LoopStop",
    "StateFileDriver",
    "UsageComputer",
    "build_claude_argv",
    "log_file_path",
    "parse_args",
    "parse_parallel_args",
    "parse_duration",
    "project_dir",
    "run_loop",
    "run_parallel",
    "set_project_root",
]
