# PRD: Night-Shift Ignore File (`.night-shift`)

## Problem

The `night-shift` command's hunt scan currently scans the entire repository
without a user-controlled exclusion mechanism. Users have no way to tell
agent-fox to skip specific files or directories during hunt scans — for
example, generated code, vendored dependencies, or large data files that
produce irrelevant findings.

## Solution

Introduce a `.night-shift` file in the repository root that follows
`.gitignore` syntax and semantics. The file controls which files and folders
the hunt scan should **not** inspect. It is additive to `.gitignore` — both
are applied, and `.night-shift` further limits the scan scope.

## Scope

- **In scope:** Hunt scan file filtering within the `night-shift` command.
- **Out of scope:** Fix pipeline, spec executor, coding sessions, knowledge
  graph scanning, or any other agent-fox operation.

## Behaviour

1. **File location:** `.night-shift` is expected in the repository root only.
   Agent-fox does not look for `.night-shift` files in subdirectories.

2. **Syntax:** The file uses `.gitignore` syntax (parsed by the `pathspec`
   library with the `gitwildmatch` pattern style). Blank lines and lines
   starting with `#` are comments.

3. **Additive filtering:** `.night-shift` patterns are applied *in addition
   to* `.gitignore` patterns. A file excluded by either is excluded from the
   hunt scan.

4. **Default exclusions:** The following patterns are always excluded,
   regardless of whether a `.night-shift` file exists or what it contains:
   - `.agent-fox/**`
   - `.git/**`
   - `node_modules/**`
   - `__pycache__/**`
   - `.claude/**`

5. **Missing file:** If `.night-shift` does not exist, only the default
   exclusions and `.gitignore` are applied. This is not an error.

6. **Malformed file:** If `.night-shift` contains invalid patterns or cannot
   be read (encoding errors, permission errors), the file is silently ignored
   and the hunt scan proceeds with only the default exclusions and
   `.gitignore`.

7. **Init command:** Running `agent-fox init` creates an empty `.night-shift`
   file in the project root if one does not already exist. The file contains
   a comment header explaining its purpose and lists the default exclusions
   for user reference.

8. **Static tools:** Hunt categories that delegate to external static tools
   (ruff, pytest, mypy) are not affected by `.night-shift`. Those tools use
   their own configuration for file selection. `.night-shift` only affects
   files that agent-fox itself enumerates or presents to AI analysis.

## Design Decisions

1. **File renamed from `.agent-fox-ignore` to `.night-shift`** — Makes it
   obvious that the file only applies to the `night-shift` command, not to
   agent-fox broadly.

2. **Additive to `.gitignore`** — `.night-shift` further limits the scan;
   it cannot un-ignore files that `.gitignore` already excludes.

3. **Hunt scans only** — The fix pipeline and spec executor are not affected.
   They operate on specific issues and specs, not file enumeration.

4. **Static tool output not filtered** — Filtering ruff/pytest output by
   `.night-shift` patterns would be complex and fragile. Instead, users
   should configure those tools' own ignore mechanisms.

5. **`pathspec` promoted to hard dependency** — The codebase already uses
   `pathspec` optionally for `.gitignore` support. Since `.night-shift` is a
   core feature, `pathspec` becomes a required dependency.

6. **Default exclusions baked into code** — `.agent-fox/**`, `.git/**`, etc.
   are always excluded even without a `.night-shift` file, ensuring
   agent-fox never scans its own internal directories.

7. **Default exclusions also written to the init-generated file** — So users
   can see what is excluded by default and use the file as a starting point.

## Source

GitHub issue: https://github.com/agent-fox-dev/agent-fox/issues/343
