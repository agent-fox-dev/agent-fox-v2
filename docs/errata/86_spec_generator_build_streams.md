# Erratum: build_streams() wiring for SpecGeneratorStream

## Spec

86 — Spec Generator

## What the spec says

- `SpecGeneratorStream.__init__()` accepts `config`, `platform`, and
  `repo_root` parameters (design.md, Components and Interfaces section).
- Task 5.2 says "Replace the no-op stub from spec 85 with real
  implementation" but does not mention updating `build_streams()`.

## What the code does

The `build_streams()` factory in `nightshift/streams.py` was constructing
`SpecGeneratorStream` with only `enabled` and `interval` keyword arguments,
omitting the `config`, `platform`, and `repo_root` parameters required for
the generator to function. This caused `run_once()` to silently no-op
(the early-return guard `if self._platform is None or self._generator is
None` would always trigger).

## Fix applied (task group 6)

- Added `platform` and `repo_root` optional keyword parameters to
  `build_streams()`.
- The factory now passes `config=ns_config` (the `NightShiftConfig`
  instance from `config.night_shift`), `platform`, and `repo_root` to
  `SpecGeneratorStream`.
- When callers of `build_streams()` do not supply `platform` or
  `repo_root`, the stream gracefully degrades to no-op (same as before),
  preserving backward compatibility.

## Stale section header comments

Removed outdated comments referencing "stub" in `spec_gen.py` and
`streams.py` that were left over from task groups 3-5.
