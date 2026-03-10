# Implementation Plan: GitHub Issue REST API Migration

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan migrates GitHub issue operations from the `gh` CLI to the REST API.
Task group 1 writes failing tests, group 2 extends `GitHubPlatform` with issue
methods, group 3 rewrites `github_issues.py` and creates errata, and group 4
is a checkpoint.

## Test Commands

- Spec tests: `uv run pytest tests/unit/platform/test_github_issues_rest.py tests/unit/session/test_github_issues.py -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/property/ -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create platform issue method tests
    - Create `tests/unit/platform/test_github_issues_rest.py`
    - Tests for `search_issues`, `create_issue`, `update_issue`,
      `add_issue_comment`, `close_issue` — mock `httpx.AsyncClient`
    - Tests for error cases (non-2xx responses raising `IntegrationError`)
    - Test for auth header consistency with `create_pr`
    - _Test Spec: TS-28-1 through TS-28-6, TS-28-11, TS-28-E1 through TS-28-E3_

  - [x] 1.2 Update session github_issues tests
    - Update `tests/unit/session/test_github_issues.py` to test against
      the new `platform` parameter interface
    - Tests for create-when-no-existing, update-when-existing,
      close-if-empty, platform-None fallback, IntegrationError swallowed
    - _Test Spec: TS-28-7 through TS-28-10, TS-28-E4, TS-28-E5_

  - [x] 1.3 Write property tests
    - Add to `tests/property/session/test_github_issues_props.py`
    - Property: no gh CLI references (source content check)
    - Property: idempotency (at most one create per title prefix)
    - Property: graceful degradation (never raises)
    - Property: auth header consistency across all issue methods
    - Property: search query correctness (required components present)
    - _Test Spec: TS-28-P1, TS-28-P2, TS-28-P3, TS-28-P4, TS-28-P5_

  - [x] 1.4 Write errata existence test
    - Test that `docs/errata/28_github_issue_rest_api.md` exists and
      references the correct spec 26 requirement IDs
    - _Test Spec: TS-28-12_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Extend GitHubPlatform with issue methods
  - [x] 2.1 Add `IssueResult` dataclass
    - Frozen dataclass with `number: int`, `title: str`, `html_url: str`
    - Add to `agent_fox/platform/github.py`
    - _Requirements: 28-REQ-2.2_

  - [x] 2.2 Implement `search_issues()`
    - `GET /search/issues` with query `repo:{owner}/{repo} in:title {prefix} state:{state} type:issue`
    - Return `list[IssueResult]`, empty list on zero results
    - Raise `IntegrationError` on non-200
    - _Requirements: 28-REQ-1.1, 28-REQ-1.2, 28-REQ-1.3, 28-REQ-1.E1, 28-REQ-1.E2_

  - [x] 2.3 Implement `create_issue()`
    - `POST /repos/{owner}/{repo}/issues` with `{title, body}`
    - Return `IssueResult` on 201, raise `IntegrationError` otherwise
    - _Requirements: 28-REQ-2.1, 28-REQ-2.2, 28-REQ-2.E1_

  - [x] 2.4 Implement `update_issue()`, `add_issue_comment()`, `close_issue()`
    - `PATCH /repos/{owner}/{repo}/issues/{N}` for update and close
    - `POST /repos/{owner}/{repo}/issues/{N}/comments` for comment
    - Raise `IntegrationError` on error
    - _Requirements: 28-REQ-3.1, 28-REQ-3.2, 28-REQ-3.E1, 28-REQ-4.1, 28-REQ-4.E1_

  - [x] 2.V Verify task group 2
    - [x] Platform issue method tests pass: `uv run pytest tests/unit/platform/test_github_issues_rest.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/platform/`
    - [x] Requirements 28-REQ-1.*, 28-REQ-2.*, 28-REQ-3.*, 28-REQ-4.* met

- [ ] 3. Rewrite github_issues.py and create errata
  - [ ] 3.1 Rewrite `file_or_update_issue()` to use `GitHubPlatform`
    - Add `platform: GitHubPlatform | None` parameter
    - Remove `repo: str | None` parameter
    - Use platform methods instead of `_run_gh_command`
    - Delete `_run_gh_command()` and `_parse_issue_number()` helpers
    - Catch `IntegrationError`, log warning, return None
    - _Requirements: 28-REQ-5.1, 28-REQ-5.2, 28-REQ-5.3, 28-REQ-5.4, 28-REQ-5.E1, 28-REQ-5.E2_

  - [ ] 3.2 Update callers of `file_or_update_issue()`
    - Update `tests/unit/session/test_skeptic.py` and `test_verifier.py`
      to use the new `platform` parameter in their mocks
    - If any production code calls `file_or_update_issue()`, update those
      call sites to pass a `GitHubPlatform` instance
    - _Requirements: 28-REQ-5.2_

  - [ ] 3.3 Create errata document
    - Create `docs/errata/28_github_issue_rest_api.md`
    - Note that 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, 26-REQ-10.E1
      now use the GitHub REST API via `GitHubPlatform` instead of `gh` CLI
    - _Requirements: 28-REQ-6.1_

  - [ ] 3.V Verify task group 3
    - [ ] All session github_issues tests pass: `uv run pytest tests/unit/session/test_github_issues.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/session/test_github_issues_props.py -q`
    - [ ] Skeptic and verifier tests pass: `uv run pytest tests/unit/session/test_skeptic.py tests/unit/session/test_verifier.py -q`
    - [ ] Errata document exists and passes content check
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 28-REQ-5.*, 28-REQ-6.* met

- [ ] 4. Checkpoint — GitHub Issue REST API Complete
  - Ensure all tests pass, ask the user if questions arise.
  - Create or update documentation in README.md or docs/ if needed.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 28-REQ-1.1 | TS-28-1, TS-28-11 | 2.2 | `test_github_issues_rest.py::TestSearchIssues` |
| 28-REQ-1.2 | TS-28-1 | 2.2 | `test_github_issues_rest.py::TestSearchIssues` |
| 28-REQ-1.3 | TS-28-1 | 2.2 | `test_github_issues_rest.py::TestSearchIssues` |
| 28-REQ-1.E1 | TS-28-E1 | 2.2 | `test_github_issues_rest.py::TestSearchIssuesError` |
| 28-REQ-1.E2 | TS-28-2 | 2.2 | `test_github_issues_rest.py::TestSearchIssuesEmpty` |
| 28-REQ-2.1 | TS-28-3 | 2.3 | `test_github_issues_rest.py::TestCreateIssue` |
| 28-REQ-2.2 | TS-28-3 | 2.3 | `test_github_issues_rest.py::TestCreateIssue` |
| 28-REQ-2.E1 | TS-28-E2 | 2.3 | `test_github_issues_rest.py::TestCreateIssueError` |
| 28-REQ-3.1 | TS-28-4 | 2.4 | `test_github_issues_rest.py::TestUpdateIssue` |
| 28-REQ-3.2 | TS-28-5 | 2.4 | `test_github_issues_rest.py::TestAddIssueComment` |
| 28-REQ-3.E1 | TS-28-E3 | 2.4 | `test_github_issues_rest.py::TestUpdateIssueError` |
| 28-REQ-4.1 | TS-28-6 | 2.4 | `test_github_issues_rest.py::TestCloseIssue` |
| 28-REQ-4.E1 | TS-28-E3 | 2.4 | `test_github_issues_rest.py::TestCloseIssueError` |
| 28-REQ-5.1 | TS-28-7, TS-28-E4 | 3.1 | `test_github_issues.py::TestFileOrUpdateIssue` |
| 28-REQ-5.2 | TS-28-7, TS-28-8 | 3.1 | `test_github_issues.py::TestFileOrUpdateIssue` |
| 28-REQ-5.3 | TS-28-7, TS-28-8, TS-28-9, TS-28-P1 | 3.1 | `test_github_issues.py`, `test_github_issues_props.py` |
| 28-REQ-5.4 | TS-28-10 | 3.1 | `test_github_issues.py::TestNoGhCliReferences` |
| 28-REQ-5.E1 | TS-28-E4 | 3.1 | `test_github_issues.py::TestPlatformNone` |
| 28-REQ-5.E2 | TS-28-E5, TS-28-P2 | 3.1 | `test_github_issues.py`, `test_github_issues_props.py` |
| 28-REQ-6.1 | TS-28-12 | 3.3 | `test_github_issues.py::TestErrataExists` |
| Property 1 | TS-28-P3 | 1.3 | `test_github_issues_props.py::TestNoGhCliRefs` |
| Property 2 | TS-28-P1 | 1.3 | `test_github_issues_props.py::TestIdempotency` |
| Property 3 | TS-28-P2 | 1.3 | `test_github_issues_props.py::TestGracefulDegradation` |
| Property 4 | TS-28-P4 | 1.3 | `test_github_issues_props.py::TestAuthConsistency` |
| Property 5 | TS-28-P5 | 1.3 | `test_github_issues_props.py::TestSearchQueryCorrectness` |

## Notes

- All `GitHubPlatform` issue methods follow the same `httpx` + `_auth_headers()`
  pattern as the existing `create_pr()`.
- Tests mock `httpx.AsyncClient` — same pattern as `test_github_rest.py`.
- The `repo: str | None` parameter on `file_or_update_issue()` is removed.
  Callers must construct a `GitHubPlatform` instance instead.
- Existing tests in `test_skeptic.py` and `test_verifier.py` that mock
  `_run_gh_command` must be updated to mock `GitHubPlatform` methods instead.
