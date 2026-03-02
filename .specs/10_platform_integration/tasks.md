# Implementation Plan: Platform Integration

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the platform integration layer for agent-fox v2. It adds
the Platform protocol, NullPlatform (direct merge), GitHubPlatform (gh CLI),
and the create_platform factory. Task groups are ordered: tests first, then
protocol and null implementation, then GitHub implementation, then factory and
integration wiring.

## Test Commands

- Unit tests: `uv run pytest tests/unit/platform/ -q`
- Property tests: `uv run pytest tests/property/platform/ -q`
- All platform tests: `uv run pytest tests/unit/platform/ tests/property/platform/ -q`
- Linter: `uv run ruff check agent_fox/platform/`
- Type check: `uv run mypy agent_fox/platform/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure
    - Create `tests/unit/platform/__init__.py`
    - Create `tests/unit/platform/conftest.py` with shared fixtures:
      `mock_subprocess` (patches `subprocess.run`), `null_platform`
      (NullPlatform instance), `github_platform` (GitHubPlatform with mocked
      gh availability), `platform_config` (default PlatformConfig)
    - Create `tests/property/platform/__init__.py`

  - [x] 1.2 Write protocol and NullPlatform tests
    - `tests/unit/platform/test_protocol.py`: TS-10-1 (protocol methods),
      TS-10-2 (NullPlatform satisfies protocol)
    - `tests/unit/platform/test_null.py`: TS-10-3 (create_pr merges),
      TS-10-4 (wait_for_ci), TS-10-5 (wait_for_review), TS-10-6 (merge_pr
      no-op)
    - _Test Spec: TS-10-1, TS-10-2, TS-10-3, TS-10-4, TS-10-5, TS-10-6_

  - [x] 1.3 Write GitHubPlatform tests
    - `tests/unit/platform/test_github.py`: TS-10-7 (create_pr), TS-10-8
      (wait_for_ci pass), TS-10-9 (wait_for_review approved), TS-10-10
      (merge_pr)
    - _Test Spec: TS-10-7, TS-10-8, TS-10-9, TS-10-10_

  - [x] 1.4 Write factory tests
    - `tests/unit/platform/test_factory.py`: TS-10-11 (factory returns
      NullPlatform), TS-10-12 (factory returns GitHubPlatform)
    - _Test Spec: TS-10-11, TS-10-12_

  - [x] 1.5 Write edge case tests
    - `tests/unit/platform/test_github.py`: TS-10-E1 (gh not installed),
      TS-10-E2 (gh not authenticated), TS-10-E3 (create_pr fails), TS-10-E4
      (CI check failure), TS-10-E5 (CI timeout), TS-10-E6 (review rejected),
      TS-10-E7 (merge failure)
    - `tests/unit/platform/test_factory.py`: TS-10-E8 (unknown type)
    - `tests/unit/platform/test_null.py`: TS-10-E9 (merge conflict)
    - _Test Spec: TS-10-E1 through TS-10-E9_

  - [x] 1.6 Write property tests
    - `tests/property/platform/test_platform_props.py`: TS-10-P1 (NullPlatform
      gates always pass), TS-10-P2 (NullPlatform create_pr returns empty),
      TS-10-P3 (factory rejects unknown types)
    - _Test Spec: TS-10-P1, TS-10-P2, TS-10-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/platform/ tests/property/platform/`

