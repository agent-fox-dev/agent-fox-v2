# Implementation Plan: Issue Session Summary

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec adds a post-completion hook that posts a roll-up summary
comment to the originating GitHub issue when all task groups of a spec
are fully implemented. The implementation is small and self-contained:
one new module (`issue_summary.py`), one new factory function
(`create_platform_safe`), and minor wiring changes to the orchestrator
and infrastructure setup.

## Test Commands

- Unit tests: `uv run pytest -q tests/unit/engine/test_issue_summary.py tests/unit/nightshift/test_platform_factory_safe.py`
- Integration tests: `uv run pytest -q tests/integration/engine/test_issue_summary_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Add parse_source_url unit tests to test_issue_summary.py
    - TestParseSourceUrl: TS-108-1, TS-108-2, TS-108-3, TS-108-4, TS-108-5
    - TestParseSourceUrlEdgeCases: TS-108-E1, TS-108-E2
    - _Test Spec: TS-108-1 through TS-108-5, TS-108-E1, TS-108-E2_

  - [x] 1.2 Add build_summary_comment unit tests to test_issue_summary.py
    - TestBuildSummaryComment: TS-108-6, TS-108-7
    - _Test Spec: TS-108-6, TS-108-7_

  - [x] 1.3 Add post_issue_summaries unit tests to test_issue_summary.py
    - TestPostIssueSummaries: TS-108-8, TS-108-9, TS-108-10, TS-108-11
    - TestPostIssueSummariesForgeMismatch: TS-108-17
    - _Test Spec: TS-108-8 through TS-108-11, TS-108-17_

  - [x] 1.4 Add get_develop_head unit tests to test_issue_summary.py
    - TestGetDevelopHead: TS-108-15, TS-108-16
    - _Test Spec: TS-108-15, TS-108-16_

  - [x] 1.5 Add create_platform_safe unit tests
    - TestCreatePlatformSafe: TS-108-12, TS-108-13, TS-108-14
    - File: tests/unit/nightshift/test_platform_factory_safe.py
    - _Test Spec: TS-108-12 through TS-108-14_

  - [x] 1.6 Add orchestrator integration tests
    - TestOrchestratorSkipsWhenNoPlatform: TS-108-E3
    - TestEndToEndIssueSummary: TS-108-SMOKE-1
    - File: tests/integration/engine/test_issue_summary_smoke.py
    - _Test Spec: TS-108-E3, TS-108-SMOKE-1_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced

- [ ] 2. Implement issue_summary module
  - [ ] 2.1 Create `agent_fox/engine/issue_summary.py`
    - Define `SourceIssue` dataclass
    - Implement `parse_source_url(prd_path)` with GitHub regex
    - _Requirements: 108-REQ-1.1, 108-REQ-1.2, 108-REQ-1.3, 108-REQ-1.E1,
      108-REQ-1.E2, 108-REQ-1.E3_

  - [ ] 2.2 Implement `_get_develop_head(repo_root)`
    - Run `git rev-parse develop` via subprocess
    - Return `"unknown"` on failure
    - _Requirements: 108-REQ-6.1, 108-REQ-6.E1_

  - [ ] 2.3 Implement `build_summary_comment(spec_name, commit_sha, tasks_path)`
    - Use `parse_tasks()` to extract group titles
    - Format as Markdown with spec name, commit SHA, task list, footer
    - _Requirements: 108-REQ-3.1, 108-REQ-3.2, 108-REQ-3.3, 108-REQ-3.4_

  - [ ] 2.4 Implement `post_issue_summaries(platform, specs_dir, completed_specs, already_posted, repo_root)`
    - Iterate newly completed specs (completed - already_posted)
    - Call parse_source_url, build_summary_comment, add_issue_comment
    - Handle failures gracefully (warn + skip)
    - Check forge type matches platform
    - _Requirements: 108-REQ-2.1, 108-REQ-2.2, 108-REQ-4.1, 108-REQ-4.E1,
      108-REQ-4.E2, 108-REQ-2.E1_

  - [ ] 2.V Verify task group 2
    - [ ] parse_source_url tests pass
    - [ ] build_summary_comment tests pass
    - [ ] post_issue_summaries tests pass
    - [ ] get_develop_head tests pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

- [ ] 3. Wire platform into orchestrator
  - [ ] 3.1 Add `create_platform_safe()` to `nightshift/platform_factory.py`
    - Return `None` instead of `sys.exit(1)` when platform not configured
    - Return `None` when `GITHUB_PAT` is missing
    - _Requirements: 108-REQ-5.3_

  - [ ] 3.2 Update `_setup_infrastructure()` in `engine/run.py`
    - Call `create_platform_safe()` and include result in infra dict
    - Pass `platform` to orchestrator kwargs
    - _Requirements: 108-REQ-5.1_

  - [ ] 3.3 Update `Orchestrator.__init__()` in `engine/engine.py`
    - Accept optional `platform: PlatformProtocol | None = None`
    - Store as `self._platform`
    - Initialize `self._issue_summaries_posted: set[str] = set()`
    - _Requirements: 108-REQ-5.2_

  - [ ] 3.4 Add `post_issue_summaries()` call to Orchestrator `run()` finally block
    - After existing cleanup (audit, consolidation, memory rendering)
    - Guard with `if self._platform is not None`
    - _Requirements: 108-REQ-4.2, 108-REQ-5.E1_

  - [ ] 3.V Verify task group 3
    - [ ] create_platform_safe tests pass
    - [ ] Orchestrator integration tests pass
    - [ ] Smoke test passes
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

- [ ] 4. Wiring verification
  - [ ] 4.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next
      function in the chain
    - Confirm no function in the chain is a stub
    - _Requirements: all_

  - [ ] 4.2 Verify return values propagate correctly
    - `parse_source_url()` result consumed by `post_issue_summaries()`
    - `build_summary_comment()` result passed to `add_issue_comment()`
    - `_get_develop_head()` result included in comment body
    - `post_issue_summaries()` return value updates `_issue_summaries_posted`
    - _Requirements: all_

  - [ ] 4.3 Run the integration smoke test
    - TS-108-SMOKE-1 passes using real components (no stub bypass)
    - _Test Spec: TS-108-SMOKE-1_

  - [ ] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced

  - [ ] 4.5 Cross-spec entry point verification
    - Verify `Orchestrator.run()` calls `post_issue_summaries()` in the
      finally block
    - Verify `_setup_infrastructure()` calls `create_platform_safe()`
    - Verify `create_platform_safe()` returns a platform or `None`

  - [ ] 4.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live
    - [ ] All existing tests still pass: `uv run pytest -q`

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
| 108-REQ-1.1 | TS-108-1, TS-108-E2 | 2.1 | test_parse_source_url_github |
| 108-REQ-1.2 | TS-108-1 | 2.1 | test_parse_source_url_github |
| 108-REQ-1.3 | TS-108-5 | 2.1 | test_parse_source_url_pure |
| 108-REQ-1.E1 | TS-108-3, TS-108-E1 | 2.1 | test_parse_source_url_no_source |
| 108-REQ-1.E2 | TS-108-4 | 2.1 | test_parse_source_url_non_url |
| 108-REQ-1.E3 | TS-108-2 | 2.1 | test_parse_source_url_missing_file |
| 108-REQ-2.1 | TS-108-8 | 2.4 | test_post_issue_summaries |
| 108-REQ-2.2 | TS-108-8 | 2.4 | test_post_issue_summaries |
| 108-REQ-2.E1 | TS-108-9 | 2.4 | test_skips_already_posted |
| 108-REQ-3.1 | TS-108-6 | 2.3 | test_build_summary_comment |
| 108-REQ-3.2 | TS-108-6 | 2.3 | test_build_summary_comment |
| 108-REQ-3.3 | TS-108-6 | 2.3 | test_build_summary_comment |
| 108-REQ-3.4 | TS-108-6, TS-108-7 | 2.3 | test_build_summary_comment |
| 108-REQ-4.1 | TS-108-8, TS-108-SMOKE-1 | 2.4, 3.4 | test_post_issue_summaries |
| 108-REQ-4.2 | TS-108-SMOKE-1 | 3.4 | test_end_to_end_smoke |
| 108-REQ-4.E1 | TS-108-11 | 2.4 | test_handles_comment_failure |
| 108-REQ-4.E2 | TS-108-17 | 2.4 | test_skips_forge_mismatch |
| 108-REQ-5.1 | TS-108-14 | 3.1, 3.2 | test_create_platform_safe |
| 108-REQ-5.2 | TS-108-E3 | 3.3 | test_orchestrator_no_platform |
| 108-REQ-5.3 | TS-108-12, TS-108-13 | 3.1 | test_create_platform_safe_* |
| 108-REQ-5.E1 | TS-108-E3 | 3.4 | test_orchestrator_no_platform |
| 108-REQ-6.1 | TS-108-15 | 2.2 | test_get_develop_head |
| 108-REQ-6.E1 | TS-108-16 | 2.2 | test_get_develop_head_failure |

## Notes

- This spec has no cross-spec dependencies — all upstream infrastructure
  (orchestrator, platform protocol, GraphSync) is already implemented
  and stable.
- The `create_platform_safe()` function should be added alongside the
  existing `create_platform()` in the same file, not as a replacement.
- The orchestrator's `finally` block already has a pattern of
  best-effort cleanup calls (audit cleanup, consolidation, memory
  rendering). The issue summary posting follows the same pattern.
