# Implementation Plan: Platform Issue Abstraction

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan refactors issue management from the session module to the platform
module behind an abstract `Platform` protocol. Task group 1 writes failing
tests; groups 2-5 implement the protocol, GitLab platform, factory, and
migration in order.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/platform/ tests/property/platform/ -x`
- Unit tests: `uv run pytest -q tests/unit/ -x`
- Property tests: `uv run pytest -q tests/property/ -x`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file structure
    - Create `tests/unit/platform/test_protocol.py` — protocol and conformance tests
    - Create `tests/unit/platform/test_gitlab.py` — GitLabPlatform unit tests
    - Create `tests/unit/platform/test_factory.py` — factory tests
    - Create `tests/unit/platform/test_issues.py` — file_or_update_issue tests (moved)
    - Create `tests/property/platform/test_platform_props.py` — property tests
    - Ensure `__init__.py` files exist in test directories
    - _Test Spec: TS-48-1 through TS-48-19_

  - [ ] 1.2 Translate protocol and conformance tests
    - TS-48-1: Protocol exports (attributes exist)
    - TS-48-2: GitHubPlatform satisfies protocol (isinstance + name)
    - TS-48-3: GitLabPlatform satisfies protocol (isinstance + name)
    - TS-48-E1: Incomplete class fails isinstance
    - _Test Spec: TS-48-1, TS-48-2, TS-48-3, TS-48-E1_

  - [ ] 1.3 Translate GitLabPlatform unit tests
    - TS-48-4: create_issue returns IssueResult
    - TS-48-5: search_issues returns list / empty list
    - TS-48-6: update_issue sends PUT
    - TS-48-7: close_issue sends PUT with state_event
    - TS-48-8: add_issue_comment posts note
    - TS-48-9: Auth header uses PRIVATE-TOKEN
    - TS-48-E2: API error raises IntegrationError
    - TS-48-E9: Search no results returns []
    - _Test Spec: TS-48-4 through TS-48-9, TS-48-E2, TS-48-E9_

  - [ ] 1.4 Translate factory tests
    - TS-48-10: Factory returns GitHubPlatform
    - TS-48-11: Factory returns GitLabPlatform
    - TS-48-12: Factory returns None for "none"
    - TS-48-E3: Factory missing token
    - TS-48-E4: Factory unparseable remote
    - TS-48-E5: Factory unknown type
    - _Test Spec: TS-48-10 through TS-48-12, TS-48-E3 through TS-48-E5_

  - [ ] 1.5 Translate file_or_update_issue and auditor tests
    - TS-48-13: Import from new path
    - TS-48-14: Works with any Platform
    - TS-48-15: Search-before-create behavior
    - TS-48-16: handle_auditor_issue renamed import
    - TS-48-17: handle_auditor_issue uses protocol
    - TS-48-18: PlatformConfig accepts "gitlab"
    - TS-48-19: Old github_issues.py deleted
    - TS-48-E6: file_or_update_issue platform None
    - TS-48-E7: file_or_update_issue API error swallowed
    - TS-48-E8: handle_auditor_issue platform None
    - _Test Spec: TS-48-13 through TS-48-19, TS-48-E6 through TS-48-E8_

  - [ ] 1.6 Translate property tests
    - TS-48-P1: Protocol structural conformance
    - TS-48-P2: Factory determinism
    - TS-48-P3: Factory graceful degradation
    - TS-48-P4: file_or_update_issue idempotency
    - TS-48-P5: file_or_update_issue never raises
    - TS-48-P6: GitLabPlatform error handling
    - TS-48-P7: Auditor issue handling never raises
    - _Test Spec: TS-48-P1 through TS-48-P7_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [ ] 2. Platform protocol and GitHubPlatform conformance
  - [ ] 2.1 Create `agent_fox/platform/protocol.py`
    - Define `Platform` protocol with `@runtime_checkable`
    - Five async methods: `search_issues`, `create_issue`, `update_issue`,
      `add_issue_comment`, `close_issue`
    - `name` property returning `str`
    - _Requirements: 48-REQ-1.1, 48-REQ-1.2, 48-REQ-1.3, 48-REQ-1.4_

  - [ ] 2.2 Add `name` property to `GitHubPlatform`
    - Add `@property def name(self) -> str: return "github"` to
      `agent_fox/platform/github.py`
    - _Requirements: 48-REQ-2.1, 48-REQ-2.2_

  - [ ] 2.3 Update `agent_fox/platform/__init__.py` exports
    - Export `Platform`, `IssueResult`, and other public names
    - _Requirements: 48-REQ-1.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/platform/test_protocol.py -x`
    - [ ] Tests TS-48-1, TS-48-2, TS-48-E1, TS-48-P1 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 48-REQ-1.*, 48-REQ-2.* acceptance criteria met

