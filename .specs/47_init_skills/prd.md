# PRD: Install Claude Code Skills via `init --skills`

## Problem

agent-fox ships with a set of Claude Code skills (af-spec, af-fix,
af-spec-audit, af-code-simplifier, af-adr, af-reverse-engineer) that assist
users during interactive Claude Code sessions. Currently, these skills are only
available if manually installed into `~/.claude/skills/` (global) or the
project's `.claude/skills/` directory. There is no automated way for a user to
install them into a project.

The bundled skill templates in `agent_fox/_templates/skills/` lack YAML
frontmatter required by Claude Code, making them unusable as-is.

## Solution

Add a `--skills` flag to the `agent-fox init` command. When set, the command
copies the bundled skill files from `agent_fox/_templates/skills/` into the
project's `.claude/skills/{skill-name}/SKILL.md` directory, making them
available to Claude Code in that project.

The bundled templates must be updated to include the required YAML frontmatter
so they are complete, self-contained SKILL.md files.

## User Experience

```bash
# Initialize project with skills
agent-fox init --skills

# Re-run to update skills to latest version
agent-fox init --skills
```

Output (human-readable):
```
Installed 6 skills to .claude/skills/.
Initialized agent-fox project.
```

Output (JSON mode):
```json
{"status": "ok", "skills_installed": 6, "agents_md": "created"}
```

## Scope

- Install all bundled skills (no subset selection).
- Opt-in via `--skills` flag (not installed by default).
- Overwrite existing skill files on re-run (always install latest version).
- Works on both fresh init and re-init.

## Clarifications

- **Source**: Bundled templates in `agent_fox/_templates/skills/`. These must be
  updated to include YAML frontmatter (name, description, argument-hint) so
  they are valid SKILL.md files. The frontmatter metadata should match what
  is currently in `skills/*/SKILL.md` (the repo-root source of truth).
- **Target**: `{project_root}/.claude/skills/{skill-name}/SKILL.md`.
- **Idempotency**: Overwrite on re-run — always installs the latest version.
- **No subset selection**: All bundled skills are installed together.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 44_init_agents_md | 2 | 1 | Uses the existing init command structure and template loading pattern from group 2 |
