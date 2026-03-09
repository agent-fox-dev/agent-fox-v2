# Implementation Plan: Agent Archetypes

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into two sequential phases:

- **Phase A** (groups 2-4): SDK abstraction layer. Low-risk mechanical
  refactor. Can be merged and validated independently.
- **Phase B** (groups 5-9): Archetype registry, graph builder injection,
  multi-instance convergence, Skeptic/Verifier behavior, retry-predecessor
  orchestrator logic.

Group 1 writes failing tests for both phases. Groups 2-3 implement Phase A.
Group 4 is a Phase A checkpoint. Groups 5-8 implement Phase B. Group 9 is a
Phase B checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/session/backends/ tests/unit/session/test_archetypes.py tests/unit/session/test_convergence.py tests/unit/session/test_skeptic.py tests/unit/session/test_verifier.py tests/unit/session/test_github_issues.py tests/unit/session/test_prompt_archetype.py tests/unit/graph/test_builder_archetypes.py tests/unit/core/test_config_archetypes.py tests/unit/engine/test_retry_predecessor.py -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/unit/ -q -k "property or hypothesis"`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create Phase A test files
    - Create `tests/unit/session/backends/test_protocol.py` with tests for TS-26-1 through TS-26-4 (protocol, messages, ResultMessage fields)
    - Create `tests/unit/session/backends/test_claude.py` with tests for TS-26-5 through TS-26-8 (ClaudeBackend adapter, SDK isolation)
    - Create `tests/unit/session/backends/__init__.py`
    - _Test Spec: TS-26-1 through TS-26-8, TS-26-E1, TS-26-E2_

  - [x] 1.2 Create archetype registry and config test files
    - Create `tests/unit/session/test_archetypes.py` with tests for TS-26-9 through TS-26-11 (registry completeness, coordinator, allowlist)
    - Create `tests/unit/core/test_config_archetypes.py` with tests for TS-26-22 through TS-26-26 (config toggles, instances, model/allowlist overrides, coder-always-enabled)
    - _Test Spec: TS-26-9 through TS-26-11, TS-26-22 through TS-26-26, TS-26-E3, TS-26-E4, TS-26-E9_

  - [x] 1.3 Create graph builder and parser test files
    - Create `tests/unit/graph/test_builder_archetypes.py` with tests for TS-26-13 through TS-26-15 (Node fields, serialization, legacy defaults), TS-26-17 through TS-26-21 (tag parsing, priority, injection, logging)
    - _Test Spec: TS-26-13 through TS-26-21, TS-26-E5 through TS-26-E8_

  - [x] 1.4 Create convergence, Skeptic, Verifier, and prompt test files
    - Create `tests/unit/session/test_convergence.py` with tests for TS-26-27 through TS-26-31 (multi-instance, dedup, majority gate, majority vote, no-LLM)
    - Create `tests/unit/session/test_skeptic.py` with tests for TS-26-32 through TS-26-36 (review.md, GitHub issue, context handoff, blocking, allowlist)
    - Create `tests/unit/session/test_verifier.py` with tests for TS-26-37, TS-26-38 (verification.md, GitHub issue on FAIL)
    - Create `tests/unit/session/test_prompt_archetype.py` with test for TS-26-42 (coder equivalence), TS-26-12 (registry-based resolution), TS-26-16 (NodeSessionRunner archetype)
    - _Test Spec: TS-26-12, TS-26-16, TS-26-27 through TS-26-38, TS-26-42, TS-26-E10, TS-26-E11_

  - [x] 1.5 Create retry-predecessor and GitHub issue test files
    - Create `tests/unit/engine/test_retry_predecessor.py` with tests for TS-26-39 through TS-26-40 (predecessor reset, cycle limit)
    - Create `tests/unit/session/test_github_issues.py` with tests for TS-26-41 (search-before-create)
    - _Test Spec: TS-26-39 through TS-26-41, TS-26-E12, TS-26-E13_

  - [x] 1.6 Create property test cases
    - Add property tests TS-26-P1 through TS-26-P14 to the appropriate test files (P1 in test_protocol.py, P2 in test_claude.py, P3-P4 in test_archetypes.py, P5-P6 in test_prompt_archetype.py, P7-P8 in test_builder_archetypes.py, P9-P11 in test_convergence.py, P12 in test_retry_predecessor.py, P13 in test_github_issues.py, P14 in test_builder_archetypes.py)
    - Use `hypothesis` strategies where specified
    - _Test Spec: TS-26-P1 through TS-26-P14_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Phase A: AgentBackend protocol and ClaudeBackend adapter
  - [x] 2.1 Create canonical message types and protocol
    - Create `agent_fox/session/backends/__init__.py`
    - Create `agent_fox/session/backends/protocol.py` with `ToolUseMessage`, `AssistantMessage`, `ResultMessage` frozen dataclasses and `AgentMessage` type alias
    - Define `PermissionCallback` type alias
    - Define `AgentBackend` as `@runtime_checkable` `typing.Protocol` with `name` property, `execute()`, and `close()`
    - _Requirements: 26-REQ-1.1, 26-REQ-1.2, 26-REQ-1.3, 26-REQ-1.4_

  - [x] 2.2 Implement ClaudeBackend adapter
    - Create `agent_fox/session/backends/claude.py`
    - Move all `claude_code_sdk` imports into this module
    - Implement `ClaudeBackend.execute()`: construct `ClaudeCodeOptions`, open `ClaudeSDKClient`, map SDK messages to canonical types, yield them
    - Implement `ClaudeBackend.close()`
    - Map SDK `PermissionResultAllow`/`PermissionResultDeny` via the permission callback
    - Handle SDK streaming errors: yield `ResultMessage(is_error=True)` on exception
    - _Requirements: 26-REQ-2.1, 26-REQ-2.2, 26-REQ-2.3, 26-REQ-2.E1_

  - [x] 2.3 Create backend registry and factory
    - In `agent_fox/session/backends/__init__.py`, define `BACKEND_REGISTRY` mapping `"claude"` to `ClaudeBackend`
    - Implement `get_backend(name: str) -> AgentBackend` factory
    - Export protocol types and factory from the package
    - _Requirements: 26-REQ-2.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/session/backends/test_protocol.py tests/unit/session/backends/test_claude.py -q`
    - [x] TS-26-1 through TS-26-7 pass
    - [x] TS-26-E1, TS-26-E2 pass
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/session/backends/`

- [x] 3. Phase A: Session runner refactor
  - [x] 3.1 Refactor session.py to use AgentBackend protocol
    - Remove all `claude_code_sdk` imports from `session.py`
    - Accept `AgentBackend` instance as a parameter (or resolve via factory)
    - Replace `_query_messages()` with iteration over `backend.execute()`
    - Replace direct `ClaudeCodeOptions` construction with protocol calls
    - Map `_extract_activity()` to use canonical message types
    - Preserve all existing behavior: timeout, token tracking, error handling
    - _Requirements: 26-REQ-2.4_

  - [x] 3.2 Update session_lifecycle.py to provide backend
    - Modify `NodeSessionRunner` to instantiate or receive an `AgentBackend`
    - Pass the backend to `run_session()`
    - Ensure allowlist hook is passed via `permission_callback`
    - _Requirements: 26-REQ-2.4_

  - [x] 3.3 Verify SDK import isolation
    - Confirm no module outside `backends/claude.py` imports `claude_code_sdk`
    - Update any test mocks that were mocking SDK types directly
    - _Requirements: 26-REQ-2.4_

  - [x] 3.V Verify task group 3
    - [x] TS-26-8 passes (no claude_code_sdk imports in session.py)
    - [x] TS-26-P1 passes (protocol isolation property)
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/`

