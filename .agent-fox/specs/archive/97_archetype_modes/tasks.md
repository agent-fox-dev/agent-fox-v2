# Implementation Plan: Archetype Model v3 — Mode Infrastructure

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan adds mode support to the archetype system in six task groups. Group 1
writes failing tests. Groups 2-4 implement the core data model, config, and
resolution logic. Group 5 wires mode through the session lifecycle. Group 6
verifies end-to-end wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/core/test_archetype_modes.py tests/unit/engine/test_sdk_params_modes.py tests/property/test_mode_properties.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file `tests/unit/core/test_archetype_modes.py`
    - Unit tests for ModeConfig defaults (TS-97-1)
    - Unit tests for ArchetypeEntry.modes field (TS-97-2)
    - Unit tests for resolve_effective_config with valid mode (TS-97-3)
    - Unit tests for resolve_effective_config with None mode (TS-97-4)
    - Edge case tests for unknown mode fallback (TS-97-E1)
    - Edge case tests for empty modes dict (TS-97-E2)
    - _Test Spec: TS-97-1 through TS-97-4, TS-97-E1, TS-97-E2_

  - [x] 1.2 Create test file `tests/unit/graph/test_node_mode.py`
    - Unit tests for Node.mode field (TS-97-5)
    - Unit tests for Node serialization round-trip (TS-97-6)
    - Edge case tests for Node with None mode (TS-97-E3)
    - _Test Spec: TS-97-5, TS-97-6, TS-97-E3_

  - [x] 1.3 Create test file `tests/unit/core/test_config_modes.py`
    - Unit tests for PerArchetypeConfig.modes field (TS-97-7)
    - Unit tests for TOML parsing with mode sections (TS-97-8)
    - Edge case tests for missing mode config fallback (TS-97-E4)
    - _Test Spec: TS-97-7, TS-97-8, TS-97-E4_

  - [x] 1.4 Create test file `tests/unit/engine/test_sdk_params_modes.py`
    - Unit tests for resolve_model_tier with mode (TS-97-9, TS-97-10)
    - Unit tests for resolve_security_config with empty allowlist mode (TS-97-11)
    - Unit tests for security hook blocking with empty allowlist (TS-97-12)
    - Unit tests for NodeSessionRunner mode parameter (TS-97-13)
    - Edge case tests for None mode identity (TS-97-E5)
    - Edge case tests for mode allowlist inheritance (TS-97-E6)
    - _Test Spec: TS-97-9 through TS-97-13, TS-97-E5, TS-97-E6_

  - [x] 1.5 Create test file `tests/property/test_mode_properties.py`
    - Property tests: override semantics (TS-97-P1)
    - Property tests: inheritance semantics (TS-97-P2)
    - Property tests: null mode identity (TS-97-P3)
    - Property tests: resolution priority chain (TS-97-P4)
    - Property tests: empty allowlist blocks all (TS-97-P5)
    - Property tests: serialization round-trip (TS-97-P6)
    - _Test Spec: TS-97-P1 through TS-97-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement ModeConfig and ArchetypeEntry.modes
  - [x] 2.1 Add ModeConfig dataclass to `agent_fox/archetypes.py`
    - Frozen dataclass with 8 optional override fields (all default None)
    - _Requirements: 97-REQ-1.1_

  - [x] 2.2 Add `modes` field to ArchetypeEntry
    - Type: `dict[str, ModeConfig]`, default: `field(default_factory=dict)`
    - _Requirements: 97-REQ-1.2_

  - [x] 2.3 Implement `resolve_effective_config()` function
    - Accept ArchetypeEntry and optional mode name
    - Merge non-None ModeConfig fields onto base, return new ArchetypeEntry
    - Log warning for unknown mode names, return base unchanged
    - _Requirements: 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5, 97-REQ-1.E1, 97-REQ-1.E2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/core/test_archetype_modes.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_mode_properties.py -k "override or inherit or null_mode"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/archetypes.py`

- [x] 3. Add Node.mode and config schema
  - [x] 3.1 Add `mode` field to Node dataclass
    - Type: `str | None`, default: `None`
    - Ensure serialization/deserialization handles mode field
    - _Requirements: 97-REQ-2.1, 97-REQ-2.2, 97-REQ-2.3, 97-REQ-2.E1_

  - [x] 3.2 Add `modes` field to PerArchetypeConfig
    - Type: `dict[str, PerArchetypeConfig]`, default: empty dict
    - Self-referential Pydantic model for nested mode overrides
    - _Requirements: 97-REQ-3.1, 97-REQ-3.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/graph/test_node_mode.py tests/unit/core/test_config_modes.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_mode_properties.py -k "round_trip"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/graph/types.py agent_fox/core/config.py`

