# Implementation Plan: Oracle Agent Archetype

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The oracle archetype is implemented in 6 task groups. Group 1 writes all
failing tests. Groups 2-5 implement the feature incrementally: data model and
parser, knowledge store, graph builder changes, and prompt/config/template
integration. Group 6 is the final checkpoint.

The implementation follows the existing archetype patterns (skeptic, verifier)
to maintain consistency. The key novel piece is multi-auto_pre support in the
graph builder.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/oracle/ tests/property/oracle/ tests/integration/oracle/`
- Unit tests: `uv run pytest -q tests/unit/oracle/`
- Property tests: `uv run pytest -q tests/property/oracle/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/unit/oracle/` directory with `__init__.py`
    - Create `tests/property/oracle/` directory with `__init__.py`
    - Create `tests/integration/oracle/` directory with `__init__.py`
    - _Test Spec: TS-32-1 through TS-32-13_

  - [x] 1.2 Translate acceptance-criterion tests
    - `tests/unit/oracle/test_registry.py`: TS-32-1 (registry entry), TS-32-2 (config enabled)
    - `tests/unit/oracle/test_graph_builder.py`: TS-32-3 (single injection), TS-32-4 (dual auto_pre), TS-32-5 (backward compat)
    - `tests/unit/oracle/test_parser.py`: TS-32-6 (parse valid JSON), TS-32-7 (dataclass fields)
    - `tests/unit/oracle/test_context.py`: TS-32-10 (render drift context)
    - `tests/unit/oracle/test_blocking.py`: TS-32-11 (block threshold), TS-32-12 (config defaults)
    - `tests/integration/oracle/test_store.py`: TS-32-8 (insert and query), TS-32-9 (supersession), TS-32-13 (hot-load)
    - _Test Spec: TS-32-1 through TS-32-13_

  - [x] 1.3 Translate edge-case tests
    - `tests/unit/oracle/test_registry.py`: TS-32-E1 (oracle disabled)
    - `tests/unit/oracle/test_graph_builder.py`: TS-32-E2 (empty spec), TS-32-E3 (legacy plan compat)
    - `tests/unit/oracle/test_parser.py`: TS-32-E4 (no JSON), TS-32-E5 (missing fields)
    - `tests/unit/oracle/test_context.py`: TS-32-E6 (no findings)
    - `tests/unit/oracle/test_blocking.py`: TS-32-E7 (advisory mode), TS-32-E8 (threshold clamped)
    - `tests/unit/oracle/test_graph_builder.py`: TS-32-E9 (hot-load failure)
    - _Test Spec: TS-32-E1 through TS-32-E9_

  - [x] 1.4 Translate property tests
    - `tests/property/oracle/test_oracle_props.py`: TS-32-P1 through TS-32-P8
    - Use Hypothesis strategies for generating drift findings, batch sequences, thresholds
    - _Test Spec: TS-32-P1 through TS-32-P8_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/oracle/ tests/property/oracle/ tests/integration/oracle/`

