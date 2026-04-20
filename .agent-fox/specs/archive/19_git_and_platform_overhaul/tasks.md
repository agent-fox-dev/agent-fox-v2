# Implementation Plan: Git and Platform Overhaul

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec is implemented in 7 task groups: failing tests first, then develop
branch management, prompt template updates, git push operations, platform
simplification, post-harvest integration wiring, and cleanup. Groups are ordered
so that foundational git operations come before the platform and lifecycle
changes that depend on them.

## Test Commands

- Unit tests: `uv run pytest tests/unit/workspace/ tests/unit/platform/ tests/unit/engine/ -q`
- Property tests: `uv run pytest tests/property/platform/ -q`
- Spec tests: `uv run pytest tests/unit/ tests/property/ -k "test_ensure_develop or test_push_to_remote or test_detect_default or test_parse_github or test_post_harvest or test_platform_config or test_git_flow or test_coding_template or test_github_platform" -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create/update test directory structure
    - Ensure `tests/unit/workspace/`, `tests/unit/platform/`, `tests/unit/engine/`, `tests/property/platform/` directories exist with `__init__.py`
    - Create `tests/unit/workspace/test_git_ensure.py` for TS-19-1 through TS-19-6 and TS-19-E1 through TS-19-E4
    - _Test Spec: TS-19-1, TS-19-2, TS-19-3, TS-19-4, TS-19-5, TS-19-6_

  - [x] 1.2 Write push and post-harvest tests
    - `tests/unit/workspace/test_git_push.py`: TS-19-6 (push success), TS-19-7 (push failure)
    - `tests/unit/engine/test_post_harvest.py`: TS-19-10 (no platform), TS-19-11 (auto_merge), TS-19-12 (PR creation)
    - _Test Spec: TS-19-6, TS-19-7, TS-19-10, TS-19-11, TS-19-12_

  - [x] 1.3 Write GitHub platform and URL parsing tests
    - `tests/unit/platform/test_github_rest.py`: TS-19-13 (create_pr via REST), TS-19-14 (HTTPS parse), TS-19-15 (SSH parse)
    - _Test Spec: TS-19-13, TS-19-14, TS-19-15_

  - [x] 1.4 Write config and template tests
    - `tests/unit/platform/test_platform_config.py`: TS-19-16 (simplified config)
    - `tests/unit/prompts/test_template_content.py`: TS-19-8 (git-flow.md), TS-19-9 (coding.md)
    - _Test Spec: TS-19-8, TS-19-9, TS-19-16_

  - [x] 1.5 Write edge case tests
    - Add to `test_git_ensure.py`: TS-19-E1 (already exists), TS-19-E2 (no default branch), TS-19-E3 (fetch fails), TS-19-E4 (diverged)
    - Add to `test_post_harvest.py`: TS-19-E5 (push failure continues), TS-19-E6 (PR failure continues), TS-19-E11 (deleted branch)
    - `tests/unit/platform/test_github_rest.py`: TS-19-E7 (no PAT fallback), TS-19-E8 (API 401), TS-19-E9 (non-GitHub URL)
    - `tests/unit/platform/test_platform_config.py`: TS-19-E10 (old fields ignored)
    - _Test Spec: TS-19-E1 through TS-19-E11_

  - [x] 1.6 Write property tests
    - `tests/property/platform/test_overhaul_props.py`: TS-19-P1 (no push in templates), TS-19-P2 (URL parsing), TS-19-P3 (config backward compat), TS-19-P4 (post-harvest strategy)
    - _Test Spec: TS-19-P1, TS-19-P2, TS-19-P3, TS-19-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement robust develop branch management
  - [x] 2.1 Add `local_branch_exists` to git.py
    - Async function checking if a local branch exists via `git branch --list`
    - _Requirements: 19-REQ-1.1_

  - [x] 2.2 Add `remote_branch_exists` to git.py
    - Async function checking if a branch exists on a remote after fetch
    - _Requirements: 19-REQ-1.1_

  - [x] 2.3 Add `detect_default_branch` to git.py
    - Try `git symbolic-ref refs/remotes/origin/HEAD`, parse branch name
    - Fall back to checking local `main`, then `master`
    - Raise `WorkspaceError` if none found
    - _Requirements: 19-REQ-1.4_

  - [x] 2.4 Add `ensure_develop` to git.py
    - Fetch origin (warn on failure)
    - If local develop exists: fast-forward if behind remote, warn if diverged
    - If no local develop: create from origin/develop or default branch
    - _Requirements: 19-REQ-1.1, 19-REQ-1.2, 19-REQ-1.3, 19-REQ-1.5, 19-REQ-1.6_

  - [x] 2.5 Update `cli/init.py` to use new ensure logic
    - Replace `_ensure_develop_branch()` with a call to `ensure_develop()` (sync wrapper if needed since init is synchronous)
    - _Requirements: 19-REQ-1.5_

  - [x] 2.6 Call `ensure_develop` before worktree creation in session lifecycle
    - Add call in `NodeSessionRunner.execute()` before `create_worktree()`
    - _Requirements: 19-REQ-1.1, 19-REQ-1.6_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/workspace/test_git_ensure.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/workspace/ agent_fox/cli/ agent_fox/engine/`
    - [x] Requirements 19-REQ-1.* acceptance criteria met

