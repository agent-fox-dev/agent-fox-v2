# PRD: Update settings.local.json on init

## Problem

When agent-fox drives Claude Code sessions, Claude Code prompts the user for
permission on many common tool invocations (bash commands, file reads, etc.).
To allow smooth autonomous operation, a `.claude/settings.local.json` file with
pre-approved permissions must exist in the project root.

Currently, this file must be created manually. The init command should automate
this.

## Requirements

During `agent-fox init`, the system SHALL ensure that
`.claude/settings.local.json` contains a canonical set of permission entries
required for autonomous session execution.

### Canonical Permission List

```json
{
  "permissions": {
    "allow": [
      "Bash(bash:*)",
      "Bash(wc:*)",
      "Bash(git:*)",
      "Bash(python:*)",
      "Bash(python3:*)",
      "Bash(uv:*)",
      "Bash(make:*)",
      "Bash(sort:*)",
      "Bash(awk:*)",
      "Bash(ruff:*)",
      "Bash(gh:*)",
      "Bash(claude:*)",
      "Bash(source .venv/bin/activate:*)",
      "WebSearch",
      "WebFetch(domain:pypi.org)",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:raw.githubusercontent.com)",
      "Grep",
      "Read",
      "Glob",
      "Edit",
      "Write"
    ]
  }
}
```

### Behavior

- **File does not exist:** Create `.claude/settings.local.json` with the
  canonical permission list.
- **File exists:** Merge — add any missing canonical entries to
  `permissions.allow`, but preserve user-added entries that are not in the
  canonical list.
- **`.claude/` directory does not exist:** Create it.
- **No auto-commit:** The file is created/updated but not committed. Consistent
  with current init behavior.
- **No gitignore management:** The `.claude/` directory and its contents are
  left to the user's discretion regarding git tracking.
- **Idempotency:** Running init multiple times is safe — missing entries are
  added, existing entries (canonical or user-added) are preserved.

## Clarifications

1. **Merge policy:** When the file already exists, add missing canonical
   entries but preserve user additions. Never remove entries.
2. **Commit behavior:** No auto-commit — consistent with current init behavior.
3. **Git tracking:** Left to the user — no special gitignore management for
   `.claude/`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 3 | 1 | Extends the init command implemented in group 3 |