- [x] 2. Data model, parser, and DriftFinding
  - [x] 2.1 Create DriftFinding dataclass
    - Add `DriftFinding` frozen dataclass to `agent_fox/knowledge/review_store.py`
    - Fields: id, severity, description, spec_ref, artifact_ref, spec_name, task_group, session_id, superseded_by, created_at
    - _Requirements: 6.3_

  - [x] 2.2 Implement parse_oracle_output()
    - Add `parse_oracle_output()` to `agent_fox/session/review_parser.py`
    - Reuse `_extract_json_blocks()` for JSON extraction
    - Look for `"drift_findings"` key in parsed JSON
    - Validate severity and description presence
    - Return list of DriftFinding instances
    - _Requirements: 6.1, 6.2_

  - [x] 2.3 Add oracle archetype registry entry
    - Add `"oracle"` entry to `ARCHETYPE_REGISTRY` in `agent_fox/session/archetypes.py`
    - `injection="auto_pre"`, `default_model_tier="STANDARD"`, `task_assignable=True`
    - `default_allowlist=["ls", "cat", "git", "grep", "find", "head", "tail", "wc"]`
    - `templates=["oracle.md"]`
    - _Requirements: 1.1, 1.3_

  - [x] 2.4 Add OracleSettings config and oracle toggle
    - Add `oracle: bool = False` to `ArchetypesConfig` in `agent_fox/core/config.py`
    - Add `OracleSettings` Pydantic model with `block_threshold: int | None = None`
    - Add `oracle_settings: OracleSettings` to `ArchetypesConfig`
    - Add clamping validator for block_threshold (< 1 -> 1)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/oracle/test_registry.py tests/unit/oracle/test_parser.py -k "TS_32_1 or TS_32_2 or TS_32_6 or TS_32_7 or TS_32_12 or TS_32_E1 or TS_32_E4 or TS_32_E5 or TS_32_E8"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/session/archetypes.py agent_fox/session/review_parser.py agent_fox/knowledge/review_store.py agent_fox/core/config.py`
    - [x] Requirements 1.1, 1.3, 6.1, 6.2, 6.3, 10.1, 10.2, 10.E1 acceptance criteria met

- [x] 3. Knowledge store (DuckDB migration and CRUD)
  - [x] 3.1 Add drift_findings table migration
    - Add new migration in `agent_fox/knowledge/db.py` creating the `drift_findings` table
    - Columns: id UUID PK, severity VARCHAR NOT NULL, description VARCHAR NOT NULL, spec_ref VARCHAR, artifact_ref VARCHAR, spec_name VARCHAR NOT NULL, task_group VARCHAR NOT NULL, session_id VARCHAR NOT NULL, superseded_by UUID, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    - Migration must be idempotent (CREATE TABLE IF NOT EXISTS)
    - _Requirements: 7.2_

  - [x] 3.2 Implement insert_drift_findings()
    - Add `insert_drift_findings()` to `agent_fox/knowledge/review_store.py`
    - Follow same supersession pattern as `insert_findings()`
    - Supersede existing active records for same (spec_name, task_group) before insert
    - Insert causal links from superseded to new records
    - _Requirements: 7.1, 7.3_

  - [x] 3.3 Implement query_active_drift_findings()
    - Add `query_active_drift_findings()` to `agent_fox/knowledge/review_store.py`
    - Query WHERE superseded_by IS NULL, sorted by severity priority
    - Accept optional task_group filter
    - _Requirements: 7.4_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/integration/oracle/test_store.py -k "TS_32_8 or TS_32_9"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/`
    - [x] Requirements 7.1, 7.2, 7.3, 7.4, 7.E1 acceptance criteria met

