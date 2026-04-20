# Implementation Plan: Prompt Caching

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four groups: (1) write failing spec tests,
(2) add configuration and the cached message helper, (3) migrate all
auxiliary modules, (4) final checkpoint and documentation.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_prompt_caching.py tests/property/test_prompt_caching_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_prompt_caching.py`
    - Set up `MockAsyncAnthropic` / `MockAnthropic` fixtures that capture
      kwargs passed to `messages.create()`
    - _Test Spec: TS-77-1 through TS-77-10, TS-77-E1 through TS-77-E4_

  - [x] 1.2 Translate acceptance-criterion tests
    - `test_default_cache_policy` — TS-77-1
    - `test_cache_policy_parsing` — TS-77-2
    - `test_none_policy_passthrough` — TS-77-3
    - `test_default_policy_marker` — TS-77-4
    - `test_extended_policy_marker` — TS-77-5
    - `test_multi_block_system_prompt` — TS-77-6
    - `test_no_system_parameter` — TS-77-7
    - `test_auxiliary_modules_use_helper` — TS-77-8
    - `test_token_threshold_estimation` — TS-77-9
    - `test_threshold_gating_skips_small` — TS-77-10
    - _Test Spec: TS-77-1 through TS-77-10_

  - [x] 1.3 Translate edge-case tests
    - `test_invalid_cache_policy_value` — TS-77-E1
    - `test_string_system_prompt_conversion` — TS-77-E2
    - `test_cache_control_api_error_retry` — TS-77-E3
    - `test_unknown_model_default_threshold` — TS-77-E4
    - _Test Spec: TS-77-E1 through TS-77-E4_

  - [x] 1.4 Create property test file `tests/property/test_prompt_caching_props.py`
    - `test_policy_fidelity` — TS-77-P1
    - `test_string_to_block_normalization` — TS-77-P2
    - `test_threshold_gate` — TS-77-P3
    - `test_none_policy_passthrough_property` — TS-77-P4
    - _Test Spec: TS-77-P1 through TS-77-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Configuration and cached message helper
  - [x] 2.1 Add `CachePolicy` enum and `CachingConfig` model to `agent_fox/core/config.py`
    - `CachePolicy(str, Enum)` with NONE, DEFAULT, EXTENDED
    - `CachingConfig(BaseModel)` with `cache_policy: CachePolicy = CachePolicy.DEFAULT`
    - Add `caching: CachingConfig` field to `AgentFoxConfig`
    - Case-insensitive parsing via Pydantic validator
    - _Requirements: 77-REQ-1.1, 77-REQ-1.2, 77-REQ-1.E1_

  - [x] 2.2 Add token threshold constants and `_estimate_tokens()` to `agent_fox/core/client.py`
    - `_CACHE_TOKEN_THRESHOLDS` dict mapping model IDs to minimum tokens
    - `_DEFAULT_THRESHOLD = 4096`
    - `_estimate_tokens(text: str) -> int` — `len(text) // 4`
    - _Requirements: 77-REQ-4.1, 77-REQ-4.2, 77-REQ-4.3, 77-REQ-4.E1_

  - [x] 2.3 Add `cached_messages_create()` async helper to `agent_fox/core/client.py`
    - Accept same params as `client.messages.create()` plus `cache_policy`
    - NONE → passthrough; DEFAULT/EXTENDED → inject `cache_control` on last system block
    - String system prompt → convert to content-block list
    - Skip `cache_control` if estimated tokens below model threshold
    - On `cache_control`-related API error, log warning and retry without caching
    - _Requirements: 77-REQ-2.1, 77-REQ-2.2, 77-REQ-2.3, 77-REQ-2.4, 77-REQ-2.E1, 77-REQ-2.E2_

  - [x] 2.4 Add `cached_messages_create_sync()` variant for sync callers
    - Same logic as async version, using sync `client.messages.create()`
    - Used by `knowledge_harvest.py`, `query_oracle.py`, `clusterer.py`
    - _Requirements: 77-REQ-2.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for config and helper pass: `uv run pytest -q tests/unit/test_prompt_caching.py -k "not auxiliary"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_prompt_caching_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 77-REQ-1.*, 77-REQ-2.*, 77-REQ-4.*, 77-REQ-5.* acceptance criteria met

- [x] 3. Migrate auxiliary modules
  - [x] 3.1 Migrate async callers to `cached_messages_create()`
    - `knowledge/extraction.py` — refactor to use `system=` for stable instruction content
    - `nightshift/critic.py` — already uses `system=`, swap to helper
    - `nightshift/staleness.py` — refactor to use `system=` for stable instruction content
    - `nightshift/triage.py` — refactor to use `system=` for stable instruction content
    - `routing/assessor.py` — already uses `system=`, swap to helper
    - `spec/ai_validation.py` (2 call sites) — refactor to use `system=` for template content
    - _Requirements: 77-REQ-3.1, 77-REQ-3.2, 77-REQ-3.3_

  - [x] 3.2 Migrate sync callers to `cached_messages_create_sync()`
    - `engine/knowledge_harvest.py` — refactor to use `system=` for stable instruction content
    - `knowledge/query_oracle.py` — refactor to use `system=` for stable instruction content
    - `fix/clusterer.py` — refactor to use `system=` for stable instruction content
    - _Requirements: 77-REQ-3.1, 77-REQ-3.2, 77-REQ-3.3_

  - [x] 3.3 Thread `cache_policy` from config to each call site
    - Each module must receive `CachePolicy` from config (via constructor,
      function parameter, or config lookup)
    - _Requirements: 77-REQ-3.1_

  - [x] 3.V Verify task group 3
    - [x] Auxiliary module migration test passes: `uv run pytest -q tests/unit/test_prompt_caching.py::test_auxiliary_modules_use_helper`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 77-REQ-3.* acceptance criteria met
    - [x] No direct `.messages.create(` calls remain in auxiliary modules

- [x] 4. Checkpoint — Prompt Caching Complete
  - [x] 4.1 Full test suite green
    - `make check` passes
  - [x] 4.2 Update documentation
    - Add `[caching]` section example to `docs/cli-reference.md` or relevant config docs
    - Document the three cache policies and their trade-offs

## Traceability

| Requirement   | Test Spec Entry          | Implemented By Task | Verified By Test                                  |
|---------------|--------------------------|---------------------|---------------------------------------------------|
| 77-REQ-1.1    | TS-77-2                  | 2.1                 | `test_cache_policy_parsing`                       |
| 77-REQ-1.2    | TS-77-1                  | 2.1                 | `test_default_cache_policy`                       |
| 77-REQ-1.3    | TS-77-3, TS-77-P1        | 2.1, 2.3            | `test_none_policy_passthrough`, `test_policy_fidelity` |
| 77-REQ-1.4    | TS-77-4, TS-77-P1        | 2.3                 | `test_default_policy_marker`, `test_policy_fidelity` |
| 77-REQ-1.5    | TS-77-5, TS-77-P1        | 2.3                 | `test_extended_policy_marker`, `test_policy_fidelity` |
| 77-REQ-1.E1   | TS-77-E1                 | 2.1                 | `test_invalid_cache_policy_value`                 |
| 77-REQ-2.1    | TS-77-4                  | 2.3, 2.4            | `test_default_policy_marker`                      |
| 77-REQ-2.2    | TS-77-4, TS-77-6, TS-77-P1 | 2.3               | `test_default_policy_marker`, `test_multi_block_system_prompt` |
| 77-REQ-2.3    | TS-77-7                  | 2.3                 | `test_no_system_parameter`                        |
| 77-REQ-2.4    | TS-77-3, TS-77-P4        | 2.3                 | `test_none_policy_passthrough`, `test_none_policy_passthrough_property` |
| 77-REQ-2.E1   | TS-77-E2, TS-77-P2       | 2.3                 | `test_string_system_prompt_conversion`, `test_string_to_block_normalization` |
| 77-REQ-2.E2   | TS-77-E3                 | 2.3                 | `test_cache_control_api_error_retry`              |
| 77-REQ-3.1    | TS-77-8                  | 3.1, 3.2, 3.3       | `test_auxiliary_modules_use_helper`                |
| 77-REQ-3.2    | TS-77-8                  | 3.1, 3.2            | `test_auxiliary_modules_use_helper`                |
| 77-REQ-3.3    | TS-77-8                  | 3.1, 3.2            | `test_auxiliary_modules_use_helper`                |
| 77-REQ-3.E1   | TS-77-7                  | 3.1                 | `test_no_system_parameter`                        |
| 77-REQ-4.1    | TS-77-P3                 | 2.2                 | `test_threshold_gate`                             |
| 77-REQ-4.2    | TS-77-10, TS-77-P3       | 2.2, 2.3            | `test_threshold_gating_skips_small`, `test_threshold_gate` |
| 77-REQ-4.3    | TS-77-9, TS-77-P3        | 2.2                 | `test_token_threshold_estimation`, `test_threshold_gate` |
| 77-REQ-4.E1   | TS-77-E4                 | 2.2                 | `test_unknown_model_default_threshold`            |
| 77-REQ-5.1    | TS-77-3, TS-77-P4        | 2.3                 | `test_none_policy_passthrough`, `test_none_policy_passthrough_property` |
| 77-REQ-5.2    | (existing tests)         | —                   | (existing cost tracking tests)                    |

## Notes

- All tests use mocked Anthropic clients — no API keys or network access needed.
- TS-77-8 (auxiliary module migration) is a source-code inspection test — it
  reads the Python source of each module and asserts the import/call pattern.
  It will fail until task group 3 is complete.
- Sync and async helpers share the same injection logic; consider extracting
  the common `_inject_cache_control()` as a pure function to keep both
  variants in sync.
- The `cache_policy` value must be threaded from `AgentFoxConfig` to each
  call site. The exact plumbing depends on how each module receives config
  (constructor injection, parameter, or global lookup). Task 3.3 handles this.