- [x] 2. Implement Platform protocol and NullPlatform
  - [x] 2.1 Create package structure
    - `agent_fox/platform/__init__.py`: package init with re-exports
      (`Platform`, `create_platform`)
    - _No requirements -- structural setup_

  - [x] 2.2 Implement Platform protocol
    - `agent_fox/platform/protocol.py`: Platform Protocol class with four
      async methods (`create_pr`, `wait_for_ci`, `wait_for_review`, `merge_pr`)
    - Use `typing.Protocol` with `runtime_checkable` decorator
    - Full type annotations matching the design document signatures
    - _Requirements: 10-REQ-1.1, 10-REQ-1.2, 10-REQ-1.3, 10-REQ-1.4,
      10-REQ-1.5_

  - [x] 2.3 Implement NullPlatform
    - `agent_fox/platform/null.py`: NullPlatform class
    - `create_pr`: merge branch into develop via `git checkout` + `git merge
      --no-ff`, return empty string
    - `wait_for_ci`: return True immediately
    - `wait_for_review`: return True immediately
    - `merge_pr`: no-op
    - Raise `IntegrationError` on git command failures
    - _Requirements: 10-REQ-2.1, 10-REQ-2.2, 10-REQ-2.3, 10-REQ-2.4,
      10-REQ-2.5_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/platform/test_protocol.py tests/unit/platform/test_null.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/platform/ -k "null or protocol" -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/platform/`
    - [x] Requirements 10-REQ-1.*, 10-REQ-2.* acceptance criteria met

- [x] 3. Implement GitHubPlatform
  - [x] 3.1 Implement GitHubPlatform class
    - `agent_fox/platform/github.py`: GitHubPlatform class
    - Constructor: accept `ci_timeout`, `auto_merge`, `base_branch` parameters;
      verify `gh` CLI availability and authentication
    - `_verify_gh_available()`: check `shutil.which("gh")` and
      `gh auth status`; raise `IntegrationError` if either fails
    - `_run_gh(args)`: async helper to run `gh` commands via
      `asyncio.to_thread(subprocess.run, ...)`
    - _Requirements: 10-REQ-3.1, 10-REQ-3.E1_

  - [x] 3.2 Implement create_pr
    - Execute `gh pr create` with `--head`, `--base`, `--title`, `--body`,
      `--label` arguments
    - Parse PR URL from stdout
    - If `auto_merge` is enabled, additionally run `gh pr merge --auto --merge`
    - Raise `IntegrationError` on failure
    - _Requirements: 10-REQ-3.2, 10-REQ-3.E2_

  - [x] 3.3 Implement wait_for_ci
    - Poll `gh pr checks --json name,state,conclusion` at `_CI_POLL_INTERVAL`
      (30s) intervals
    - Parse JSON output; check if all checks completed
    - Return True if all passed (conclusion in success/skipped/neutral)
    - Return False if any failed or timeout expires
    - Handle parse errors and command failures gracefully (log warning, retry)
    - _Requirements: 10-REQ-3.3, 10-REQ-3.E3, 10-REQ-3.E4_

  - [x] 3.4 Implement wait_for_review
    - Poll `gh pr view --json reviewDecision` at `_REVIEW_POLL_INTERVAL`
      (60s) intervals
    - Return True if reviewDecision is "APPROVED"
    - Return False if reviewDecision is "CHANGES_REQUESTED"
    - Handle parse errors and command failures gracefully (log warning, retry)
    - _Requirements: 10-REQ-3.4, 10-REQ-3.E5_

  - [x] 3.5 Implement merge_pr
    - Execute `gh pr merge <url> --merge`
    - Raise `IntegrationError` on failure
    - _Requirements: 10-REQ-3.5, 10-REQ-3.E6_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/platform/test_github.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/platform/github.py`
    - [x] Requirements 10-REQ-3.* acceptance criteria met

- [x] 4. Implement factory and integration wiring
  - [x] 4.1 Implement create_platform factory
    - `agent_fox/platform/factory.py`: `create_platform(config)` function
    - Route "none" to NullPlatform, "github" to GitHubPlatform
    - Pass through config values (ci_timeout, auto_merge) to GitHubPlatform
    - Raise `ConfigError` for unrecognized platform types with list of valid
      values
    - _Requirements: 10-REQ-5.1, 10-REQ-5.2, 10-REQ-5.3, 10-REQ-5.E1_

  - [x] 4.2 Wire up package exports
    - `agent_fox/platform/__init__.py`: export `Platform`, `create_platform`,
      `NullPlatform`, `GitHubPlatform`
    - Verify imports work cleanly

  - [x] 4.V Verify task group 4
    - [x] All spec tests pass: `uv run pytest tests/unit/platform/ tests/property/platform/ -q`
    - [x] All property tests pass: `uv run pytest tests/property/platform/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/platform/`
    - [x] Type check passes: `uv run mypy agent_fox/platform/`
    - [x] Requirements 10-REQ-5.* acceptance criteria met

