# Implementation Plan: Session and Workspace

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the session execution and workspace isolation layer:
git worktree management, coding session execution via the claude-code-sdk,
context assembly, prompt building, timeout enforcement, and the harvester.
Task groups build up from tests to git operations to session runner to
harvester.

## Test Commands

- Unit tests: `uv run pytest tests/unit/workspace/ tests/unit/session/ -q`
- Property tests: `uv run pytest tests/property/workspace/ tests/property/session/ -q`
- All spec tests: `uv run pytest tests/unit/workspace/ tests/unit/session/ tests/property/workspace/ tests/property/session/ -q`
- Linter: `uv run ruff check agent_fox/workspace/ agent_fox/session/`
- Type check: `uv run mypy agent_fox/workspace/ agent_fox/session/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure and fixtures
    - Create `tests/unit/workspace/__init__.py`
    - Create `tests/unit/session/__init__.py`
    - Create `tests/property/workspace/__init__.py`
    - Create `tests/property/session/__init__.py`
    - Create `tests/conftest.py` additions (or a new
      `tests/unit/workspace/conftest.py`) with shared fixtures:
      `tmp_git_repo` (temp dir with `git init`, initial commit, develop
      branch), `tmp_worktree_repo` (extends tmp_git_repo with
      `.agent-fox/worktrees/` directory)
    - Create `tests/unit/session/conftest.py` with fixtures:
      `tmp_spec_dir` (temp dir with sample spec files), `mock_query`
      (mock for claude-code-sdk query), `default_config`
      (AgentFoxConfig with test-friendly defaults)

  - [x] 1.2 Write worktree management tests
    - `tests/unit/workspace/test_worktree.py`:
      TS-03-1 (creation), TS-03-2 (destruction), TS-03-3 (stale removal)
    - _Test Spec: TS-03-1, TS-03-2, TS-03-3_

  - [x] 1.3 Write context assembly tests
    - `tests/unit/session/test_context.py`:
      TS-03-4 (spec docs), TS-03-5 (memory facts)
    - _Test Spec: TS-03-4, TS-03-5_

  - [x] 1.4 Write prompt builder tests
    - `tests/unit/session/test_prompt.py`:
      TS-03-6 (system and task prompts)
    - _Test Spec: TS-03-6_

  - [x] 1.5 Write session runner tests
    - `tests/unit/session/test_runner.py`:
      TS-03-7 (success), TS-03-8 (SDK error), TS-03-9 (timeout)
    - _Test Spec: TS-03-7, TS-03-8, TS-03-9_

  - [x] 1.6 Write allowlist hook tests
    - `tests/unit/session/test_runner.py` (or separate
      `tests/unit/session/test_security.py`):
      TS-03-12 (allowlist enforcement)
    - _Test Spec: TS-03-12_

  - [x] 1.7 Write harvester tests
    - `tests/unit/workspace/test_harvester.py`:
      TS-03-10 (fast-forward merge), TS-03-11 (rebase on conflict)
    - _Test Spec: TS-03-10, TS-03-11_

  - [x] 1.8 Write edge case tests
    - `tests/unit/workspace/test_worktree.py`: TS-03-E1 (git error),
      TS-03-E2 (destroy non-existent)
    - `tests/unit/session/test_runner.py`: TS-03-E3 (is_error result)
    - `tests/unit/session/test_context.py`: TS-03-E4 (missing spec file)
    - `tests/unit/workspace/test_harvester.py`: TS-03-E5 (no commits),
      TS-03-E6 (unresolvable conflict)
    - `tests/unit/session/test_runner.py` or
      `tests/unit/session/test_security.py`: TS-03-E7 (empty command)
    - _Test Spec: TS-03-E1 through TS-03-E7_

  - [x] 1.9 Write property tests
    - `tests/property/workspace/test_worktree_props.py`:
      TS-03-P1 (path uniqueness)
    - `tests/property/session/test_runner_props.py`:
      TS-03-P2 (outcome fields)
    - `tests/property/session/test_security_props.py`:
      TS-03-P3 (allowlist enforcement)
    - _Test Spec: TS-03-P1, TS-03-P2, TS-03-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Implement git operations and worktree management
  - [ ] 2.1 Create git operations module
    - `agent_fox/workspace/__init__.py`
    - `agent_fox/workspace/git.py`: `run_git()`, `create_branch()`,
      `delete_branch()`, `checkout_branch()`, `has_new_commits()`,
      `get_changed_files()`, `merge_fast_forward()`, `rebase_onto()`,
      `abort_rebase()`
    - All functions are async, use `asyncio.create_subprocess_exec` to
      run git commands
    - Error handling: wrap failures in `WorkspaceError` or
      `IntegrationError` with stderr context
    - _Requirements: 03-REQ-9.1, 03-REQ-9.2_

  - [ ] 2.2 Create worktree manager
    - `agent_fox/workspace/worktree.py`: `WorkspaceInfo` dataclass,
      `create_worktree()`, `destroy_worktree()`
    - Create worktree: handle stale worktree/branch cleanup, create
      feature branch from base, add worktree
    - Destroy worktree: remove worktree via `git worktree remove`,
      prune, delete branch, clean up empty dirs
    - _Requirements: 03-REQ-1.1 through 03-REQ-1.E3, 03-REQ-2.1
      through 03-REQ-2.E2_

  - [ ] 2.V Verify task group 2
    - [ ] Worktree tests pass:
      `uv run pytest tests/unit/workspace/test_worktree.py -q`
    - [ ] Property tests pass:
      `uv run pytest tests/property/workspace/ -q`
    - [ ] No linter warnings:
      `uv run ruff check agent_fox/workspace/`
    - [ ] Requirements 03-REQ-1.*, 03-REQ-2.*, 03-REQ-9.* met

- [ ] 3. Implement context, prompt, timeout, and session runner
  - [ ] 3.1 Create context assembler
    - `agent_fox/session/__init__.py`
    - `agent_fox/session/context.py`: `assemble_context()` function
    - Read spec files (requirements.md, design.md, tasks.md) from the
      spec directory; skip missing files with a warning
    - Format output with clear section headers
    - Append memory facts in a labeled section
    - _Requirements: 03-REQ-4.1 through 03-REQ-4.E1_

  - [ ] 3.2 Create prompt builder
    - `agent_fox/session/prompt.py`: `build_system_prompt()`,
      `build_task_prompt()`
    - System prompt: agent role, context insertion, task group
      reference, instructions to follow spec acceptance criteria,
      commit on feature branch, run quality checks
    - Task prompt: identify the target task group, reference tasks.md
    - _Requirements: 03-REQ-5.1, 03-REQ-5.2_

  - [ ] 3.3 Create timeout enforcer
    - `agent_fox/session/timeout.py`: `with_timeout()` function
    - Wraps a coroutine with `asyncio.wait_for()`, converting minutes
      to seconds
    - _Requirements: 03-REQ-6.1, 03-REQ-6.2_

  - [ ] 3.4 Create session runner
    - `agent_fox/session/runner.py`: `SessionOutcome` dataclass,
      `run_session()`, `build_allowlist_hook()`
    - Build `ClaudeAgentOptions` with cwd, model, system_prompt,
      permission_mode, hooks
    - Call `query()` and iterate messages, collecting the last
      `ResultMessage`
    - Wrap in timeout via `with_timeout()`
    - Handle `asyncio.TimeoutError` -> status "timeout"
    - Handle `ClaudeSDKError` -> status "failed"
    - Handle `ResultMessage.is_error` -> status "failed"
    - Build allowlist hook: PreToolUse matcher for Bash tool,
      extract first command token, block if not in allowlist
    - _Requirements: 03-REQ-3.1 through 03-REQ-3.E2, 03-REQ-6.E1,
      03-REQ-8.1 through 03-REQ-8.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Context tests pass:
      `uv run pytest tests/unit/session/test_context.py -q`
    - [ ] Prompt tests pass:
      `uv run pytest tests/unit/session/test_prompt.py -q`
    - [ ] Runner tests pass:
      `uv run pytest tests/unit/session/test_runner.py -q`
    - [ ] Property tests pass:
      `uv run pytest tests/property/session/ -q`
    - [ ] No linter warnings:
      `uv run ruff check agent_fox/session/`
    - [ ] Requirements 03-REQ-3.* through 03-REQ-8.* met

- [ ] 4. Implement harvester
  - [ ] 4.1 Create harvester module
    - `agent_fox/workspace/harvester.py`: `harvest()` function
    - Check for new commits; no-op if none
    - Checkout dev branch in main repo
    - Attempt fast-forward merge
    - On failure: rebase feature branch onto dev, retry merge
    - On rebase failure: abort rebase, raise IntegrationError
    - Return list of changed files on success
    - _Requirements: 03-REQ-7.1 through 03-REQ-7.E2_

  - [ ] 4.V Verify task group 4
    - [ ] Harvester tests pass:
      `uv run pytest tests/unit/workspace/test_harvester.py -q`
    - [ ] No linter warnings:
      `uv run ruff check agent_fox/workspace/harvester.py`
    - [ ] Requirements 03-REQ-7.* met

- [ ] 5. Checkpoint -- Session and Workspace Complete
  - All spec tests pass:
    `uv run pytest tests/unit/workspace/ tests/unit/session/ -q`
  - All property tests pass:
    `uv run pytest tests/property/workspace/ tests/property/session/ -q`
  - All previously passing tests still pass:
    `uv run pytest tests/ -q`
  - Linter clean:
    `uv run ruff check agent_fox/workspace/ agent_fox/session/`
  - Type check clean:
    `uv run mypy agent_fox/workspace/ agent_fox/session/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 03-REQ-1.1 | TS-03-1, TS-03-P1 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-1.2 | TS-03-1, TS-03-P1 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-1.3 | TS-03-1 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-1.E1 | TS-03-3 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-1.E2 | TS-03-3 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-1.E3 | TS-03-E1 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-2.1 | TS-03-2 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-2.2 | TS-03-2 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-2.E1 | TS-03-E2 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-2.E2 | TS-03-E2 | 2.2 | tests/unit/workspace/test_worktree.py |
