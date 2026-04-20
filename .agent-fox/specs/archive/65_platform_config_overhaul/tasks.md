# Implementation Plan: Platform Config Overhaul

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan removes `auto_merge` from `PlatformConfig`, simplifies
post-harvest to pure local-git pushes, drops `create_pr` from the platform
layer, adds a `url` field for GitHub Enterprise support, and updates config
generation. Existing tests for the old behavior (spec 19 post-harvest and
platform config tests) are rewritten to match the new semantics.

Task group 1 writes all failing tests. Groups 2-4 implement the changes
to make those tests pass. Group 5 cleans up old tests and documentation.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/platform/ tests/unit/engine/test_post_harvest.py tests/property/platform/`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for config schema changes
    - Create `tests/unit/platform/test_platform_config_v2.py`
    - Tests for TS-65-1 (no auto_merge), TS-65-2 (old key ignored),
      TS-65-3 (url field), TS-65-4 (url defaults)
    - Tests for TS-65-E1 (unknown keys), TS-65-E2 (url with type=none)
    - _Test Spec: TS-65-1, TS-65-2, TS-65-3, TS-65-4, TS-65-E1, TS-65-E2_

  - [x] 1.2 Create unit test file for post-harvest simplification
    - Create `tests/unit/engine/test_post_harvest_v2.py`
    - Tests for TS-65-7 (pushes feature), TS-65-8 (pushes develop),
      TS-65-9 (no platform_config param), TS-65-10 (no GitHubPlatform ref),
      TS-65-11 (push failure best-effort)
    - Tests for TS-65-E3 (feature branch deleted)
    - _Test Spec: TS-65-7, TS-65-8, TS-65-9, TS-65-10, TS-65-11, TS-65-E3_

  - [x] 1.3 Create unit tests for platform layer removal and URL
    - Add tests to `tests/unit/platform/test_platform_config_v2.py` or
      a new file for TS-65-12 (protocol no create_pr),
      TS-65-13 (GitHubPlatform no create_pr),
      TS-65-14 (no _get_default_branch),
      TS-65-15 (url param accepted),
      TS-65-5 (api.github.com resolution),
      TS-65-6 (GHE resolution),
      TS-65-E4 (empty url default)
    - _Test Spec: TS-65-5, TS-65-6, TS-65-12, TS-65-13, TS-65-14, TS-65-15, TS-65-E4_

  - [x] 1.4 Create unit tests for factory and config generation
    - Test for TS-65-16 (factory wires url)
    - Tests for TS-65-17 (template has type+url), TS-65-18 (no auto_merge)
    - Test for TS-65-E5 (missing GITHUB_PAT exits)
    - _Test Spec: TS-65-16, TS-65-17, TS-65-18, TS-65-E5_

  - [x] 1.5 Create property tests
    - Create `tests/property/platform/test_platform_overhaul_v2.py`
    - Property tests for TS-65-P1 through TS-65-P6
    - _Test Spec: TS-65-P1, TS-65-P2, TS-65-P3, TS-65-P4, TS-65-P5, TS-65-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement config model and platform layer changes
  - [x] 2.1 Update PlatformConfig in `agent_fox/core/config.py`
    - Remove `auto_merge` field
    - Add `url` field with default `""`
    - Keep `extra = "ignore"` for backward compatibility
    - _Requirements: 65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1, 65-REQ-2.1, 65-REQ-2.2, 65-REQ-2.3, 65-REQ-2.E1_

  - [x] 2.2 Update GitHubPlatform in `agent_fox/platform/github.py`
    - Add `url` parameter to `__init__` (default `"github.com"`)
    - Add `_api_base` property resolving URL to API base
    - Replace hardcoded `_GITHUB_API` with `self._api_base` in all methods
    - Remove `create_pr()` method
    - Remove `_get_default_branch()` method
    - _Requirements: 65-REQ-4.2, 65-REQ-4.3, 65-REQ-5.1, 65-REQ-5.2, 65-REQ-5.3, 65-REQ-5.E1_

  - [x] 2.3 Update PlatformProtocol in `agent_fox/platform/protocol.py`
    - Remove `create_pr` method from protocol
    - _Requirements: 65-REQ-4.1_

  - [x] 2.4 Update platform factory in `agent_fox/nightshift/platform_factory.py`
    - Pass `url` from config to `GitHubPlatform` constructor
    - Resolve empty url to `"github.com"` before passing
    - _Requirements: 65-REQ-6.1, 65-REQ-6.E1_

  - [x] 2.V Verify task group 2
    - [x] Config and platform tests pass: `uv run pytest -q tests/unit/platform/test_platform_config_v2.py`
    - [x] Platform URL tests pass
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 65-REQ-1.*, 65-REQ-2.*, 65-REQ-4.*, 65-REQ-5.*, 65-REQ-6.* met

- [x] 3. Simplify post-harvest integration
  - [x] 3.1 Rewrite `post_harvest_integrate` in `agent_fox/workspace/harvest.py`
    - Remove `platform_config` parameter
    - Remove all GitHub API code (GitHubPlatform import, PR creation, token check, remote URL parsing)
    - Always push feature branch (if exists) + develop
    - Keep best-effort semantics and existing reconciliation logic
    - _Requirements: 65-REQ-3.1, 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4, 65-REQ-3.5, 65-REQ-3.E1, 65-REQ-3.E2_

  - [x] 3.2 Update call site in `agent_fox/engine/session_lifecycle.py`
    - Remove `platform_config=self._config.platform` argument from
      `post_harvest_integrate()` call
    - _Requirements: 65-REQ-3.3_

  - [x] 3.V Verify task group 3
    - [x] Post-harvest tests pass: `uv run pytest -q tests/unit/engine/test_post_harvest_v2.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 65-REQ-3.* met

