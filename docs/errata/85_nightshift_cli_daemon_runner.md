# Errata: Night-shift CLI does not yet use DaemonRunner

**Spec:** 85 — Daemon Framework
**Date:** 2026-04-07

## Divergence

The design document (Path 1: Daemon startup) specifies that
`cli/nightshift.py` should wire through `DaemonRunner` for lifecycle
management, PID file handling, and stream scheduling. The current
implementation retains the existing `NightShiftEngine.run()` path.

### What the spec says

- `cli/nightshift.py` creates a `DaemonRunner`, passes `build_streams()`
  output, and calls `DaemonRunner.run()`.
- The CLI accepts `--no-specs`, `--no-fixes`, `--no-hunts`, `--no-spec-gen`
  flags to disable individual work streams.
- `code --watch` is an alias for `night-shift --no-fixes --no-hunts --no-spec-gen`.

### What the code does

- `cli/nightshift.py` creates a `NightShiftEngine` directly and calls
  `engine.run()`.
- The `--no-*` flags are not present on the CLI command.
- `code --watch` delegates to `engine.run.run_code(watch=True)`, not to
  the daemon.

### Why

The `DaemonRunner` and all four work stream classes are fully implemented
and tested in isolation (see `nightshift/daemon.py`, `nightshift/streams.py`).
The CLI integration was deferred to avoid disrupting the existing
`NightShiftEngine` workflow during the daemon framework build-out. The
components are ready to be wired in a follow-up task.

### What works today

- `DaemonRunner` lifecycle, scheduling, budget, and signal handling are
  fully tested via unit and integration smoke tests.
- `build_streams()` factory correctly applies config, CLI flags, and
  platform degradation.
- `handle_merge_strategy()` and `resolve_merge_strategy()` are implemented
  and tested but not yet called from production code paths.
- PID check guards are implemented in `cli/code.py` and `cli/plan.py`.

### Intentional stub

`SpecGeneratorStream.run_once()` is a no-op placeholder for spec 86.
This is documented in the class docstring and is not a wiring gap.
