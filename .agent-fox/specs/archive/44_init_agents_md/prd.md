# PRD: Init Command — Scaffold AGENTS.md Template

## Problem

`AGENTS.md` is referenced throughout the agent-fox codebase as a project
convention file for coding agents. The auto-improve analyzer
(`agent_fox/fix/analyzer.py`) searches for it in `_CONVENTION_FILES`, and
skills (`af-spec`, `af-fix`) mention it in their documentation. However, the
`init` command never creates it — users must know about the convention and
write the file manually.

## Solution

Extend the `agent-fox init` command to scaffold an `AGENTS.md` file in the
project root. The template is a static file bundled in
`agent_fox/_templates/agents_md.md`. The file is copied verbatim on first
init; re-init skips the copy if the file already exists (user content is
never overwritten).

The template content is a generalized version of the `AGENTS.md` from the
agent-fox repository, with project-specific paths replaced by placeholder
markers (e.g., `<main_package>/`) that users fill in for their project.

## Requirements

1. Bundle a static `AGENTS.md` template at
   `agent_fox/_templates/agents_md.md`. The template content is a
   generalized version of the existing `AGENTS.md` from this repository,
   with project-specific references replaced by placeholder markers.

2. During `agent-fox init` (fresh project), copy the template to
   `{project_root}/AGENTS.md` using UTF-8 encoding. Log a user-facing
   message: `Created AGENTS.md.`

3. During `agent-fox init` (re-init on existing project), check whether
   `{project_root}/AGENTS.md` already exists. If it does, skip the copy
   silently (no message, no warning). If it does not exist, copy the
   template and log: `Created AGENTS.md.`

4. The existence of `CLAUDE.md` in the project root does NOT affect whether
   `AGENTS.md` is created. Both files may coexist.

5. `AGENTS.md` is user-owned content intended to be git-tracked. It MUST NOT
   be added to `.gitignore` by `init`.

6. In `--json` mode, include an `"agents_md"` field in the JSON output
   indicating the action taken: `"created"` if the file was written,
   `"skipped"` if it already existed.

## Implementation Notes

- `init` is defined in `agent_fox/cli/init.py:92-184`.
- The template should be loaded using `Path(__file__)` relative resolution
  (consistent with how `_templates/prompts/` are loaded in
  `agent_fox/session/prompt.py`).
- The copy logic follows the same pattern as `_ensure_claude_settings()`:
  check existence, write if absent, skip if present.
- No merge or update logic on re-init — the file is user-owned once created.

## Clarifications

- **Template content**: Generalized version of the existing `AGENTS.md` from
  this repository with placeholder markers (e.g., `<main_package>/`,
  `<test_directory>/`). Users customize the placeholders for their project.
- **Template storage**: Static file at `agent_fox/_templates/agents_md.md`,
  loaded via `Path(__file__)` resolution. Not generated inline.
- **CLAUDE.md interaction**: `AGENTS.md` is always created regardless of
  whether `CLAUDE.md` exists. The analyzer's `_CONVENTION_FILES` priority
  order is unchanged.
- **JSON mode**: The `{"status": "ok"}` response gains an `"agents_md"`
  field with value `"created"` or `"skipped"`.
- **Logging**: User-facing `click.echo` only. Message shown only when file
  is created, not when skipped.
- **Encoding**: UTF-8.
- **File location**: `Path.cwd() / "AGENTS.md"` — project root.