- [x] 5. Checkpoint -- Platform Integration Complete
  - Ensure all tests pass: `uv run pytest tests/unit/platform/ tests/property/platform/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/platform/ tests/unit/platform/ tests/property/platform/`
  - Ensure type check clean: `uv run mypy agent_fox/platform/`
  - Verify factory returns correct implementations for all valid config types
  - Verify all edge cases are exercised (gh missing, auth failure, CI timeout,
    merge conflict, unknown platform type)

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 10-REQ-1.1 | TS-10-1 | 2.2 | tests/unit/platform/test_protocol.py |
| 10-REQ-1.2 | TS-10-1 | 2.2 | tests/unit/platform/test_protocol.py |
| 10-REQ-1.3 | TS-10-1 | 2.2 | tests/unit/platform/test_protocol.py |
| 10-REQ-1.4 | TS-10-1 | 2.2 | tests/unit/platform/test_protocol.py |
| 10-REQ-1.5 | TS-10-1 | 2.2 | tests/unit/platform/test_protocol.py |
| 10-REQ-2.1 | TS-10-2 | 2.3 | tests/unit/platform/test_protocol.py |
| 10-REQ-2.2 | TS-10-3, TS-10-P2, TS-10-E9 | 2.3 | tests/unit/platform/test_null.py |
| 10-REQ-2.3 | TS-10-4, TS-10-P1 | 2.3 | tests/unit/platform/test_null.py |
| 10-REQ-2.4 | TS-10-5, TS-10-P1 | 2.3 | tests/unit/platform/test_null.py |
| 10-REQ-2.5 | TS-10-6 | 2.3 | tests/unit/platform/test_null.py |
| 10-REQ-3.1 | TS-10-12 | 3.1 | tests/unit/platform/test_factory.py |
| 10-REQ-3.2 | TS-10-7 | 3.2 | tests/unit/platform/test_github.py |
| 10-REQ-3.3 | TS-10-8 | 3.3 | tests/unit/platform/test_github.py |
| 10-REQ-3.4 | TS-10-9 | 3.4 | tests/unit/platform/test_github.py |
| 10-REQ-3.5 | TS-10-10 | 3.5 | tests/unit/platform/test_github.py |
| 10-REQ-3.E1 | TS-10-E1, TS-10-E2 | 3.1 | tests/unit/platform/test_github.py |
| 10-REQ-3.E2 | TS-10-E3 | 3.2 | tests/unit/platform/test_github.py |
| 10-REQ-3.E3 | TS-10-E4 | 3.3 | tests/unit/platform/test_github.py |
| 10-REQ-3.E4 | TS-10-E5 | 3.3 | tests/unit/platform/test_github.py |
| 10-REQ-3.E5 | TS-10-E6 | 3.4 | tests/unit/platform/test_github.py |
| 10-REQ-3.E6 | TS-10-E7 | 3.5 | tests/unit/platform/test_github.py |
| 10-REQ-4.1 | — | (orchestrator, spec 04) | (orchestrator tests) |
| 10-REQ-4.2 | — | (orchestrator, spec 04) | (orchestrator tests) |
| 10-REQ-5.1 | TS-10-11, TS-10-12 | 4.1 | tests/unit/platform/test_factory.py |
| 10-REQ-5.2 | TS-10-11 | 4.1 | tests/unit/platform/test_factory.py |
| 10-REQ-5.3 | TS-10-12 | 4.1 | tests/unit/platform/test_factory.py |
| 10-REQ-5.E1 | TS-10-E8, TS-10-P3 | 4.1 | tests/unit/platform/test_factory.py |
| Property 1 | TS-10-P1 | 2.3 | tests/property/platform/test_platform_props.py |
| Property 2 | TS-10-P2 | 2.3 | tests/property/platform/test_platform_props.py |
| Property 3 | TS-10-P3 | 4.1 | tests/property/platform/test_platform_props.py |
| Property 4 | TS-10-11, TS-10-12 | 4.1 | tests/unit/platform/test_factory.py |
| Property 5 | TS-10-1, TS-10-2 | 2.2, 2.3 | tests/unit/platform/test_protocol.py |
| Property 6 | TS-10-E5 | 3.3 | tests/unit/platform/test_github.py |

## Notes

- All `gh` CLI interactions are mocked in tests. No real GitHub API calls.
- `subprocess.run` is the primary mock target for both `git` commands
  (NullPlatform) and `gh` commands (GitHubPlatform).
- For CI timeout tests, patch `_CI_POLL_INTERVAL` to 0 and use a small timeout
  (1 second) to avoid slow tests.
- The `asyncio` test pattern uses `pytest-asyncio` with `@pytest.mark.asyncio`
  decorators.
- PR granularity (10-REQ-4.1, 10-REQ-4.2) is orchestrator-level logic defined
  in spec 04. This spec provides the platform primitives that the orchestrator
  calls.
- `PlatformConfig` is already defined in spec 01 (`agent_fox/core/config.py`).
  This spec consumes it but does not modify it.