| 03-REQ-3.1 | TS-03-7 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-3.2 | TS-03-7 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-3.3 | TS-03-7, TS-03-P2 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-3.4 | TS-03-12 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-3.E1 | TS-03-8 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-3.E2 | TS-03-E3 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-4.1 | TS-03-4 | 3.1 | tests/unit/session/test_context.py |
| 03-REQ-4.2 | TS-03-5 | 3.1 | tests/unit/session/test_context.py |
| 03-REQ-4.3 | TS-03-4, TS-03-5 | 3.1 | tests/unit/session/test_context.py |
| 03-REQ-4.E1 | TS-03-E4 | 3.1 | tests/unit/session/test_context.py |
| 03-REQ-5.1 | TS-03-6 | 3.2 | tests/unit/session/test_prompt.py |
| 03-REQ-5.2 | TS-03-6 | 3.2 | tests/unit/session/test_prompt.py |
| 03-REQ-6.1 | TS-03-9 | 3.3, 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-6.2 | TS-03-9 | 3.3, 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-6.E1 | TS-03-9 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-7.1 | TS-03-10 | 4.1 | tests/unit/workspace/test_harvester.py |
| 03-REQ-7.2 | TS-03-11 | 4.1 | tests/unit/workspace/test_harvester.py |
| 03-REQ-7.3 | TS-03-10 | 4.1 | tests/unit/workspace/test_harvester.py |
| 03-REQ-7.E1 | TS-03-E6 | 4.1 | tests/unit/workspace/test_harvester.py |
| 03-REQ-7.E2 | TS-03-E5 | 4.1 | tests/unit/workspace/test_harvester.py |
| 03-REQ-8.1 | TS-03-12, TS-03-P3 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-8.2 | TS-03-12, TS-03-P3 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-8.E1 | TS-03-E7 | 3.4 | tests/unit/session/test_runner.py |
| 03-REQ-9.1 | TS-03-1, TS-03-10, TS-03-11 | 2.1 | tests/unit/workspace/test_worktree.py |
| 03-REQ-9.2 | TS-03-E1, TS-03-E6 | 2.1 | tests/unit/workspace/test_worktree.py |
| Property 1 | TS-03-P1 | 2.2 | tests/property/workspace/test_worktree_props.py |
| Property 3 | TS-03-P2 | 3.4 | tests/property/session/test_runner_props.py |
| Property 5 | TS-03-P3 | 3.4 | tests/property/session/test_security_props.py |

## Notes

- All git operations use `asyncio.create_subprocess_exec` for non-blocking
  I/O. This is important because the session runner is async and git
  operations are called from async context.
- The claude-code-sdk dependency should be imported lazily or behind a
  try/except in tests so that tests can run without a Claude Code CLI
  installation by mocking the SDK.
- The `query()` mock should yield a realistic message sequence:
  `[AssistantMessage, ..., ResultMessage]`. Tests should verify that the
  runner handles each message type correctly.
- Worktree integration tests need real git repositories. Use `tmp_path`
  fixtures and `git init` to create temporary repos. These tests are slower
  than unit tests but necessary for confidence in git operations.
- The allowlist hook callback must be an async function matching the
  `HookCallback` type signature from the SDK.
- The session runner should NOT handle retries -- that is the orchestrator's
  responsibility (spec 04). The runner executes exactly once and reports
  the outcome.