- [x] 4. Checkpoint — Phase A Complete
  - Verify all Phase A tests pass (TS-26-1 through TS-26-8, TS-26-E1, TS-26-E2, TS-26-P1, TS-26-P2)
  - Run full test suite: `uv run pytest -q`
  - Run linter: `uv run ruff check agent_fox/ tests/`
  - Confirm behavioral equivalence: existing orchestrator runs produce identical results
  - Ask the user if questions arise

- [ ] 5. Phase B: Archetype registry and configuration
  - [ ] 5.1 Create ArchetypesConfig pydantic model
    - Add `ArchetypeInstancesConfig`, `SkepticConfig`, `ArchetypesConfig` to `core/config.py`
    - Add `archetypes: ArchetypesConfig` field to `AgentFoxConfig`
    - Implement `coder_always_enabled` validator
    - Implement instance count clamping (1-5)
    - _Requirements: 26-REQ-6.1, 26-REQ-6.2, 26-REQ-6.3, 26-REQ-6.4, 26-REQ-6.5, 26-REQ-6.E1_

  - [ ] 5.2 Create archetype registry
    - Create `agent_fox/session/archetypes.py`
    - Define `ArchetypeEntry` frozen dataclass
    - Define `ARCHETYPE_REGISTRY` with all six entries (coder, skeptic, verifier, librarian, cartographer, coordinator)
    - Implement `get_archetype(name)` with coder fallback and warning
    - _Requirements: 26-REQ-3.1, 26-REQ-3.2, 26-REQ-3.3, 26-REQ-3.E1_

  - [ ] 5.3 Extend Node dataclass
    - Add `archetype: str = "coder"` and `instances: int = 1` fields to `Node` in `graph/types.py`
    - Update `_node_from_dict()` in `persistence.py` with `.get()` defaults for backward compatibility
    - Verify `_serialize()` includes new fields (handled automatically by `dataclasses.asdict`)
    - _Requirements: 26-REQ-4.1, 26-REQ-4.2, 26-REQ-4.3_

  - [ ] 5.4 Extend TaskGroupDef with archetype field
    - Add `archetype: str | None = None` field to `TaskGroupDef` in `spec/parser.py`
    - Add `[archetype: X]` tag extraction regex to `parse_tasks()`
    - Strip the tag from the stored `title` field
    - Log warning for unknown archetype names
    - _Requirements: 26-REQ-5.1, 26-REQ-5.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/unit/core/test_config_archetypes.py tests/unit/session/test_archetypes.py -q`
    - [ ] TS-26-9 through TS-26-11, TS-26-13 through TS-26-15, TS-26-17, TS-26-22 through TS-26-26 pass
    - [ ] TS-26-E3 through TS-26-E6, TS-26-E8, TS-26-E9 pass
    - [ ] TS-26-P3, TS-26-P4, TS-26-P8, TS-26-P14 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 6. Phase B: Graph builder injection and prompt refactor
  - [ ] 6.1 Implement auto-injection in graph builder
    - Add `archetypes_config` and `coordinator_overrides` parameters to `build_graph()`
    - Implement `auto_pre` injection: insert group-0 Skeptic node with intra-spec edge to first real group
    - Implement `auto_post` injection: insert sibling nodes after last Coder group for each enabled `auto_post` archetype
    - Set `instances` on injected nodes from `archetypes_config.instances`
    - _Requirements: 26-REQ-5.3, 26-REQ-5.4_

  - [ ] 6.2 Implement three-layer assignment priority
    - Apply coordinator overrides to node archetypes (layer 2)
    - Apply `tasks.md` tag overrides as final precedence (layer 3 — highest priority)
    - Skip overrides for disabled archetypes with warning
    - Log final archetype assignment for each node at INFO level
    - _Requirements: 26-REQ-5.2, 26-REQ-5.5, 26-REQ-5.E1_

  - [ ] 6.3 Refactor build_system_prompt to use registry
    - Delete `_ROLE_TEMPLATES` dict from `prompt.py`
    - Change `build_system_prompt()` parameter from `role` to `archetype`
    - Look up template files via `get_archetype(archetype).templates`
    - Maintain backward compatibility: `archetype="coder"` produces identical output to old `role="coding"`
    - _Requirements: 26-REQ-3.5_

  - [ ] 6.4 Update callers of build_system_prompt
    - Update `NodeSessionRunner._build_prompts()` to pass `archetype` instead of `role`
    - Update any other callers (coordinator planning code) to use `archetype="coordinator"`
    - _Requirements: 26-REQ-3.5_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests pass: `uv run pytest tests/unit/graph/test_builder_archetypes.py tests/unit/session/test_prompt_archetype.py -q`
    - [ ] TS-26-12, TS-26-18 through TS-26-21, TS-26-42 pass
    - [ ] TS-26-E7 passes
    - [ ] TS-26-P5, TS-26-P6, TS-26-P7 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 7. Phase B: Archetype-aware session execution
  - [ ] 7.1 Update NodeSessionRunner for archetype resolution
    - Accept `archetype` and `instances` parameters in `__init__()`
    - Resolve model tier: check `config.archetypes.models.get(archetype)`, fall back to `entry.default_model_tier`
    - Resolve allowlist: check `config.archetypes.allowlists.get(archetype)`, fall back to `entry.default_allowlist`, fall back to global
    - Pass resolved model and allowlist to `run_session()`
    - _Requirements: 26-REQ-4.4, 26-REQ-3.4_

  - [ ] 7.2 Implement multi-instance dispatch
    - In `NodeSessionRunner.execute()`, dispatch N instances in parallel when `instances > 1`
    - Each instance uses the same prompts, model, and allowlist
    - Collect results with `asyncio.gather(*coros, return_exceptions=True)`
    - Clamp coder instances to 1 with warning; clamp all > 5 to 5
    - _Requirements: 26-REQ-7.1, 26-REQ-4.E1, 26-REQ-4.E2_

  - [ ] 7.3 Implement convergence logic
    - Create `agent_fox/session/convergence.py`
    - Implement `Finding` dataclass and `normalize_finding()` helper
    - Implement `converge_skeptic()`: union, normalize-dedup, majority-gate criticals, apply blocking threshold
    - Implement `converge_verifier()`: majority vote on verdicts
    - Handle partial failures: converge with successful subset; all-fail returns None
    - _Requirements: 26-REQ-7.2, 26-REQ-7.3, 26-REQ-7.4, 26-REQ-7.5, 26-REQ-7.E1_

  - [ ] 7.4 Wire convergence into NodeSessionRunner
    - After multi-instance gather, call appropriate convergence function based on archetype
    - Use converged result for the session record (merged findings, final verdict)
    - Apply Skeptic blocking threshold from config
    - _Requirements: 26-REQ-8.4_

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests pass: `uv run pytest tests/unit/session/test_convergence.py tests/unit/session/test_prompt_archetype.py -q -k "archetype or convergence or instance"`
    - [ ] TS-26-16, TS-26-27 through TS-26-31, TS-26-35 pass
    - [ ] TS-26-E5, TS-26-E6, TS-26-E10 pass
    - [ ] TS-26-P9, TS-26-P10, TS-26-P11 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 8. Phase B: Skeptic/Verifier behavior and orchestrator logic
  - [ ] 8.1 Create Skeptic and Verifier prompt templates
    - Create `agent_fox/_templates/prompts/skeptic.md` with structured review instructions (severity categories, review.md output path)
    - Create `agent_fox/_templates/prompts/verifier.md` with verification instructions (per-requirement assessment, verification.md output, PASS/FAIL verdict)
    - Create `agent_fox/_templates/prompts/librarian.md` with documentation instructions
    - Create `agent_fox/_templates/prompts/cartographer.md` with architecture mapping instructions
    - _Requirements: 26-REQ-8.1, 26-REQ-9.1_

  - [ ] 8.2 Implement GitHub issue filing
    - Create `agent_fox/session/github_issues.py`
    - Implement `file_or_update_issue()` with search-before-create via `gh` CLI subprocess
    - Handle update (edit body + add comment) when existing issue found
    - Handle close when `close_if_empty=True` and no findings
    - All `gh` failures are logged and swallowed (never block execution)
    - _Requirements: 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, 26-REQ-10.E1_

  - [ ] 8.3 Implement Skeptic post-session logic
    - After Skeptic convergence, call `file_or_update_issue()` with title `[Skeptic Review] {spec_name}`
    - If zero critical findings and existing issue, close it
    - Write merged review to `.specs/{spec_name}/review.md` in the worktree
    - Ensure review.md content is included in successor Coder's system prompt via `assemble_context()` enhancement
    - _Requirements: 26-REQ-8.2, 26-REQ-8.3, 26-REQ-8.E1_

  - [ ] 8.4 Implement Verifier post-session logic
    - After Verifier convergence, if verdict is FAIL: call `file_or_update_issue()` with title `[Verifier] {spec_name} group {N}: FAIL`
    - Write verification report to `.specs/{spec_name}/verification.md`
    - _Requirements: 26-REQ-9.2_

  - [ ] 8.5 Implement retry-predecessor in orchestrator
    - In `Orchestrator._process_session_result()`, after a failed node: check `get_archetype(archetype).retry_predecessor`
    - If true and within retry budget: reset predecessor to `pending`, set predecessor's `previous_error` to the failure report, reset the failed node to `pending`
    - If retry budget exhausted: block the node per normal rules
    - Pass archetype metadata from plan nodes to the session runner factory
    - _Requirements: 26-REQ-9.3, 26-REQ-9.4, 26-REQ-9.E1_

  - [ ] 8.V Verify task group 8
    - [ ] Spec tests pass: `uv run pytest tests/unit/session/test_skeptic.py tests/unit/session/test_verifier.py tests/unit/session/test_github_issues.py tests/unit/engine/test_retry_predecessor.py -q`
    - [ ] TS-26-32 through TS-26-41 pass
    - [ ] TS-26-E7, TS-26-E11 through TS-26-E13 pass
    - [ ] TS-26-P12, TS-26-P13 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 9. Checkpoint — Phase B Complete
  - Verify all spec tests pass: full spec test command from top of document
  - Verify all property tests pass: `uv run pytest -q -k "property or hypothesis"`
  - Run full test suite: `uv run pytest -q`
  - Run linter: `uv run ruff check agent_fox/ tests/`
  - Update documentation: README, CLAUDE.md if archetype config sections are relevant
  - Create ADR `docs/adr/agent_archetypes.md` documenting key design decisions
  - Ask the user if questions arise

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
| 26-REQ-1.1 | TS-26-1 | 2.1 | `tests/unit/session/backends/test_protocol.py::test_protocol_runtime_checkable` |
| 26-REQ-1.2 | TS-26-2 | 2.1 | `tests/unit/session/backends/test_protocol.py::test_execute_parameters` |
| 26-REQ-1.3 | TS-26-3 | 2.1 | `tests/unit/session/backends/test_protocol.py::test_canonical_messages_frozen` |
| 26-REQ-1.4 | TS-26-4 | 2.1 | `tests/unit/session/backends/test_protocol.py::test_result_message_fields` |
| 26-REQ-1.E1 | TS-26-E1 | 2.2, 3.1 | `tests/unit/session/backends/test_protocol.py::test_backend_exception_handling` |
| 26-REQ-2.1 | TS-26-5 | 2.2 | `tests/unit/session/backends/test_claude.py::test_claude_backend_conforms` |
| 26-REQ-2.2 | TS-26-6 | 2.2 | `tests/unit/session/backends/test_claude.py::test_sdk_type_mapping` |
| 26-REQ-2.3 | TS-26-7 | 2.2 | `tests/unit/session/backends/test_claude.py::test_execute_constructs_options` |
| 26-REQ-2.4 | TS-26-8 | 3.1, 3.2, 3.3 | `tests/unit/session/backends/test_claude.py::test_session_no_sdk_imports` |
| 26-REQ-2.E1 | TS-26-E2 | 2.2 | `tests/unit/session/backends/test_claude.py::test_streaming_error_yields_result` |
| 26-REQ-3.1 | TS-26-9 | 5.2 | `tests/unit/session/test_archetypes.py::test_registry_completeness` |
| 26-REQ-3.2 | TS-26-9 | 5.2 | `tests/unit/session/test_archetypes.py::test_registry_completeness` |
| 26-REQ-3.3 | TS-26-10 | 5.2 | `tests/unit/session/test_archetypes.py::test_coordinator_not_assignable` |
| 26-REQ-3.4 | TS-26-11 | 7.1 | `tests/unit/session/test_archetypes.py::test_per_archetype_allowlist` |
| 26-REQ-3.5 | TS-26-12, TS-26-42 | 6.3, 6.4 | `tests/unit/session/test_prompt_archetype.py::test_registry_based_resolution` |
| 26-REQ-3.E1 | TS-26-E3 | 5.2 | `tests/unit/session/test_archetypes.py::test_unknown_archetype_fallback` |
| 26-REQ-3.E2 | TS-26-E4 | 6.3 | `tests/unit/session/test_prompt_archetype.py::test_missing_template_raises` |
| 26-REQ-4.1 | TS-26-13 | 5.3 | `tests/unit/graph/test_builder_archetypes.py::test_node_archetype_defaults` |
| 26-REQ-4.2 | TS-26-14 | 5.3 | `tests/unit/graph/test_builder_archetypes.py::test_plan_serialization_archetype` |
| 26-REQ-4.3 | TS-26-15 | 5.3 | `tests/unit/graph/test_builder_archetypes.py::test_legacy_plan_defaults` |
| 26-REQ-4.4 | TS-26-16 | 7.1 | `tests/unit/session/test_prompt_archetype.py::test_runner_uses_archetype` |
| 26-REQ-4.E1 | TS-26-E5 | 7.2 | `tests/unit/graph/test_builder_archetypes.py::test_coder_instances_clamped` |
| 26-REQ-4.E2 | TS-26-E6 | 7.2 | `tests/unit/graph/test_builder_archetypes.py::test_instances_over_5_clamped` |
| 26-REQ-5.1 | TS-26-17 | 5.4 | `tests/unit/graph/test_builder_archetypes.py::test_archetype_tag_extraction` |
| 26-REQ-5.2 | TS-26-18 | 6.2 | `tests/unit/graph/test_builder_archetypes.py::test_three_layer_priority` |
| 26-REQ-5.3 | TS-26-19 | 6.1 | `tests/unit/graph/test_builder_archetypes.py::test_skeptic_auto_injection` |
| 26-REQ-5.4 | TS-26-20 | 6.1 | `tests/unit/graph/test_builder_archetypes.py::test_auto_post_siblings` |
| 26-REQ-5.5 | TS-26-21 | 6.2 | `tests/unit/graph/test_builder_archetypes.py::test_assignment_logged` |
| 26-REQ-5.E1 | TS-26-E7 | 6.2 | `tests/unit/graph/test_builder_archetypes.py::test_disabled_archetype_override_ignored` |
| 26-REQ-5.E2 | TS-26-E8 | 5.4 | `tests/unit/graph/test_builder_archetypes.py::test_unknown_tag_defaults_coder` |
| 26-REQ-6.1 | TS-26-22 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_archetype_toggles` |
| 26-REQ-6.2 | TS-26-23 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_instance_counts` |
| 26-REQ-6.3 | TS-26-24 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_model_tier_override` |
| 26-REQ-6.4 | TS-26-25 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_allowlist_override` |
| 26-REQ-6.5 | TS-26-26 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_coder_always_enabled` |
| 26-REQ-6.E1 | TS-26-E9 | 5.1 | `tests/unit/core/test_config_archetypes.py::test_missing_archetypes_section` |
| 26-REQ-7.1 | TS-26-27 | 7.2 | `tests/unit/session/test_convergence.py::test_multi_instance_dispatch` |
| 26-REQ-7.2 | TS-26-28 | 7.3 | `tests/unit/session/test_convergence.py::test_skeptic_union_dedup` |
| 26-REQ-7.3 | TS-26-29 | 7.3 | `tests/unit/session/test_convergence.py::test_skeptic_majority_gating` |
| 26-REQ-7.4 | TS-26-30 | 7.3 | `tests/unit/session/test_convergence.py::test_verifier_majority_vote` |
| 26-REQ-7.5 | TS-26-31 | 7.3 | `tests/unit/session/test_convergence.py::test_convergence_no_llm` |
| 26-REQ-7.E1 | TS-26-E10 | 7.3 | `tests/unit/session/test_convergence.py::test_partial_instance_failure` |
| 26-REQ-8.1 | TS-26-32 | 8.1 | `tests/unit/session/test_skeptic.py::test_skeptic_template` |
| 26-REQ-8.2 | TS-26-33 | 8.3 | `tests/unit/session/test_skeptic.py::test_skeptic_github_issue` |
| 26-REQ-8.3 | TS-26-34 | 8.3 | `tests/unit/session/test_skeptic.py::test_review_passed_to_coder` |
| 26-REQ-8.4 | TS-26-35 | 7.4 | `tests/unit/session/test_skeptic.py::test_blocking_threshold` |
| 26-REQ-8.5 | TS-26-36 | 5.2 | `tests/unit/session/test_skeptic.py::test_readonly_allowlist` |
| 26-REQ-8.E1 | TS-26-E11 | 8.3 | `tests/unit/session/test_skeptic.py::test_close_issue_no_findings` |
| 26-REQ-9.1 | TS-26-37 | 8.1 | `tests/unit/session/test_verifier.py::test_verifier_template` |
| 26-REQ-9.2 | TS-26-38 | 8.4 | `tests/unit/session/test_verifier.py::test_verifier_github_issue` |
| 26-REQ-9.3 | TS-26-39 | 8.5 | `tests/unit/engine/test_retry_predecessor.py::test_predecessor_reset` |
| 26-REQ-9.4 | TS-26-40 | 8.5 | `tests/unit/engine/test_retry_predecessor.py::test_retry_cycle_limit` |
| 26-REQ-9.E1 | TS-26-E12 | 8.5 | `tests/unit/engine/test_retry_predecessor.py::test_non_coder_predecessor` |
| 26-REQ-10.1 | TS-26-41 | 8.2 | `tests/unit/session/test_github_issues.py::test_search_before_create` |
| 26-REQ-10.2 | TS-26-41 | 8.2 | `tests/unit/session/test_github_issues.py::test_search_before_create` |
| 26-REQ-10.3 | TS-26-41 | 8.2 | `tests/unit/session/test_github_issues.py::test_search_before_create` |
| 26-REQ-10.E1 | TS-26-E13 | 8.2 | `tests/unit/session/test_github_issues.py::test_gh_unavailable` |
| Property 1 | TS-26-P1 | 3.3 | `tests/unit/session/backends/test_protocol.py::test_prop_protocol_isolation` |
| Property 2 | TS-26-P2 | 2.2 | `tests/unit/session/backends/test_claude.py::test_prop_message_completeness` |
| Property 3 | TS-26-P3 | 5.2 | `tests/unit/session/test_archetypes.py::test_prop_registry_completeness` |
| Property 4 | TS-26-P4 | 5.2 | `tests/unit/session/test_archetypes.py::test_prop_archetype_fallback` |
| Property 5 | TS-26-P5 | 6.3 | `tests/unit/session/test_prompt_archetype.py::test_prop_template_equivalence` |
| Property 6 | TS-26-P6 | 6.2 | `tests/unit/session/test_prompt_archetype.py::test_prop_assignment_priority` |
| Property 7 | TS-26-P7 | 6.1 | `tests/unit/graph/test_builder_archetypes.py::test_prop_injection_structure` |
| Property 8 | TS-26-P8 | 7.2 | `tests/unit/graph/test_builder_archetypes.py::test_prop_instance_clamping` |
| Property 9 | TS-26-P9 | 7.3 | `tests/unit/session/test_convergence.py::test_prop_convergence_determinism` |
| Property 10 | TS-26-P10 | 7.3 | `tests/unit/session/test_convergence.py::test_prop_blocking_threshold` |
| Property 11 | TS-26-P11 | 7.3 | `tests/unit/session/test_convergence.py::test_prop_majority_vote` |
| Property 12 | TS-26-P12 | 8.5 | `tests/unit/engine/test_retry_predecessor.py::test_prop_retry_predecessor` |
| Property 13 | TS-26-P13 | 8.2 | `tests/unit/session/test_github_issues.py::test_prop_issue_idempotency` |
| Property 14 | TS-26-P14 | 5.3 | `tests/unit/graph/test_builder_archetypes.py::test_prop_backward_compat` |

## Notes

- **Phase A can be merged independently.** After group 4 checkpoint, Phase A
  delivers value (testability, vendor resilience) even if Phase B is delayed.
- **Phase B defaults to no-op.** All archetypes except Coder are disabled by
  default. Existing behavior is preserved unless the user opts in via config.
- **Template files** (skeptic.md, verifier.md, librarian.md, cartographer.md)
  are created in group 8.1 but their exact content is refined iteratively.
  The test spec validates structural requirements (severity categories,
  output paths) not prose quality.
- **Property tests** use `hypothesis` for randomized input generation.
  Ensure `hypothesis` is in dev dependencies.
- **GitHub issue tests** mock `subprocess` calls to `gh` CLI. No real GitHub
  API calls in tests.
- **Retry-predecessor** is the highest-risk new feature. Group 8.5 should be
  reviewed carefully for edge cases around cycle counting and state consistency.