- [ ] 3. GitLabPlatform implementation
  - [ ] 3.1 Create `agent_fox/platform/gitlab.py`
    - Implement `GitLabPlatform` class with constructor accepting
      `project_id` and `token`
    - Add `name` property returning `"gitlab"`
    - Implement `_auth_headers()` using `PRIVATE-TOKEN` header
    - _Requirements: 48-REQ-3.1, 48-REQ-3.2, 48-REQ-3.4, 48-REQ-3.5_

  - [ ] 3.2 Implement GitLab issue operations
    - `search_issues()` using GET /projects/:id/issues?search=...
    - `create_issue()` using POST /projects/:id/issues
    - `update_issue()` using PUT /projects/:id/issues/:iid
    - `add_issue_comment()` using POST /projects/:id/issues/:iid/notes
    - `close_issue()` using PUT with state_event=close
    - _Requirements: 48-REQ-3.1, 48-REQ-3.3_

  - [ ] 3.3 Add `parse_gitlab_remote()` utility
    - Parse GitLab remote URLs (HTTPS and SSH)
    - Return URL-encoded `namespace/project` path
    - _Requirements: 48-REQ-4.4_

  - [ ] 3.4 Update `agent_fox/platform/__init__.py` exports
    - Export `GitLabPlatform` and `parse_gitlab_remote`
    - _Requirements: 48-REQ-3.1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/platform/test_gitlab.py -x`
    - [ ] Tests TS-48-3 through TS-48-9, TS-48-E2, TS-48-E9, TS-48-P6 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 48-REQ-3.* acceptance criteria met

- [ ] 4. Platform factory and config extension
  - [ ] 4.1 Create `agent_fox/platform/factory.py`
    - Implement `create_platform()` accepting `PlatformConfig` and repo root
    - For "github": read `GITHUB_PAT`, parse remote, create `GitHubPlatform`
    - For "gitlab": read `GITLAB_PAT`, parse remote, create `GitLabPlatform`
    - For "none": return None
    - For unknown: log warning, return None
    - _Requirements: 48-REQ-4.1, 48-REQ-4.2, 48-REQ-4.3, 48-REQ-4.4_

  - [ ] 4.2 Update `PlatformConfig` description
    - Update config_gen help text to list "gitlab" as valid type
    - _Requirements: 48-REQ-7.1, 48-REQ-7.2_

  - [ ] 4.3 Export factory from `__init__.py`
    - Export `create_platform` from `agent_fox/platform/__init__.py`
    - _Requirements: 48-REQ-4.1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/platform/test_factory.py -x`
    - [ ] Tests TS-48-10 through TS-48-12, TS-48-18, TS-48-E3 through TS-48-E5, TS-48-P2, TS-48-P3 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 48-REQ-4.*, 48-REQ-7.* acceptance criteria met