- [x] 4. Update SDK resolution and security for modes
  - [x] 4.1 Add `mode` parameter to `resolve_model_tier()`
    - Add `*, mode: str | None = None` keyword argument
    - Implement 4-tier priority resolution (config mode > config arch > registry mode > registry base)
    - _Requirements: 97-REQ-4.1, 97-REQ-3.3_

  - [x] 4.2 Add `mode` parameter to `resolve_max_turns()` and `resolve_thinking()`
    - Same 4-tier priority pattern
    - _Requirements: 97-REQ-4.2, 97-REQ-4.3_

  - [x] 4.3 Add `mode` parameter to `resolve_security_config()`
    - Same 4-tier priority pattern
    - Empty allowlist produces SecurityConfig(bash_allowlist=[])
    - _Requirements: 97-REQ-4.4, 97-REQ-5.1, 97-REQ-5.2, 97-REQ-5.E1_

  - [x] 4.4 Update `clamp_instances()` to accept mode parameter
    - Coder always clamped to 1 regardless of mode
    - _Requirements: 97-REQ-4.5_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest -q tests/unit/engine/test_sdk_params_modes.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_mode_properties.py -k "priority or allowlist"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/sdk_params.py agent_fox/hooks/security.py`
    - [x] Requirements 97-REQ-4.1 through 97-REQ-5.E1 met

- [x] 5. Wire mode through session lifecycle
  - [x] 5.1 Add `mode` parameter to `NodeSessionRunner.__init__()`
    - Store as `self._mode`
    - Pass to `resolve_model_tier()`, `resolve_security_config()` in init
    - Pass to `resolve_max_turns()`, `resolve_thinking()` where called
    - _Requirements: 97-REQ-5.3_

  - [x] 5.2 Update engine dispatch to pass `node.mode` to NodeSessionRunner
    - Where the engine creates NodeSessionRunner from a Node, pass `mode=node.mode`
    - _Requirements: 97-REQ-5.3_

  - [x] 5.3 Update `build_system_prompt()` and `build_task_prompt()` to accept mode
    - Thread mode parameter for future template resolution (profiles spec)
    - _Requirements: 97-REQ-5.3_

  - [x] 5.V Verify task group 5
    - [x] Smoke tests pass: `uv run pytest -q tests/unit/engine/test_sdk_params_modes.py -k "smoke or session"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/ agent_fox/session/`

- [x] 6. Wiring verification

  - [x] 6.1 Trace every execution path from design.md end-to-end
    - Path 1: Node(mode) → NodeSessionRunner → resolve_model_tier(mode) → resolve_effective_config(mode)
    - Path 2: Node(mode) → NodeSessionRunner → resolve_security_config(mode) → make_pre_tool_use_hook → block/allow
    - Path 3: Node(mode) → resolve_max_turns(mode) → config mode lookup → registry mode lookup
    - Path 4: Node(mode) → serialize → deserialize → Node(mode) preserved
    - Confirm no function in the chain is a stub
    - _Requirements: all_

  - [x] 6.2 Verify return values propagate correctly
    - resolve_effective_config returns ArchetypeEntry consumed by SDK functions
    - resolve_security_config returns SecurityConfig consumed by make_pre_tool_use_hook
    - Grep for callers; confirm none discards the return value
    - Fixed critical bug: session_runner_factory in run.py was not forwarding mode
      to NodeSessionRunner — added mode parameter to factory signature and call.
    - _Requirements: all_

  - [x] 6.3 Run the integration smoke tests
    - TS-97-SMOKE-1: End-to-end mode resolution
    - TS-97-SMOKE-2: Security hook with mode
    - TS-97-SMOKE-3: Graph serialization with mode
    - _Test Spec: TS-97-SMOKE-1 through TS-97-SMOKE-3_

  - [x] 6.4 Stub / dead-code audit
    - Search touched files for `return []`, `return None` on non-Optional returns,
      `pass` in non-abstract methods, `# TODO`, `NotImplementedError`
    - All hits are justified: empty-list returns for missing tasks/specs,
      exception-swallowing pass in signal handlers, None returns for Optional fields.
    - _Requirements: all_

  - [x] 6.5 Cross-spec entry point verification
    - This spec has no upstream callers yet (mode injection comes in spec 98)
    - Verify all new public functions are importable and have correct signatures
    - All functions verified importable with mode parameter: resolve_model_tier,
      resolve_max_turns, resolve_thinking, resolve_security_config, clamp_instances,
      NodeSessionRunner, Node, PerArchetypeConfig, ArchetypeEntry.
    - _Requirements: all_

  - [x] 6.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 97-REQ-1.1 | TS-97-1 | 2.1 | test_archetype_modes.py::test_mode_config_defaults |
