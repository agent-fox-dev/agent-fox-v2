# Implementation Plan: Claude SDK Feature Adoption

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four phases: (1) write failing tests, (2) add
config model extensions and archetype defaults, (3) wire parameters through
session lifecycle and backend, (4) checkpoint. Each SDK feature (max_turns,
max_budget_usd, fallback_model, thinking) is wired in a single pass through
the config → lifecycle → backend pipeline.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_sdk_features.py tests/unit/test_sdk_config.py tests/property/test_sdk_features_props.py tests/integration/test_sdk_features_integration.py`
- Unit tests: `uv run pytest -q tests/unit/test_sdk_features.py tests/unit/test_sdk_config.py`
- Property tests: `uv run pytest -q tests/property/test_sdk_features_props.py`
- Integration tests: `uv run pytest -q tests/integration/test_sdk_features_integration.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/test_sdk_config.py`
    - Config parsing tests for max_turns (TS-56-1), max_budget_usd (TS-56-5),
      fallback_model (TS-56-8), thinking (TS-56-12)
    - Default value tests (TS-56-3, TS-56-7, TS-56-10, TS-56-14)
    - Validation error tests (TS-56-E1, TS-56-E3, TS-56-E5, TS-56-E6)
    - _Test Spec: TS-56-1, TS-56-3, TS-56-5, TS-56-7, TS-56-8, TS-56-10, TS-56-12, TS-56-14, TS-56-E1, TS-56-E3, TS-56-E5, TS-56-E6_

  - [x] 1.2 Create `tests/unit/test_sdk_features.py`
    - Passthrough tests for max_turns (TS-56-2), max_budget_usd (TS-56-6),
      fallback_model (TS-56-9), thinking (TS-56-13)
    - Zero/empty/unlimited tests (TS-56-4, TS-56-11, TS-56-E2)
    - Protocol signature test (TS-56-15)
    - Unknown fallback model warning test (TS-56-E4)
    - _Test Spec: TS-56-2, TS-56-4, TS-56-6, TS-56-9, TS-56-11, TS-56-13, TS-56-15, TS-56-E2, TS-56-E4_

  - [x] 1.3 Create `tests/property/test_sdk_features_props.py`
    - Turn limit passthrough invariant (TS-56-P1)
    - Zero turns unlimited invariant (TS-56-P2)
    - Budget cap passthrough invariant (TS-56-P3)
    - Fallback model passthrough invariant (TS-56-P4)
    - Thinking passthrough invariant (TS-56-P5)
    - Config override precedence invariant (TS-56-P6)
    - Validation rejection invariant (TS-56-P7)
    - SDK compatibility fallback (TS-56-P8)
    - _Test Spec: TS-56-P1 through TS-56-P8_

  - [x] 1.4 Create `tests/integration/test_sdk_features_integration.py`
    - SDK TypeError fallback test (TS-56-E7)
    - _Test Spec: TS-56-E7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_sdk_config.py tests/unit/test_sdk_features.py tests/property/test_sdk_features_props.py tests/integration/test_sdk_features_integration.py`

