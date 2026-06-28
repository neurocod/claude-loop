Current state: plan mode

Allowed states: plan mode | implementation | cleanup | error

## plan mode

Planning. The context is still clean - a good time to look around.

1. Read `TODO.md` (if the file doesn't exist - create an empty one).
2. If needed, analyze the state of the project (code, README, recent commits).
3. If `TODO.md` contains less than 3 tasks, propose a few (1-4) additional tasks for
   the user to choose from and append them to `TODO.md`.
4. Prepare `currentTask.md` for the next implementation run:
   - if `currentTask.md` already exists and contains a task - leave it as is;
   - otherwise, if `TODO.md` contains tasks - pick one task, move it into
     `currentTask.md`, and remove it from `TODO.md`;
   - otherwise, write `Current state: plan mode` into the first line of this file
     and exit.
5. Write `Current state: implementation` into the first line of this file.
6. Exit.

## implementation

Implementation of a single task.

1. Read `currentTask.md`.
2. If `currentTask.md` doesn't exist or is empty - write `Current state: plan mode`
   into the first line of this file and exit. Task selection belongs to `plan mode`.
3. Start implementing the task from `currentTask.md`.
4. Once the skeleton of the new functionality exists, write a unit test for it
   (self-test convention, see `CLAUDE.md` Tests). Use it to verify the logic
   as you build, then commit the test for the future. UI can be tested too - if
   not the rendering, then at least the behaviour (drive the widget, assert state
   and signals). Skip only for purely visual tasks, where the screenshot loop is
   the verification.
5. Along the way you may commit intermediate working results (optional - the
   final commit will be made by `cleanup` anyway).
6. After implementation, write `Current state: cleanup` into the first line.
7. Exit.

## cleanup

Wrapping up and tidying.

1. Update `currentState.md`:
   - if the task is fully done - delete `currentTask.md`;
   - if something is left to finish - write it into `currentTask.md` (or return it to `TODO.md`).
2. Commit the changes (if the result works) or revert them (if it doesn't).
   Part of it may have already been committed during `implementation` - here you
   finish the rest. You may refactor if you find it necessary or useful (to avoid
   accumulating technical debt).
3. Review the last couple of commits and remove added self-evident comments -
   those whose meaning is already clear from the code itself. Keep only comments
   that explain "why", non-obvious decisions, and subtleties.
4. If needed, add something to `TODO.md` or `README.md`. If `TODO.md` has a section that is out of items - remove that section
5. If `README.md` has grown too large - clean it up, leaving only the project
   description and the build system.
6. Write `Current state: plan mode` into the first line.
7. Exit.

## error

A dead end: something went wrong and automatic continuation is impossible
(a recurring build failure, a contradictory task, lack of permissions/information,
doubts about the state framework itself).

In any state, when you hit an unrecoverable problem, write `Current state: error`
into the first line. And write the detailed description of the error to `currentTask.md`, where briefly describe:

- what exactly went wrong and at which step;
- what you have already tried;
- proposed options: change the framework/task, or a specific question for the developer.

After writing these, exit. The orchestrator script must stop and not start the
next iteration until a human sorts it out and manually returns the state to
`plan mode` (or another one).