- [x] 4. Graph builder multi-auto_pre support
  - [x] 4.1 Modify _inject_archetype_nodes() for multiple auto_pre
    - Count enabled auto_pre archetypes
    - If count > 1: use `{spec}:0:{arch_name}` node IDs
    - If count == 1: use `{spec}:0` for backward compatibility
    - Each auto_pre node gets an edge to the first coder group
    - No edges between auto_pre nodes (parallel execution)
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

  - [x] 4.2 Modify _ensure_archetype_nodes() for runtime injection
    - Handle oracle injection at runtime when plan was built without it
    - When both skeptic (at :0) and oracle are needed, add oracle with distinct ID
    - Update edges and order lists
    - _Requirements: 3.E1, 4.1, 4.2_

  - [x] 4.3 Update hot_load_specs integration
    - After hot-loading new specs, inject oracle nodes (via _ensure_archetype_nodes or direct injection)
    - New oracle nodes added to state as "pending"
    - _Requirements: 4.1, 4.2, 4.E1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/oracle/test_graph_builder.py tests/integration/oracle/test_store.py -k "TS_32_3 or TS_32_4 or TS_32_5 or TS_32_13 or TS_32_E2 or TS_32_E3 or TS_32_E9"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/graph/ agent_fox/engine/`
    - [x] Requirements 2.1, 2.2, 2.E1, 3.1, 3.2, 3.3, 3.E1, 4.1, 4.2, 4.E1 acceptance criteria met

- [x] 5. Prompt template, context rendering, and blocking
  - [x] 5.1 Create oracle.md prompt template
    - Create `agent_fox/_templates/prompts/oracle.md` with YAML frontmatter
    - Role: oracle, description: Spec assumption validator
    - Instructions: read spec files, extract assumptions, verify against codebase
    - Output format: JSON with `drift_findings` array
    - Constraints: read-only, no file modifications
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.2 Implement render_drift_context()
    - Add `render_drift_context()` to `agent_fox/session/prompt.py`
    - Query active drift findings from DuckDB
    - Render as `## Oracle Drift Report` markdown with severity groups
    - Return None if no findings
    - _Requirements: 8.1, 8.2, 8.E1_

  - [x] 5.3 Integrate drift context into session preparation
    - Add `("oracle_drift.md", "## Oracle Drift Report")` check in `_ARCHETYPE_SPEC_FILES` or call `render_drift_context()` during context assembly
    - Only include if oracle has run and findings exist
    - _Requirements: 8.1_

  - [x] 5.4 Implement blocking logic
    - After oracle session completes: parse output, count critical findings
    - If block_threshold configured and critical_count > threshold: mark node failed
    - If no threshold or within threshold: mark node completed
    - Wire into session result processing in the orchestrator
    - _Requirements: 9.1, 9.2, 9.3, 9.E1_

  - [x] 5.V Verify task group 5
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/oracle/test_context.py tests/unit/oracle/test_blocking.py -k "TS_32_10 or TS_32_11 or TS_32_E6 or TS_32_E7"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/session/ agent_fox/engine/`
    - [x] Requirements 5.1-5.4, 5.E1, 5.E2, 8.1, 8.2, 8.E1, 9.1-9.3, 9.E1 acceptance criteria met

- [x] 6. Checkpoint - Oracle Complete
  - [x] 6.1 Full test suite verification
    - All spec tests pass: `uv run pytest -q tests/unit/oracle/ tests/property/oracle/ tests/integration/oracle/`
    - All property tests pass: `uv run pytest -q tests/property/oracle/`
    - Full regression suite: `uv run pytest -q`
    - Linter clean: `uv run ruff check agent_fox/ tests/`
  - [x] 6.2 Documentation
    - Update README.md archetypes table to include oracle
    - Update docs/cli-reference.md if oracle adds CLI options
    - Create docs/adr/oracle-archetype.md documenting the design decision

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 32-REQ-1.1 | TS-32-1 | 2.3 | tests/unit/oracle/test_registry.py::test_oracle_registry_entry |
| 32-REQ-1.2 | TS-32-2 | 2.4 | tests/unit/oracle/test_registry.py::test_oracle_enabled_config |
| 32-REQ-1.3 | TS-32-1 | 2.3 | tests/unit/oracle/test_registry.py::test_oracle_registry_entry |
| 32-REQ-1.E1 | TS-32-E1 | 2.4 | tests/unit/oracle/test_registry.py::test_oracle_disabled |
| 32-REQ-2.1 | TS-32-3 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_oracle_node_injected |
| 32-REQ-2.2 | TS-32-4 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_dual_auto_pre |
| 32-REQ-2.3 | TS-32-3 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_oracle_node_injected |
| 32-REQ-2.E1 | TS-32-E2 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_empty_spec_no_oracle |
| 32-REQ-3.1 | TS-32-4 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_dual_auto_pre |
| 32-REQ-3.2 | TS-32-5 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_single_auto_pre_compat |
| 32-REQ-3.3 | TS-32-4 | 4.1 | tests/unit/oracle/test_graph_builder.py::test_dual_auto_pre |
| 32-REQ-3.E1 | TS-32-E3 | 4.2 | tests/unit/oracle/test_graph_builder.py::test_legacy_plan_compat |
| 32-REQ-4.1 | TS-32-13 | 4.3 | tests/integration/oracle/test_store.py::test_hot_load_oracle_injection |
| 32-REQ-4.2 | TS-32-13 | 4.3 | tests/integration/oracle/test_store.py::test_hot_load_oracle_injection |
| 32-REQ-4.E1 | TS-32-E9 | 4.3 | tests/unit/oracle/test_graph_builder.py::test_hot_load_failure_skip |
| 32-REQ-5.1 | TS-32-6 | 5.1 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-5.2 | TS-32-6 | 5.1 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-5.3 | TS-32-6 | 5.1 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-5.4 | TS-32-6 | 5.1 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-5.E1 | TS-32-E4 | 2.2 | tests/unit/oracle/test_parser.py::test_no_json_output |
| 32-REQ-5.E2 | TS-32-E5 | 2.2 | tests/unit/oracle/test_parser.py::test_missing_fields |
| 32-REQ-6.1 | TS-32-6 | 2.2 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-6.2 | TS-32-6 | 2.2 | tests/unit/oracle/test_parser.py::test_parse_valid_json |
| 32-REQ-6.3 | TS-32-7 | 2.1 | tests/unit/oracle/test_parser.py::test_drift_finding_fields |
| 32-REQ-6.E1 | TS-32-E4 | 2.2 | tests/unit/oracle/test_parser.py::test_no_json_output |
| 32-REQ-6.E2 | TS-32-E5 | 2.2 | tests/unit/oracle/test_parser.py::test_missing_fields |
| 32-REQ-7.1 | TS-32-8 | 3.2 | tests/integration/oracle/test_store.py::test_insert_query |
| 32-REQ-7.2 | TS-32-8 | 3.1 | tests/integration/oracle/test_store.py::test_insert_query |
| 32-REQ-7.3 | TS-32-9 | 3.2 | tests/integration/oracle/test_store.py::test_supersession |
| 32-REQ-7.4 | TS-32-8 | 3.3 | tests/integration/oracle/test_store.py::test_insert_query |
| 32-REQ-7.E1 | TS-32-E9 | 3.2 | tests/integration/oracle/test_store.py::test_db_unavailable |
| 32-REQ-8.1 | TS-32-10 | 5.2 | tests/unit/oracle/test_context.py::test_render_drift_context |
| 32-REQ-8.2 | TS-32-10 | 5.2 | tests/unit/oracle/test_context.py::test_render_drift_context |
| 32-REQ-8.E1 | TS-32-E6 | 5.2 | tests/unit/oracle/test_context.py::test_no_findings |
| 32-REQ-9.1 | TS-32-11 | 5.4 | tests/unit/oracle/test_blocking.py::test_block_threshold |
| 32-REQ-9.2 | TS-32-11 | 5.4 | tests/unit/oracle/test_blocking.py::test_block_threshold |
| 32-REQ-9.3 | TS-32-11 | 5.4 | tests/unit/oracle/test_blocking.py::test_block_threshold |
| 32-REQ-9.E1 | TS-32-E7 | 5.4 | tests/unit/oracle/test_blocking.py::test_advisory_mode |
| 32-REQ-10.1 | TS-32-12 | 2.4 | tests/unit/oracle/test_blocking.py::test_config_defaults |
| 32-REQ-10.2 | TS-32-12 | 2.4 | tests/unit/oracle/test_blocking.py::test_config_defaults |
| 32-REQ-10.3 | TS-32-12 | 2.4 | tests/unit/oracle/test_blocking.py::test_config_defaults |
| 32-REQ-10.4 | TS-32-12 | 2.4 | tests/unit/oracle/test_blocking.py::test_config_defaults |
| 32-REQ-10.E1 | TS-32-E8 | 2.4 | tests/unit/oracle/test_blocking.py::test_threshold_clamped |
| Property 1 | TS-32-P1 | 2.3 | tests/property/oracle/test_oracle_props.py::test_registry_completeness |
| Property 2 | TS-32-P2 | 4.1 | tests/property/oracle/test_oracle_props.py::test_multi_auto_pre |
| Property 3 | TS-32-P3 | 4.1 | tests/property/oracle/test_oracle_props.py::test_backward_compat |
| Property 4 | TS-32-P4 | 2.2 | tests/property/oracle/test_oracle_props.py::test_roundtrip |
| Property 5 | TS-32-P5 | 3.2, 3.3 | tests/property/oracle/test_oracle_props.py::test_supersession |
| Property 6 | TS-32-P6 | 5.4 | tests/property/oracle/test_oracle_props.py::test_block_threshold |
| Property 7 | TS-32-P7 | 5.2 | tests/property/oracle/test_oracle_props.py::test_render_completeness |
| Property 8 | TS-32-P8 | 4.3 | tests/property/oracle/test_oracle_props.py::test_hot_load_injection |

## Notes

- The oracle follows the same architectural patterns as the skeptic archetype. Reference the skeptic implementation as a guide.
- Multi-auto_pre support (Requirement 3) is the most complex piece. Test thoroughly with both single and dual auto_pre configurations.
- The DuckDB migration must be idempotent and should not modify existing tables.
- Property tests use Hypothesis; set `max_examples` appropriately to avoid slow CI runs.
- The oracle prompt template (`oracle.md`) is the only non-code artifact; its quality directly affects the oracle's effectiveness.