- [x] 2. Config model extensions and archetype defaults
  - [x] 2.1 Add `ThinkingConfig` model to `agent_fox/core/config.py`
    - Pydantic model with `mode` (Literal), `budget_tokens` (int, ge=0)
    - Model validator: budget_tokens > 0 when mode == "enabled"
    - _Requirements: 56-REQ-4.1, 56-REQ-4.E1, 56-REQ-4.E2_

  - [x] 2.2 Extend `ArchetypeConfig` in `agent_fox/core/config.py`
    - Add `max_turns: dict[str, int]` with Field(default_factory=dict)
    - Add `thinking: dict[str, ThinkingConfig]` with Field(default_factory=dict)
    - Add validator: reject negative max_turns values
    - _Requirements: 56-REQ-1.1, 56-REQ-1.E1_

  - [x] 2.3 Extend `OrchestratorConfig` in `agent_fox/core/config.py`
    - Add `max_budget_usd: float` with Field(default=2.0, ge=0.0)
    - _Requirements: 56-REQ-2.1, 56-REQ-2.3, 56-REQ-2.E2_

  - [x] 2.4 Extend `ModelsConfig` in `agent_fox/core/config.py`
    - Add `fallback_model: str = "claude-sonnet-4-6"`
    - _Requirements: 56-REQ-3.1, 56-REQ-3.3_

  - [x] 2.5 Add default values to `ArchetypeEntry` in `agent_fox/session/archetypes.py`
    - Add `default_max_turns` field per archetype (coder=200, oracle=50, etc.)
    - Add `default_thinking_mode` and `default_thinking_budget` fields
    - Set coder to adaptive/10000, all others to disabled/10000
    - _Requirements: 56-REQ-1.3, 56-REQ-4.3_

  - [x] 2.V Verify task group 2
    - [x] Config tests pass: `uv run pytest -q tests/unit/test_sdk_config.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/core/config.py agent_fox/session/archetypes.py`
    - [x] Requirements 56-REQ-1.1, 56-REQ-1.3, 56-REQ-2.1, 56-REQ-2.3, 56-REQ-3.1, 56-REQ-3.3, 56-REQ-4.1, 56-REQ-4.3 acceptance criteria met

- [x] 3. Wire parameters through session lifecycle and backend
  - [x] 3.1 Extend `AgentBackend` protocol in `protocol.py`
    - Add optional kwargs: `max_turns`, `max_budget_usd`, `fallback_model`, `thinking`
    - _Requirements: 56-REQ-5.3_

  - [x] 3.2 Update `ClaudeBackend.execute()` in `claude.py`
    - Accept new kwargs and forward to `ClaudeCodeOptions`
    - Only include params when not None/zero/empty
    - Wrap in try/except TypeError for SDK compatibility (56-REQ-5.E1)
    - Map ThinkingBlock to AssistantMessage when present
    - _Requirements: 56-REQ-1.2, 56-REQ-2.2, 56-REQ-3.2, 56-REQ-4.2, 56-REQ-4.4, 56-REQ-5.2, 56-REQ-5.E1_

  - [x] 3.3 Add resolution functions in `session_lifecycle.py`
    - `_resolve_max_turns(config, archetype)` — config override > archetype default
    - `_resolve_thinking(config, archetype)` — config override > archetype default
    - `_resolve_fallback_model(config)` — empty string → None
    - `_resolve_max_budget(config)` — zero → None
    - _Requirements: 56-REQ-1.4, 56-REQ-2.E1, 56-REQ-3.4, 56-REQ-5.1_

  - [x] 3.4 Update `run_session()` in `session.py`
    - Accept and forward new parameters to `backend.execute()`
    - _Requirements: 56-REQ-5.2_

  - [x] 3.5 Update `session_lifecycle.py` callers
    - Resolve max_turns, thinking per archetype before calling `run_session()`
    - Resolve max_budget_usd, fallback_model from config
    - Log resolved values at session start
    - Warn if fallback_model not in MODEL_REGISTRY (56-REQ-3.E1)
    - _Requirements: 56-REQ-1.2, 56-REQ-2.2, 56-REQ-3.2, 56-REQ-3.E1, 56-REQ-4.2_

  - [x] 3.V Verify task group 3
    - [x] All spec tests pass: `uv run pytest -q tests/unit/test_sdk_features.py tests/unit/test_sdk_config.py tests/property/test_sdk_features_props.py tests/integration/test_sdk_features_integration.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/`
    - [x] Requirements 56-REQ-1.2, 56-REQ-2.2, 56-REQ-3.2, 56-REQ-4.2, 56-REQ-5.1, 56-REQ-5.2, 56-REQ-5.3, 56-REQ-5.E1 acceptance criteria met