- [x] 4. Update config generation and clean up old tests
  - [x] 4.1 Update config generation in `agent_fox/core/config_gen.py`
    - Remove `("PlatformConfig", "auto_merge")` from `_DEFAULT_DESCRIPTIONS`
    - Add description for `("PlatformConfig", "url")`
    - _Requirements: 65-REQ-7.1, 65-REQ-7.2, 65-REQ-7.3_

  - [x] 4.2 Remove or rewrite old spec 19 tests
    - Remove `tests/unit/platform/test_platform_config.py` (superseded by v2)
    - Remove `tests/unit/engine/test_post_harvest.py` (superseded by v2)
    - Rewrite `tests/property/platform/test_overhaul_props.py`:
      remove TS-19-P4 (strategy-matches-config), update TS-19-P3
      (backward compat) to exclude `auto_merge` from "old fields"
    - Also cleaned up `tests/unit/platform/test_github_rest.py` and
      `tests/unit/nightshift/test_platform.py` to remove create_pr references
    - _Requirements: all (regression prevention)_

  - [x] 4.3 Rename v2 test files to replace originals
    - Rename `test_platform_config_v2.py` → `test_platform_config.py`
    - Rename `test_post_harvest_v2.py` → `test_post_harvest.py`
    - Merged `test_platform_overhaul_v2.py` into `test_overhaul_props.py`
    - _Requirements: all (clean file naming)_

  - [x] 4.V Verify task group 4
    - [x] Config template tests pass: `uv run pytest -q tests/unit/core/test_config_gen.py`
    - [x] All tests pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 65-REQ-7.* met

