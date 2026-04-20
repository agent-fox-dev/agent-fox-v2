# PRD: Session and Workspace

**Source:** `.specs/prd.md` -- Section 5 (Autonomous Coding REQ-020 through
REQ-027), Section 8 (Error Handling: Session Failure, Integration Conflict,
Timeout).

## Overview

This spec implements the core execution machinery for agent-fox v2: the
isolated git worktree workspaces where coding sessions run, the session runner
that drives the claude-code-sdk, context assembly that feeds the agent
task-specific knowledge, and the harvester that integrates completed work back
into the shared development line.

Together these modules turn a planned task into a committed, integrated code
change -- or a well-documented failure with captured metrics.

## Problem Statement

agent-fox needs to run AI coding sessions that are fully isolated from each
other and from already-integrated work. Each session must receive the right
context (spec documents, memory facts), execute within a time budget, and
produce a measurable outcome. When a session succeeds, its changes must be
cleanly merged into the development branch. When it fails, the failure must be
recorded with enough detail for retry logic to operate.

## Goals

- Create and destroy git worktrees at `.agent-fox/worktrees/{spec}/{group}`
  so each session gets a clean, isolated working copy
- Execute coding sessions via the claude-code-sdk async `query()` function,
  in-process, not via subprocess
- Assemble task-specific context: spec documents (requirements.md, design.md,
  tasks.md) and relevant memory facts
- Build system and task prompts that instruct the coding agent
- Enforce a configurable session timeout (default 30 minutes) via
  `asyncio.wait_for()`
- Capture session outcomes: status, files touched, token usage, duration,
  error messages
- Validate and merge worktree changes back to `develop`, handling merge
  conflicts with automatic rebase retry
- Register security hooks (command allowlist) as SDK PreToolUse hooks

## Non-Goals

- Parallel session orchestration -- that is spec 04
- Retry logic and cascade-blocking -- that is spec 04 (orchestrator)
- Memory extraction after sessions -- that is spec 06
- DuckDB persistence of outcomes -- that is spec 11
- Hook script execution (pre/post session) -- that is spec 05
- Cost tracking and budget enforcement -- that is spec 04

## Key Decisions

- **claude-code-sdk `query()` over subprocess:** In-process async execution
  avoids process management overhead, enables structured message handling, and
  allows PreToolUse hooks for security enforcement. Each coding session uses a
  single `query()` call with `permission_mode="bypassPermissions"` since
  security is enforced via the allowlist hook.

- **Git worktrees over clones:** Worktrees share the object store with the
  main repository, making creation near-instant and disk-efficient. They
  provide true filesystem isolation (separate working tree and index) without
  the overhead of a full clone.

- **asyncio.wait_for for timeout:** Standard library, no external dependency,
  integrates naturally with the async SDK. On timeout, the coroutine is
  cancelled and partial results are captured from the last observed
  ResultMessage.

- **Rebase-then-merge for conflict resolution:** When a fast-forward merge
  fails, the harvester rebases the feature branch onto the current develop
  tip and retries. This keeps the commit history linear and clean.

- **PreToolUse hook for command allowlist:** The SDK's hook system is the
  documented way to intercept tool calls. The hook inspects Bash tool
  invocations and blocks any command not on the configured allowlist.

## Dependencies

| Dependency | Spec | What is used |
|------------|------|--------------|
| AgentFoxConfig | 01 | `orchestrator.session_timeout`, `security.bash_allowlist`, `security.bash_allowlist_extend`, `models.coding` |
| Error hierarchy | 01 | `SessionError`, `WorkspaceError`, `IntegrationError`, `SessionTimeoutError`, `SecurityError` |
| Model registry | 01 | `resolve_model()` to get model ID for SDK options |
| ThemeConfig | 01 | Not directly used; logging only |
