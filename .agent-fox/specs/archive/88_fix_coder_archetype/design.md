# Design Document: Fix-Coder Archetype

## Overview

Introduces a `fix_coder` archetype with a dedicated `fix_coding.md` template
for night-shift issue-driven fix sessions. Reuses all existing session
infrastructure (session runner, worktrees, harvest, SDK params) while providing
issue-focused prompt instructions that prevent spec artifact creation.

## Architecture

```mermaid
flowchart TD
    FP[fix_pipeline.py] -->|archetype="fix_coder"| BSP[build_system_prompt]
    BSP -->|loads template| FC[fix_coding.md]
    BSP -->|loads template| C[coding.md]
    FP -->|archetype="fix_coder"| RS[_run_session]
    RS -->|resolves SDK params| SDK[sdk_params.py]
    SDK -->|looks up| REG[ARCHETYPE_REGISTRY]
    REG -->|fix_coder entry| FCE["ArchetypeEntry(fix_coder)"]
    REG -->|coder entry| CE["ArchetypeEntry(coder)"]

    style FC fill:#4a9,stroke:#333
    style FCE fill:#4a9,stroke:#333
    style C fill:#888,stroke:#333
    style CE fill:#888,stroke:#333
```

The green nodes are new; gray nodes are existing and unchanged.

### Module Responsibilities

1. **`agent_fox/_templates/prompts/fix_coding.md`** (new) — Issue-focused
   system prompt template for the fix_coder archetype.
2. **`agent_fox/archetypes.py`** (modified) — Adds `fix_coder` entry to
   `ARCHETYPE_REGISTRY`.
3. **`agent_fox/nightshift/fix_pipeline.py`** (modified) — Uses `fix_coder`
   archetype instead of `coder`; removes hardcoded commit format.
4. **`agent_fox/session/prompt.py`** (unchanged) — `build_system_prompt()`
   loads templates via archetype lookup; works with any registered archetype.
5. **`agent_fox/engine/sdk_params.py`** (unchanged) — Resolves SDK params
   via archetype name; `fix_coder` uses its own registry defaults.

## Execution Paths

### Path 1: Fix pipeline coder session with fix_coder archetype

1. `nightshift/fix_pipeline.py: _build_coder_prompt(spec, triage)` — builds
   system and task prompts
2. `session/prompt.py: build_system_prompt(context, 0, "fix-issue-313", archetype="fix_coder")` →
   `str` (system prompt)
3. `session/archetypes.py: get_archetype("fix_coder")` → `ArchetypeEntry`
   with `templates=["fix_coding.md"]`
4. `session/prompt.py: _load_template("fix_coding.md")` → `str` (template
   content, frontmatter stripped)
5. `session/prompt.py: _interpolate(template, variables)` → `str`
   (interpolated template)
6. `nightshift/fix_pipeline.py: _run_coder_session(workspace, spec, system_prompt, task_prompt)` —
   runs session with `archetype="fix_coder"`
7. `nightshift/fix_pipeline.py: _run_session("fix_coder", workspace, spec=spec, ...)` —
   resolves SDK params for `fix_coder`
8. `engine/sdk_params.py: resolve_model_tier(config, "fix_coder")` → `str`
   (model tier from registry)
9. `session/session.py: run_session(...)` — side effect: agent executes with
   fix-focused prompt

## Components and Interfaces

### New Template: `fix_coding.md`

The template uses the same placeholder variables as `coding.md`:
- `{spec_name}` — e.g., `"fix-issue-313"` (used for identification only)
- `{task_group}` — always `"0"` for fix sessions (not referenced in template)
- `{number}` — same as `spec_name` (no underscore split)
- `{specification}` — same as `spec_name`

Key differences from `coding.md`:

