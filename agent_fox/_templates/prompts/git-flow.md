---
inclusion: always
---

# Git Workflow

This repository uses a `develop` integration branch with one feature branch per task.

## Branch Policy

- Never commit directly to `main` or `develop`
- Create one branch per task using `feature/<task-name>`
- Do not reuse an old feature branch for a new task

## Session Start Commands

The coding agent runs inside a git worktree that is already on the correct
feature branch. Do **not** switch branches — the worktree is ready to use.

```bash
git fetch origin
git status --short --branch
```

Do **not** rebase onto develop yourself — the orchestrator handles
rebasing and merging into develop after the session ends.

## Commit Policy

- Use conventional commits: `<type>: <description>`
- Commit only files relevant to the selected task
- Keep commits focused and traceable to `tasks.md`
- Merge `.gitignore` updates manually; never overwrite unrelated ignore rules
- **Never add `Co-Authored-By` lines.** No AI attribution in commits — ever.

## Session Landing Commands

Commit your work and push the feature branch. Do **not** merge into develop —
the orchestrator handles that after the session ends.

```bash
git add .
git commit -m "<type>: <description>"
git push origin feature/<task-name>
git status --short --branch
```

## Required End State

- Local working tree is clean
- Feature branch is pushed to `origin`
- Do **not** switch to develop or merge locally
