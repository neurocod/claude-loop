"""
Example wrapper: the parallel counterpart of runFileList.py.

Same per-file work, but with N worker threads running `claude` concurrently
(`run_parallel`) instead of one file at a time. It reuses runFileList.py's driver
(the same list path, target naming, prompt and model); the list file is the
single source of truth, guarded by one lock, so the run stays idempotent.

CLI mirrors the family; the additions are `-j/--jobs N` (default 10), and
`--max N` caps the *total* number of files processed this run, not iterations.

Copy this into your host project root next to runFileList.py and run
`python runFileListParallel.py -j 8`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools", "claude-loop"))

from claude_loop import parse_parallel_args, run_parallel

from runFileList import LIST_FILE_REL, build_driver


def main():
    args = parse_parallel_args(
        prog="runFileListParallel.py",
        description=f"Process the files listed in {LIST_FILE_REL} with N "
                    "concurrent `claude` workers.",
    )
    run_parallel(build_driver(), args, app_name="runFileListParallel")


if __name__ == "__main__":
    main()