- [x] 4. Checkpoint — SDK Feature Adoption Complete
  - Ensure all tests pass and no regressions.
  - Update `docs/cli-reference.md` if config.toml changes affect CLI behavior.
  - Verify config.toml example in README or docs includes new fields.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 56-REQ-1.1 | TS-56-1, TS-56-P1 | 2.2 | test_sdk_config.py::test_max_turns_parsing |
| 56-REQ-1.2 | TS-56-2, TS-56-P1 | 3.2, 3.5 | test_sdk_features.py::test_max_turns_passthrough |
| 56-REQ-1.3 | TS-56-3 | 2.5 | test_sdk_config.py::test_max_turns_defaults |
| 56-REQ-1.4 | TS-56-4, TS-56-P2 | 3.3 | test_sdk_features.py::test_max_turns_zero |
| 56-REQ-1.E1 | TS-56-E1, TS-56-P7 | 2.2 | test_sdk_config.py::test_negative_max_turns |
| 56-REQ-2.1 | TS-56-5, TS-56-P3 | 2.3 | test_sdk_config.py::test_budget_parsing |
| 56-REQ-2.2 | TS-56-6, TS-56-P3 | 3.2, 3.5 | test_sdk_features.py::test_budget_passthrough |
| 56-REQ-2.3 | TS-56-7 | 2.3 | test_sdk_config.py::test_budget_default |
| 56-REQ-2.4 | TS-56-6 | 3.2 | test_sdk_features.py::test_budget_passthrough |
| 56-REQ-2.E1 | TS-56-E2 | 3.3 | test_sdk_features.py::test_budget_zero |
| 56-REQ-2.E2 | TS-56-E3, TS-56-P7 | 2.3 | test_sdk_config.py::test_negative_budget |
| 56-REQ-3.1 | TS-56-8, TS-56-P4 | 2.4 | test_sdk_config.py::test_fallback_parsing |
| 56-REQ-3.2 | TS-56-9, TS-56-P4 | 3.2, 3.5 | test_sdk_features.py::test_fallback_passthrough |
| 56-REQ-3.3 | TS-56-10 | 2.4 | test_sdk_config.py::test_fallback_default |
| 56-REQ-3.4 | TS-56-11 | 3.3 | test_sdk_features.py::test_fallback_empty |
| 56-REQ-3.E1 | TS-56-E4 | 3.5 | test_sdk_features.py::test_fallback_unknown_warns |
| 56-REQ-4.1 | TS-56-12, TS-56-P5 | 2.1, 2.2 | test_sdk_config.py::test_thinking_parsing |
| 56-REQ-4.2 | TS-56-13, TS-56-P5 | 3.2, 3.5 | test_sdk_features.py::test_thinking_passthrough |
| 56-REQ-4.3 | TS-56-14 | 2.5 | test_sdk_config.py::test_thinking_defaults |
| 56-REQ-4.4 | TS-56-13 | 3.2 | test_sdk_features.py::test_thinking_passthrough |
| 56-REQ-4.E1 | TS-56-E5, TS-56-P7 | 2.1 | test_sdk_config.py::test_invalid_thinking_mode |
| 56-REQ-4.E2 | TS-56-E6, TS-56-P7 | 2.1 | test_sdk_config.py::test_zero_budget_enabled |
| 56-REQ-5.1 | TS-56-1, TS-56-P6 | 2.2, 3.3 | test_sdk_features_props.py::test_config_override_precedence |
| 56-REQ-5.2 | TS-56-2, TS-56-6, TS-56-9, TS-56-13 | 3.2, 3.4 | test_sdk_features.py |
| 56-REQ-5.3 | TS-56-15 | 3.1 | test_sdk_features.py::test_protocol_signature |
| 56-REQ-5.E1 | TS-56-E7, TS-56-P8 | 3.2 | test_sdk_features_integration.py::test_sdk_typeerror_fallback |