- [x] 5. Checkpoint — Platform Config Overhaul Complete
  - Ensure `make check` passes (lint + all tests).
  - Update `docs/memory.md` with key decisions if applicable.
  - Verify no stale references to `auto_merge` or `create_pr` remain
    in the codebase: `grep -r "auto_merge\|create_pr" agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|---|---|---|---|
| 65-REQ-1.1 | TS-65-1 | 2.1 | test_platform_config::test_no_auto_merge_field |
| 65-REQ-1.2 | TS-65-2 | 2.1 | test_platform_config::test_old_auto_merge_ignored |
| 65-REQ-1.E1 | TS-65-E1 | 2.1 | test_platform_config::test_unknown_keys_ignored |
| 65-REQ-2.1 | TS-65-3 | 2.1 | test_platform_config::test_url_field |
| 65-REQ-2.2 | TS-65-4 | 2.1 | test_platform_config::test_url_defaults |
| 65-REQ-2.3 | TS-65-4 | 2.1 | test_platform_config::test_url_defaults |
| 65-REQ-2.4 | TS-65-5 | 2.2 | test_platform_config::test_api_base_github_com |
| 65-REQ-2.5 | TS-65-6 | 2.2 | test_platform_config::test_api_base_ghe |
| 65-REQ-2.E1 | TS-65-E2 | 2.1 | test_platform_config::test_url_with_type_none |
| 65-REQ-3.1 | TS-65-7 | 3.1 | test_post_harvest::test_pushes_feature |
| 65-REQ-3.2 | TS-65-8 | 3.1 | test_post_harvest::test_pushes_develop |
| 65-REQ-3.3 | TS-65-9 | 3.1, 3.2 | test_post_harvest::test_no_platform_config_param |
| 65-REQ-3.4 | TS-65-10 | 3.1 | test_post_harvest::test_no_github_platform_ref |
| 65-REQ-3.5 | TS-65-11 | 3.1 | test_post_harvest::test_push_failure_best_effort |
| 65-REQ-3.E1 | TS-65-E3 | 3.1 | test_post_harvest::test_feature_branch_deleted |
| 65-REQ-3.E2 | — | 3.1 | (existing spec 36 reconciliation tests) |
| 65-REQ-4.1 | TS-65-12 | 2.3 | test_platform_config::test_protocol_no_create_pr |
| 65-REQ-4.2 | TS-65-13 | 2.2 | test_platform_config::test_github_no_create_pr |
| 65-REQ-4.3 | TS-65-14 | 2.2 | test_platform_config::test_github_no_get_default_branch |
| 65-REQ-5.1 | TS-65-15 | 2.2 | test_platform_config::test_url_param_accepted |
| 65-REQ-5.2 | TS-65-5 | 2.2 | test_platform_config::test_api_base_github_com |
| 65-REQ-5.3 | TS-65-6 | 2.2 | test_platform_config::test_api_base_ghe |
| 65-REQ-5.E1 | TS-65-E4 | 2.2 | test_platform_config::test_empty_url_defaults |
| 65-REQ-6.1 | TS-65-16 | 2.4 | test_platform_config::test_factory_wires_url |
| 65-REQ-6.E1 | TS-65-E5 | 2.4 | test_platform_config::test_missing_pat_exits |
| 65-REQ-7.1 | TS-65-17 | 4.1 | test_config_gen::test_template_has_type_and_url |
| 65-REQ-7.2 | TS-65-18 | 4.1 | test_config_gen::test_template_no_auto_merge |
| 65-REQ-7.3 | TS-65-17 | 4.1 | test_config_gen::test_template_has_type_and_url |
| Property 1 | TS-65-P1 | 3.1 | test_overhaul_props::test_always_pushes_both |
| Property 2 | TS-65-P2 | 3.1 | test_overhaul_props::test_no_github_api |
| Property 3 | TS-65-P3 | 2.2 | test_overhaul_props::test_url_resolution |
| Property 4 | TS-65-P4 | 2.1 | test_overhaul_props::test_unknown_keys_ignored |
| Property 5 | TS-65-P5 | 2.4 | test_overhaul_props::test_factory_wires_url |
| Property 6 | TS-65-P6 | 4.1 | test_overhaul_props::test_template_schema |

## Notes

- Old test files (`test_platform_config.py`, `test_post_harvest.py`) are
  replaced in task group 4, after new implementation is verified.
- Property test `TS-19-P4` (strategy-matches-config) is deleted since
  the strategy branching logic no longer exists.
- The `_GITHUB_API` module-level constant in `github.py` is replaced by
  an instance-level `_api_base` attribute.
- `post_harvest_integrate` call site in `session_lifecycle.py` must be
  updated in the same group as the function signature change (group 3).