- [ ] 5. Migrate issue orchestration and clean up
  - [ ] 5.1 Create `agent_fox/platform/issues.py`
    - Move `file_or_update_issue()` from `session/github_issues.py`
    - Change type annotation from `GitHubPlatform` to `Platform`
    - Keep identical behavior
    - _Requirements: 48-REQ-5.1, 48-REQ-5.2, 48-REQ-5.3_

  - [ ] 5.2 Rename and refactor auditor issue handling
    - Rename `handle_auditor_github_issue` to `handle_auditor_issue` in
      `agent_fox/session/auditor_output.py`
    - Change `platform` type from `Any` to `Platform | None`
    - _Requirements: 48-REQ-6.1, 48-REQ-6.2, 48-REQ-6.3_

  - [ ] 5.3 Update test imports
    - Update `tests/unit/session/test_github_issues.py` to import from
      `agent_fox.platform.issues` (or move test file)
    - Update `tests/unit/session/test_skeptic.py` imports
    - Update `tests/unit/session/test_verifier.py` imports
    - Update `tests/unit/session/test_review_context.py` imports
    - Update `tests/unit/session/test_auditor.py` to use new function name
    - Update `tests/unit/engine/test_auditor_circuit_breaker.py` if needed
    - Update `tests/property/session/test_github_issues_props.py` imports
    - _Requirements: 48-REQ-8.1, 48-REQ-8.2_

  - [ ] 5.4 Delete `agent_fox/session/github_issues.py`
    - Remove the file after all imports are updated
    - Verify `format_issue_body_from_findings` is relocated or no longer needed
      (keep in session if it has session-domain callers; otherwise move
      to wherever its callers live)
    - _Requirements: 48-REQ-5.4_

  - [ ] 5.5 Update `agent_fox/platform/__init__.py` exports
    - Export `file_or_update_issue` from platform package
    - _Requirements: 48-REQ-5.1_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/platform/test_issues.py -x`
    - [ ] Tests TS-48-13 through TS-48-17, TS-48-19, TS-48-E6 through TS-48-E8, TS-48-P4, TS-48-P5, TS-48-P7 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 48-REQ-5.*, 48-REQ-6.*, 48-REQ-8.* acceptance criteria met
    - [ ] `agent_fox/session/github_issues.py` does not exist

- [ ] 6. Checkpoint - Full spec complete
  - Ensure all tests pass.
  - Update `docs/errata/` if any spec divergences arose.
  - Verify `make check` passes.

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
| 48-REQ-1.1 | TS-48-1 | 2.1, 2.3 | tests/unit/platform/test_protocol.py |
| 48-REQ-1.2 | TS-48-2, TS-48-3, TS-48-P1 | 2.1 | tests/unit/platform/test_protocol.py, tests/property/platform/test_platform_props.py |
| 48-REQ-1.3 | TS-48-2 | 2.1 | tests/unit/platform/test_protocol.py |
| 48-REQ-1.4 | TS-48-1 | 2.1 | tests/unit/platform/test_protocol.py |
| 48-REQ-1.E1 | TS-48-E1 | 2.1 | tests/unit/platform/test_protocol.py |
| 48-REQ-2.1 | TS-48-2, TS-48-P1 | 2.2 | tests/unit/platform/test_protocol.py |
| 48-REQ-2.2 | TS-48-2 | 2.2 | tests/unit/platform/test_protocol.py |
| 48-REQ-3.1 | TS-48-3 through TS-48-8 | 3.1, 3.2 | tests/unit/platform/test_gitlab.py |
| 48-REQ-3.2 | TS-48-9 | 3.1 | tests/unit/platform/test_gitlab.py |
| 48-REQ-3.3 | TS-48-4 | 3.2 | tests/unit/platform/test_gitlab.py |
| 48-REQ-3.4 | TS-48-3, TS-48-4 | 3.1 | tests/unit/platform/test_gitlab.py |
| 48-REQ-3.5 | TS-48-3 | 3.1 | tests/unit/platform/test_gitlab.py |
| 48-REQ-3.E1 | TS-48-E2, TS-48-P6 | 3.2 | tests/unit/platform/test_gitlab.py, tests/property/platform/test_platform_props.py |
| 48-REQ-3.E2 | TS-48-5, TS-48-E9 | 3.2 | tests/unit/platform/test_gitlab.py |
| 48-REQ-4.1 | TS-48-10, TS-48-P2 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.2 | TS-48-11, TS-48-P2 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.3 | TS-48-12, TS-48-P2 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.4 | TS-48-10, TS-48-11 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.E1 | TS-48-E3, TS-48-P3 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.E2 | TS-48-E4, TS-48-P3 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-4.E3 | TS-48-E5, TS-48-P3 | 4.1 | tests/unit/platform/test_factory.py |
| 48-REQ-5.1 | TS-48-13 | 5.1, 5.5 | tests/unit/platform/test_issues.py |
| 48-REQ-5.2 | TS-48-14 | 5.1 | tests/unit/platform/test_issues.py |
| 48-REQ-5.3 | TS-48-15, TS-48-P4 | 5.1 | tests/unit/platform/test_issues.py |
| 48-REQ-5.4 | TS-48-19 | 5.4 | tests/unit/platform/test_issues.py |
| 48-REQ-5.E1 | TS-48-E6, TS-48-P5 | 5.1 | tests/unit/platform/test_issues.py |
| 48-REQ-5.E2 | TS-48-E7, TS-48-P5 | 5.1 | tests/unit/platform/test_issues.py |
| 48-REQ-6.1 | TS-48-16 | 5.2 | tests/unit/platform/test_issues.py |
| 48-REQ-6.2 | TS-48-17 | 5.2 | tests/unit/platform/test_issues.py |
| 48-REQ-6.3 | TS-48-17 | 5.2 | tests/unit/platform/test_issues.py |
| 48-REQ-6.E1 | TS-48-E8, TS-48-P7 | 5.2 | tests/unit/platform/test_issues.py |
| 48-REQ-7.1 | TS-48-18 | 4.2 | tests/unit/platform/test_factory.py |
| 48-REQ-7.2 | TS-48-18 | 4.2 | tests/unit/platform/test_factory.py |
| 48-REQ-8.1 | TS-48-13 | 5.3 | tests/unit/platform/test_issues.py |
| 48-REQ-8.2 | TS-48-16 | 5.3 | tests/unit/platform/test_issues.py |

## Notes

- `format_issue_body_from_findings()` stays in the session module (or moves
  alongside its callers) since it's session-domain formatting logic.
- `parse_github_remote()` stays in `platform/github.py` — it's
  GitHub-specific and already in the right module.
- Existing tests in `tests/unit/session/test_github_issues.py` and
  `tests/property/session/test_github_issues_props.py` should be migrated to
  the new test paths or have their imports updated.
- The `auditor_output.py` module retains its `persist_auditor_results`,
  `create_circuit_breaker_issue_title`, `create_auditor_retry_event`, and
  `create_circuit_breaker_event` functions unchanged — only the
  issue-handling function is renamed.