- [x] 3. Remove push instructions from agent prompts
  - [x] 3.1 Update git-flow.md
    - Remove `git push origin feature/<task-name>` from "Session Landing Commands"
    - Update "Required End State" to require clean working tree only, not pushed
    - _Requirements: 19-REQ-2.1, 19-REQ-2.2, 19-REQ-2.3_

  - [x] 3.2 Update coding.md
    - Remove `git push origin HEAD` from STEP 9
    - Remove FAILURE POLICY section about push retries
    - Update STEP 9 to only require commit + clean tree
    - _Requirements: 19-REQ-2.4, 19-REQ-2.5_

  - [x] 3.3 Audit other templates for push references
    - Check coordinator.md and any other templates in `_templates/prompts/`
    - Remove any remaining push references
    - _Requirements: 19-REQ-2.E1_

  - [x] 3.V Verify task group 3
    - [x] Template tests pass: `uv run pytest tests/unit/prompts/ -q`
    - [x] Property test passes: `uv run pytest tests/property/platform/test_overhaul_props.py -k "push_instructions" -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`

- [x] 4. Implement git push and GitHub REST API platform
  - [x] 4.1 Add `push_to_remote` to git.py
    - Async function: `git push {remote} {branch}`
    - Returns True/False, never raises; logs warning on failure
    - _Requirements: 19-REQ-3.1_

  - [x] 4.2 Add `parse_github_remote` utility
    - In `agent_fox/platform/github.py`
    - Parse owner/repo from HTTPS and SSH GitHub URLs
    - Return None for non-GitHub URLs
    - _Requirements: 19-REQ-4.4_

  - [x] 4.3 Rewrite GitHubPlatform with REST API
    - Remove all `gh` CLI code, `_run_gh`, `_verify_gh_available`
    - Constructor takes owner, repo, token
    - `create_pr` uses httpx to POST `/repos/{owner}/{repo}/pulls`
    - Remove `wait_for_ci`, `wait_for_review`, `merge_pr`
    - _Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3_

  - [x] 4.4 Simplify Platform protocol
    - Remove `wait_for_ci`, `wait_for_review`, `merge_pr` from protocol
    - Keep only `create_pr` with simplified signature (no labels param)
    - _Requirements: 19-REQ-6.2_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest tests/unit/platform/test_github_rest.py tests/unit/workspace/test_git_push.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/platform/test_overhaul_props.py -k "url_parsing" -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/platform/ agent_fox/workspace/`
    - [x] Requirements 19-REQ-4.* acceptance criteria met

- [x] 5. Simplify config and remove dead code
  - [x] 5.1 Simplify PlatformConfig
    - Remove `wait_for_ci`, `wait_for_review`, `ci_timeout`, `pr_granularity`, `labels` fields
    - Keep `type` and `auto_merge` only
    - Verify `extra = "ignore"` allows old fields
    - _Requirements: 19-REQ-5.1, 19-REQ-5.2, 19-REQ-5.3, 19-REQ-5.E1_

  - [x] 5.2 Delete NullPlatform
    - Delete `agent_fox/platform/null.py`
    - _Requirements: 19-REQ-6.1_

  - [x] 5.3 Delete factory
    - Delete `agent_fox/platform/factory.py`
    - _Requirements: 19-REQ-6.3_

  - [x] 5.4 Update platform package init
    - Remove `NullPlatform`, `create_platform` from exports
    - Export `GitHubPlatform`, `Platform`, `parse_github_remote`
    - _Requirements: 19-REQ-6.3_

  - [x] 5.5 Remove old platform tests
    - Delete or update `tests/unit/platform/test_null.py`, `test_factory.py`, `test_protocol.py`
    - Update `tests/unit/platform/test_github.py` to remove tests for deleted methods
    - Update `tests/property/platform/test_platform_props.py` to remove tests for deleted code
    - _Requirements: 19-REQ-6.4_

  - [x] 5.V Verify task group 5
    - [x] Config tests pass: `uv run pytest tests/unit/platform/test_platform_config.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 19-REQ-5.*, 19-REQ-6.* acceptance criteria met