| Section | `coding.md` | `fix_coding.md` |
|---------|-------------|-----------------|
| Role description | Spec-driven coder | Issue-driven fixer |
| Task lock | Choose one task group from tasks.md | Fix the described issue |
| Implement | Group 1 = tests, Group N = code | Directly implement the fix |
| Git workflow | Conventional commits | `fix(#N, nightshift):` format |
| Session summary | Write .session-summary.json | Omitted |
| Session learnings | Write .session-learnings.md | Omitted |
| Land the session | Update tasks.md, commit | Commit, clean tree |
| Quality gates | Same | Same |

### Modified Archetype Entry

```python
"fix_coder": ArchetypeEntry(
    name="fix_coder",
    templates=["fix_coding.md"],
    default_model_tier="STANDARD",
    injection=None,
    task_assignable=False,
    default_max_turns=300,
    default_thinking_mode="adaptive",
    default_thinking_budget=64000,
)
```

### Modified `_build_coder_prompt()`

Before:
```python
system_prompt = build_system_prompt(..., archetype="coder")
task_prompt = spec.task_prompt
task_prompt = f"{task_prompt}\n\n...commit format..."
```

After:
```python
system_prompt = build_system_prompt(..., archetype="fix_coder")
task_prompt = spec.task_prompt
# commit format is in the template; no hardcoded append
```

### Modified `_run_coder_session()`

Before:
```python
return await self._run_session("coder", workspace, ...)
```

After:
```python
return await self._run_session("fix_coder", workspace, ...)
```

## Data Models

No new data models. The existing `ArchetypeEntry`, `InMemorySpec`, and
`FixMetrics` dataclasses are unchanged.

## Operational Readiness

- **Observability:** Audit events already include the archetype name in node
  IDs (e.g., `fix-issue-313:0:fix_coder`). No changes needed.
- **Rollback:** Revert the three changed files to restore `coder` usage.
- **Migration:** No config migration needed. Existing `archetypes.overrides.coder`
  settings continue to apply to spec-driven sessions; `fix_coder` starts with
  registry defaults.

## Correctness Properties

### Property 1: Template Isolation

*For any* `spec_name` string, the `fix_coding.md` template after interpolation
SHALL NOT contain the substring `.specs/`.

**Validates: 88-REQ-1.2, 88-REQ-1.E1**

### Property 2: Archetype Registry Completeness

*For any* lookup of `"fix_coder"` in `ARCHETYPE_REGISTRY`, the returned entry
SHALL have `templates == ["fix_coding.md"]` and default values matching
`coder` except for `task_assignable` (which is `False`).

**Validates: 88-REQ-2.1, 88-REQ-2.2, 88-REQ-2.3**

### Property 3: Fix Pipeline Archetype Usage

*For any* invocation of `_build_coder_prompt()`, the resulting system prompt
SHALL be built using the `fix_coder` archetype, and the task prompt SHALL NOT
contain hardcoded commit format instructions appended by `_build_coder_prompt`.

**Validates: 88-REQ-3.1, 88-REQ-3.3**

### Property 4: SDK Parameter Parity

*For any* SDK parameter resolution function called with `archetype="fix_coder"`
and no config overrides, the returned value SHALL equal the value returned for
`archetype="coder"` with no config overrides, except for `task_assignable`.

**Validates: 88-REQ-4.1**

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| `fix_coding.md` not found | `ConfigError` raised by `_load_template()` | 88-REQ-1.1 |
| `fix_coder` not in registry | Fall back to `coder`, log warning | 88-REQ-3.E1 |

## Technology Stack

- Python 3.12+
- Existing template loading (`session/prompt.py`)
- Existing archetype registry (`archetypes.py`)
- Existing fix pipeline (`nightshift/fix_pipeline.py`)

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and merged into `develop`
7. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests:** Verify archetype registration, template loading, template
  content assertions (no `.specs/` references, commit format present), and
  fix pipeline archetype argument.
- **Property tests:** Template isolation (Property 1), registry completeness
  (Property 2), SDK parity (Property 4).
- **Integration smoke test:** End-to-end fix pipeline session uses
  `fix_coding.md` content in the system prompt.