| 97-REQ-1.2 | TS-97-2 | 2.2 | test_archetype_modes.py::test_archetype_entry_modes_field |
| 97-REQ-1.3 | TS-97-3 | 2.3 | test_archetype_modes.py::test_resolve_effective_config_valid |
| 97-REQ-1.4 | TS-97-4 | 2.3 | test_archetype_modes.py::test_resolve_effective_config_none |
| 97-REQ-1.5 | TS-97-3 | 2.3 | test_archetype_modes.py::test_resolve_effective_config_valid |
| 97-REQ-1.E1 | TS-97-E1 | 2.3 | test_archetype_modes.py::test_unknown_mode_fallback |
| 97-REQ-1.E2 | TS-97-E2 | 2.3 | test_archetype_modes.py::test_empty_modes_dict |
| 97-REQ-2.1 | TS-97-5 | 3.1 | test_node_mode.py::test_node_mode_field |
| 97-REQ-2.2 | TS-97-6 | 3.1 | test_node_mode.py::test_node_serialization_roundtrip |
| 97-REQ-2.3 | TS-97-5 | 3.1 | test_node_mode.py::test_node_mode_repr |
| 97-REQ-2.E1 | TS-97-E3 | 3.1 | test_node_mode.py::test_node_none_mode |
| 97-REQ-3.1 | TS-97-7 | 3.2 | test_config_modes.py::test_per_archetype_modes_field |
| 97-REQ-3.2 | TS-97-8 | 3.2 | test_config_modes.py::test_toml_mode_parsing |
| 97-REQ-3.3 | TS-97-10 | 4.1 | test_sdk_params_modes.py::test_mode_fallback |
| 97-REQ-3.E1 | TS-97-E4 | 4.1 | test_sdk_params_modes.py::test_missing_mode_config |
| 97-REQ-4.1 | TS-97-9 | 4.1 | test_sdk_params_modes.py::test_resolve_model_tier_mode |
| 97-REQ-4.2 | TS-97-E4 | 4.2 | test_sdk_params_modes.py::test_resolve_max_turns_mode |
| 97-REQ-4.3 | TS-97-9 | 4.2 | test_sdk_params_modes.py::test_resolve_thinking_mode |
| 97-REQ-4.4 | TS-97-11 | 4.3 | test_sdk_params_modes.py::test_resolve_security_mode |
| 97-REQ-4.5 | TS-97-13 | 4.4 | test_sdk_params_modes.py::test_clamp_instances_mode |
| 97-REQ-4.E1 | TS-97-E5 | 4.1 | test_sdk_params_modes.py::test_none_mode_identity |
| 97-REQ-5.1 | TS-97-12 | 4.3 | test_sdk_params_modes.py::test_hook_mode |
| 97-REQ-5.2 | TS-97-12 | 4.3 | test_sdk_params_modes.py::test_empty_allowlist_blocks |
| 97-REQ-5.3 | TS-97-13 | 5.1 | test_sdk_params_modes.py::test_session_runner_mode |
| 97-REQ-5.E1 | TS-97-E6 | 4.3 | test_sdk_params_modes.py::test_mode_allowlist_inherit |
| Property 1 | TS-97-P1 | 2.3 | test_mode_properties.py::test_override_semantics |
| Property 2 | TS-97-P2 | 2.3 | test_mode_properties.py::test_inheritance_semantics |
| Property 3 | TS-97-P3 | 2.3 | test_mode_properties.py::test_null_mode_identity |
| Property 4 | TS-97-P4 | 4.1-4.3 | test_mode_properties.py::test_resolution_priority |
| Property 5 | TS-97-P5 | 4.3 | test_mode_properties.py::test_empty_allowlist_blocks_all |
| Property 6 | TS-97-P6 | 3.1 | test_mode_properties.py::test_serialization_roundtrip |