- [x] 6. Wire post-harvest integration into session lifecycle
  - [x] 6.1 Implement `_post_harvest_integrate` in session_lifecycle.py
    - After successful harvest: determine strategy from platform config
    - type="none": push develop to origin
    - type="github" + auto_merge=true: push feature + push develop
    - type="github" + auto_merge=false: push feature + create PR
    - All remote operations are best-effort (warn on failure, never raise)
    - Check GITHUB_PAT availability; fall back to no-platform if missing
    - Parse remote URL for owner/repo; fall back if non-GitHub
    - _Requirements: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3, 19-REQ-3.4_

  - [x] 6.2 Call `_post_harvest_integrate` from `_run_and_harvest`
    - Add call after successful harvest, before returning the SessionRecord
    - Pass platform config from `self._config.platform`
    - _Requirements: 19-REQ-3.4_

  - [x] 6.3 Handle edge cases in post-harvest integration
    - Check if feature branch exists before pushing (19-REQ-3.E3)
    - Catch and warn on push failures (19-REQ-3.E1)
    - Catch and warn on PR creation failures (19-REQ-3.E2)
    - Handle missing GITHUB_PAT (19-REQ-4.E1)
    - Handle non-GitHub remotes (19-REQ-4.E4)
    - _Requirements: 19-REQ-3.E1, 19-REQ-3.E2, 19-REQ-3.E3, 19-REQ-4.E1, 19-REQ-4.E2, 19-REQ-4.E4_

  - [x] 6.V Verify task group 6
    - [x] Post-harvest tests pass: `uv run pytest tests/unit/engine/test_post_harvest.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/`
    - [x] Requirements 19-REQ-3.*, 19-REQ-4.E* acceptance criteria met

