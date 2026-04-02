# Implementation Plan: Local-Only Feature Branches

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Four task groups: (1) write failing tests, (2) update post-harvest code and
templates, (3) create erratum and update existing tests, (4) checkpoint.
The change is small enough that implementation fits in two groups plus a
checkpoint.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/engine/test_post_harvest.py tests/unit/templates/test_78_local_branches.py tests/property/templates/test_78_local_branches_props.py`
- Unit tests: `make test-unit`
- Property tests: `make test-property`
- All tests: `make test`
- Linter: `make lint`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file `tests/unit/templates/test_78_local_branches.py`
    - TS-78-4: Assert `agents_md.md` has no "pushed to `origin`"
    - TS-78-5: Assert `agents_md.md` has no "push the feature branch"
    - TS-78-6: Assert `agents_md.md` contains "local-only" guidance
    - TS-78-7: Assert `af-spec` template has no "pushed to remote"
    - TS-78-8: Assert `af-spec` git-flow line has no "-> push"
    - TS-78-9: Assert erratum file exists with 65-REQ-3.1 and 65-REQ-3.E1 references
    - _Test Spec: TS-78-4 through TS-78-9_

  - [ ] 1.2 Create unit tests for post-harvest in `tests/unit/engine/test_78_post_harvest.py`
    - TS-78-1: Assert `push_to_remote` is not called directly
    - TS-78-2: Assert `_push_develop_if_pushable` is called
    - TS-78-3: Assert `local_branch_exists` is not called
    - TS-78-E1: Assert deleted branch does not prevent develop push
    - _Test Spec: TS-78-1 through TS-78-3, TS-78-E1_

  - [ ] 1.3 Create property test file `tests/property/templates/test_78_local_branches_props.py`
    - TS-78-P1: For any branch name, `push_to_remote` not called directly
    - TS-78-P2: For any branch name, `_push_develop_if_pushable` always called
    - TS-78-P3: Agent template has no push instructions
    - TS-78-P4: Spec template has no push instructions
    - _Test Spec: TS-78-P1 through TS-78-P4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `make lint`

- [ ] 2. Implement changes
  - [ ] 2.1 Simplify `post_harvest_integrate()` in `agent_fox/workspace/harvest.py`
    - Remove the feature branch existence check (`local_branch_exists` call)
    - Remove the `push_to_remote(repo_root, feature_branch)` call
    - Remove the associated warning log for missing/failed feature branch push
    - Keep only the `_push_develop_if_pushable(repo_root)` call
    - Update docstring to reflect local-only feature branches
    - _Requirements: 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.3, 78-REQ-1.E1_

  - [ ] 2.2 Update `_templates/agents_md.md`
    - Git Workflow section: add "Feature branches are local-only — do not push them to origin."
    - Remove "push the feature branch to `origin`" from Landing instruction
    - Session Completion: replace "The feature branch is pushed to `origin`" with "Changes are merged into `develop` locally"
    - _Requirements: 78-REQ-2.1, 78-REQ-2.2, 78-REQ-2.3_

  - [ ] 2.3 Update `_templates/skills/af-spec`
    - Definition of Done item 6: change "pushed to remote" to "merged into `develop`"
    - Git-flow comment: change "merge to develop -> push" to "merge to develop"
    - _Requirements: 78-REQ-3.1, 78-REQ-3.2_

  - [ ] 2.4 Update existing post-harvest tests in `tests/unit/engine/test_post_harvest.py`
    - Update `TestPostHarvestPushesFeature` (TS-65-7) — change to assert feature branch is NOT pushed
    - Update `TestPostHarvestPushFailureBestEffort` (TS-65-11) — adjust since feature push no longer happens
    - Update `TestPostHarvestFeatureBranchDeleted` (TS-65-E3) — simplify since feature branch existence is no longer checked
    - Keep `TestPostHarvestPushesDevelop` (TS-65-8) unchanged
    - Keep `TestPostHarvestNoPlatformConfigParam` (TS-65-9) unchanged
    - Keep `TestPostHarvestNoGitHubPlatformRef` (TS-65-10) unchanged
    - _Requirements: 78-REQ-1.1, 78-REQ-1.2, 78-REQ-1.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/engine/test_78_post_harvest.py tests/unit/templates/test_78_local_branches.py tests/property/templates/test_78_local_branches_props.py`
    - [ ] All existing tests still pass: `make test`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 78-REQ-1.*, 78-REQ-2.*, 78-REQ-3.* met

- [ ] 3. Create erratum and checkpoint
  - [ ] 3.1 Create `docs/errata/65_no_feature_branch_push.md`
    - Document that 65-REQ-3.1 (push feature branch) is superseded by spec 78
    - Document that 65-REQ-3.E1 (skip push if branch deleted) is no longer applicable
    - Reference spec 78 as the source of the change
    - _Requirements: 78-REQ-4.1_

  - [ ] 3.2 Regenerate `AGENTS.md` and `CLAUDE.md` from template
    - Run `agent-fox init` in the project root or manually copy the updated template
    - Verify both files reflect the local-only branch workflow
    - _Requirements: 78-REQ-2.1, 78-REQ-2.2, 78-REQ-2.3_

  - [ ] 3.V Verify task group 3
    - [ ] Erratum file exists: `test -f docs/errata/65_no_feature_branch_push.md`
    - [ ] All tests pass: `make check`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirement 78-REQ-4.1 met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 78-REQ-1.1 | TS-78-1 | 2.1 | tests/unit/engine/test_78_post_harvest.py::test_does_not_push_feature_branch |
| 78-REQ-1.2 | TS-78-2 | 2.1 | tests/unit/engine/test_78_post_harvest.py::test_pushes_develop |
| 78-REQ-1.3 | TS-78-3 | 2.1 | tests/unit/engine/test_78_post_harvest.py::test_does_not_check_branch_existence |
| 78-REQ-1.E1 | TS-78-E1 | 2.1 | tests/unit/engine/test_78_post_harvest.py::test_deleted_branch_still_pushes_develop |
| 78-REQ-2.1 | TS-78-4 | 2.2 | tests/unit/templates/test_78_local_branches.py::test_no_pushed_to_origin |
| 78-REQ-2.2 | TS-78-5 | 2.2 | tests/unit/templates/test_78_local_branches.py::test_no_push_feature_branch |
| 78-REQ-2.3 | TS-78-6 | 2.2 | tests/unit/templates/test_78_local_branches.py::test_local_only_guidance |
| 78-REQ-3.1 | TS-78-7 | 2.3 | tests/unit/templates/test_78_local_branches.py::test_no_pushed_to_remote |
| 78-REQ-3.2 | TS-78-8 | 2.3 | tests/unit/templates/test_78_local_branches.py::test_no_push_in_git_flow |
| 78-REQ-4.1 | TS-78-9 | 3.1 | tests/unit/templates/test_78_local_branches.py::test_erratum_exists |
| Property 1 | TS-78-P1 | 2.1 | tests/property/templates/test_78_local_branches_props.py::test_never_pushes_feature |
| Property 2 | TS-78-P2 | 2.1 | tests/property/templates/test_78_local_branches_props.py::test_always_pushes_develop |
| Property 3 | TS-78-P3 | 2.2 | tests/property/templates/test_78_local_branches_props.py::test_agent_template_no_push |
| Property 4 | TS-78-P4 | 2.3 | tests/property/templates/test_78_local_branches_props.py::test_spec_template_no_push |
