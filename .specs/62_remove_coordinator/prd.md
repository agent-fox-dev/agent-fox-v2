# PRD: Remove Coordinator Archetype

## Problem Statement

The coordinator archetype was designed as an LLM-powered cross-spec dependency
analyzer that would run during plan creation to detect inter-spec edges. After
analysis, the coordinator adds more cost, latency, non-determinism, and
complexity than it provides value:

- Cross-spec dependencies are already declared in `prd.md` dependency tables,
  authored by the `af-spec` skill which reads all existing specs at creation
  time.
- The coordinator is defined but never wired up — the `coordinator_overrides`
  parameter in `build_graph()` is always `None`, and no session invocation
  exists.
- The `_apply_coordinator_overrides()` function in the graph builder is dead
  code (Layer 2 of the three-layer archetype assignment).
- The coordinator template, archetype registry entry, model config field, and
  associated tests all exist for a feature that was never activated.

Removing it simplifies the codebase and eliminates a dead code path.

## Scope

### In scope

Remove all coordinator code, configuration, and tests at every level:

1. **Archetype registry** (`agent_fox/session/archetypes.py`): Remove the
   `"coordinator"` entry from `ARCHETYPE_REGISTRY`.
2. **Template file** (`agent_fox/_templates/prompts/coordinator.md`): Delete.
3. **Graph builder** (`agent_fox/graph/builder.py`): Remove
   `_apply_coordinator_overrides()`, the `coordinator_overrides` parameter from
   `build_graph()`, and the Layer 2 application call.
4. **Prompt mapping** (`agent_fox/session/prompt.py`): Remove the
   `"coordinator"` role mapping.
5. **Spec parser** (`agent_fox/spec/parser.py`): Remove `"coordinator"` from
   the known archetypes list.
6. **Model config** (`agent_fox/core/config.py`): Remove the `coordinator`
   field from `ModelConfig`.
7. **Config generator** (`agent_fox/core/config_gen.py`): Remove coordinator
   description entry.
8. **Tests**: Remove or update all tests that reference the coordinator.
9. **Config files** (`.agent-fox/config.toml`, `hack/config.toml`): Remove
   coordinator model tier lines.

### Out of scope

- Changes to the `plan` command or its `--validate` flag (separate spec).
- Changes to the `af-spec` skill's dependency scanning.
- Archived spec documents in `.specs/archive/` (historical reference, not
  modified).