- [x] 7. Checkpoint — Git and Platform Overhaul Complete
  - [x] All spec tests pass: `uv run pytest tests/unit/ tests/property/ -k "test_ensure_develop or test_push_to_remote or test_detect_default or test_parse_github or test_post_harvest or test_platform_config or test_git_flow or test_coding_template or test_github_platform or overhaul" -q`
  - [x] All tests pass: `uv run pytest -q`
  - [x] All linter checks pass: `uv run ruff check agent_fox/ tests/`
  - [x] Verify `agent_fox/platform/null.py` and `agent_fox/platform/factory.py` are deleted
  - [x] Verify `PlatformConfig` only has `type` and `auto_merge` fields
  - [x] Verify no `git push` in any template file
  - [x] Verify `ensure_develop` is called before session start
  - [x] Add supersession banner to all files in `.specs/10_platform_integration/`

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
| 19-REQ-1.1 | TS-19-1 | 2.4, 2.6 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.2 | TS-19-1 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.3 | TS-19-2 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.4 | TS-19-4, TS-19-5 | 2.3 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.5 | TS-19-2 | 2.5 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.6 | TS-19-3 | 2.4, 2.6 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.E1 | TS-19-E1 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.E2 | TS-19-E2 | 2.3 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.E3 | TS-19-E3 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-1.E4 | TS-19-E4 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| 19-REQ-2.1 | TS-19-8, TS-19-P1 | 3.1 | tests/unit/prompts/test_template_content.py |
| 19-REQ-2.2 | TS-19-8 | 3.1 | tests/unit/prompts/test_template_content.py |
| 19-REQ-2.3 | TS-19-8 | 3.1 | tests/unit/prompts/test_template_content.py |
| 19-REQ-2.4 | TS-19-9, TS-19-P1 | 3.2 | tests/unit/prompts/test_template_content.py |
| 19-REQ-2.5 | TS-19-9 | 3.2 | tests/unit/prompts/test_template_content.py |
| 19-REQ-2.E1 | TS-19-P1 | 3.3 | tests/property/platform/test_overhaul_props.py |
| 19-REQ-3.1 | TS-19-6, TS-19-10, TS-19-P4 | 4.1, 6.1 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.2 | TS-19-11, TS-19-P4 | 6.1 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.3 | TS-19-12, TS-19-P4 | 6.1 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.4 | TS-19-10 | 6.2 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.E1 | TS-19-7, TS-19-E5 | 4.1, 6.3 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.E2 | TS-19-E6 | 6.3 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-3.E3 | TS-19-E11 | 6.3 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-4.1 | TS-19-13 | 4.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.2 | TS-19-13 | 4.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.3 | TS-19-13 | 4.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.4 | TS-19-14, TS-19-15, TS-19-P2 | 4.2 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.E1 | TS-19-E7 | 6.3 | tests/unit/engine/test_post_harvest.py |
| 19-REQ-4.E2 | TS-19-E8 | 4.3, 6.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.E3 | TS-19-E8 | 4.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-4.E4 | TS-19-E9, TS-19-P2 | 4.2, 6.3 | tests/unit/platform/test_github_rest.py |
| 19-REQ-5.1 | TS-19-16 | 5.1 | tests/unit/platform/test_platform_config.py |
| 19-REQ-5.2 | TS-19-16 | 5.1 | tests/unit/platform/test_platform_config.py |
| 19-REQ-5.3 | TS-19-16 | 5.1 | tests/unit/platform/test_platform_config.py |
| 19-REQ-5.E1 | TS-19-E10, TS-19-P3 | 5.1 | tests/unit/platform/test_platform_config.py |
| 19-REQ-6.1 | — | 5.2 | (verified by deletion) |
| 19-REQ-6.2 | — | 4.4 | (verified by protocol change) |
| 19-REQ-6.3 | — | 5.3 | (verified by deletion) |
| 19-REQ-6.4 | — | 5.5 | (verified by test updates) |
| Property 1 | TS-19-1, TS-19-2, TS-19-E1 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| Property 2 | TS-19-3 | 2.4 | tests/unit/workspace/test_git_ensure.py |
| Property 3 | TS-19-P1 | 3.1, 3.2, 3.3 | tests/property/platform/test_overhaul_props.py |
| Property 4 | TS-19-P4 | 6.1 | tests/property/platform/test_overhaul_props.py |
| Property 5 | TS-19-E7 | 6.3 | tests/unit/engine/test_post_harvest.py |
| Property 6 | TS-19-P2 | 4.2 | tests/property/platform/test_overhaul_props.py |
| Property 7 | TS-19-P3 | 5.1 | tests/property/platform/test_overhaul_props.py |

## Notes

- All git operations are mocked via `run_git` patches. No real git repos in tests.
- All HTTP calls are mocked via httpx mock/respx. No real GitHub API calls.
- The `ensure_develop` function is async but `af init` is synchronous — use `asyncio.run()` or a sync wrapper in `cli/init.py`.
- Task group 5 (config + dead code removal) may cause existing spec-10 tests to fail. Those tests should be deleted or updated as part of subtask 5.5.
- The supersession banner for spec 10 files is added in the final checkpoint (task group 7).
