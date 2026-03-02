# PRD: Fix Ruff Formatting Violations

## Problem

43 Python files in the `agent_fox/` package do not conform to ruff's formatting rules. Running `uv run ruff format --check agent_fox/` reports that all 43 files "Would reformat."

## Goal

Apply ruff's auto-formatter to all 43 affected files so that `uv run ruff format --check agent_fox/` exits with code 0 and reports no files needing reformatting.

## Scope

- **In scope:** Running `uv run ruff format` on the `agent_fox/` directory to auto-fix all formatting violations.
- **Out of scope:** Lint rule violations (ruff check), logic changes, test changes, or any behavioral modifications.

## Affected Files

The following 43 files need reformatting:

### CLI module (6 files)
- `agent_fox/cli/fix.py`
- `agent_fox/cli/init.py`
- `agent_fox/cli/lint_spec.py`
- `agent_fox/cli/patterns.py`
- `agent_fox/cli/plan.py`
- `agent_fox/cli/reset.py`

### Core module (1 file)
- `agent_fox/core/models.py`

### Engine module (5 files)
- `agent_fox/engine/orchestrator.py`
- `agent_fox/engine/parallel.py`
- `agent_fox/engine/reset.py`
- `agent_fox/engine/state.py`
- `agent_fox/engine/sync.py`

### Fix module (4 files)
- `agent_fox/fix/clusterer.py`
- `agent_fox/fix/detector.py`
- `agent_fox/fix/loop.py`
- `agent_fox/fix/spec_gen.py`

### Graph module (4 files)
- `agent_fox/graph/fast_mode.py`
- `agent_fox/graph/persistence.py`
- `agent_fox/graph/resolver.py`
- `agent_fox/graph/types.py`

### Hooks module (1 file)
- `agent_fox/hooks/security.py`

### Knowledge module (7 files)
- `agent_fox/knowledge/causal.py`
- `agent_fox/knowledge/embeddings.py`
- `agent_fox/knowledge/ingest.py`
- `agent_fox/knowledge/jsonl_sink.py`
- `agent_fox/knowledge/migrations.py`
- `agent_fox/knowledge/search.py`
- `agent_fox/knowledge/temporal.py`

### Memory module (2 files)
- `agent_fox/memory/extraction.py`
- `agent_fox/memory/store.py`

### Reporting module (3 files)
- `agent_fox/reporting/formatters.py`
- `agent_fox/reporting/standup.py`
- `agent_fox/reporting/status.py`

### Session module (2 files)
- `agent_fox/session/context.py`
- `agent_fox/session/runner.py`

### Spec module (4 files)
- `agent_fox/spec/ai_validator.py`
- `agent_fox/spec/discovery.py`
- `agent_fox/spec/parser.py`
- `agent_fox/spec/validator.py`

### UI module (1 file)
- `agent_fox/ui/theme.py`

### Workspace module (3 files)
- `agent_fox/workspace/git.py`
- `agent_fox/workspace/harvester.py`
- `agent_fox/workspace/worktree.py`

## Success Criteria

- `uv run ruff format --check agent_fox/` exits with code 0.
- No functional or behavioral changes to any module.
