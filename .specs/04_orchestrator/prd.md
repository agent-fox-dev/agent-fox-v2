# PRD: Orchestrator

**Source:** `.specs/prd.md` -- Section 5 "Autonomous Coding" (REQ-020 through
REQ-031), "Parallel Execution" (REQ-040 through REQ-043), Section 4 "Plan and
Execute" workflow, Section 8 "Error Handling" (session failure, cost/session
limits, interruption, stalled progress).

## Overview

The orchestrator is the main execution engine of agent-fox. It reads the task
graph produced by the planning engine (spec 02), drives coding sessions (spec
03) in dependency order, handles sequential and parallel execution, enforces
retry logic with error feedback, cascade-blocks dependent tasks on failure,
persists execution state for resume, enforces cost and session limits, and
handles graceful interruption (Ctrl+C). The orchestrator itself is
**deterministic** -- it never makes LLM calls. It follows the task graph
mechanically, delegating all AI work to the session runner.

## Problem Statement

Once the planning engine produces a task graph, something must walk that graph,
dispatch sessions, handle failures, enforce resource limits, and persist
progress so the system can resume after interruption. The orchestrator is that
something. It must be correct under concurrent execution (up to 8 parallel
sessions), resilient to interruption, and deterministic in its scheduling
decisions.

## Goals

- Execute tasks in dependency order, dispatching to serial or parallel runners
- Retry failed sessions with error feedback (up to max_retries, default 2)
- Cascade-block all downstream dependents when a task is permanently blocked
- Persist execution state after every session to `.agent-fox/state.jsonl`
- Resume from persisted state after interruption or restart
- Enforce cost ceiling: stop launching new sessions when cumulative cost >= limit
- Enforce session count ceiling: stop after configured number of sessions
- Support parallel execution of up to 8 independent tasks via asyncio
- Guarantee exactly-once execution: no task runs twice (unless explicitly reset)
- Handle Ctrl+C gracefully: save state, clean up, print resume instructions
- Apply configurable inter-session delay to avoid rate limiting

## Non-Goals

- Making LLM calls -- the orchestrator is deterministic
- Creating workspaces or running coding agents -- that is spec 03
- Building the task graph -- that is spec 02
- Hot-loading new specs during execution -- that is a separate concern (REQ-050/051)
- Sync barriers and checkpoint hooks -- deferred to a future spec
- Platform integration (PR creation, CI waiting) -- that is spec 05

## Key Decisions

- **Deterministic execution.** The orchestrator contains zero LLM calls. Every
  scheduling decision is a mechanical consequence of the task graph and current
  state.
- **State persisted as JSONL.** `.agent-fox/state.jsonl` is an append-only
  event log. Each line is a JSON object recording a state transition: session
  start, session complete, session failed, task blocked, etc. On resume, the
  log is replayed to reconstruct the current state.
- **Retry with error context.** When a session fails and is retried, the
  orchestrator passes the previous error message to the session runner so the
  agent can avoid repeating the same mistake.
- **Cascade blocking is eager and complete.** When a task is blocked, every
  node reachable from it via dependency edges is also blocked. This is computed
  by a BFS/DFS traversal from the blocked node.
- **Parallel execution via asyncio.** Up to 8 tasks dispatched concurrently.
  State writes are lock-serialized to prevent corruption. Integration conflicts
  (merge conflicts from concurrent sessions) are handled by the session runner
  via rebase-and-retry.
- **Cost limit is a soft ceiling.** When cumulative cost >= limit, no new
  sessions are launched. In-flight sessions are allowed to complete.
- **Signal handling for Ctrl+C.** A SIGINT handler saves state, cancels
  in-flight tasks (in parallel mode), cleans up workspaces, and prints
  resume instructions.

## Dependencies

| This Spec | Depends On | What It Uses |
|-----------|-----------|--------------|
| 04_orchestrator | 01_core_foundation | `AgentFoxConfig`, `OrchestratorConfig`, `CostLimitError`, `SessionError`, `SessionTimeoutError`, `AgentFoxError`, `calculate_cost()`, `resolve_model()`, logging |
| 04_orchestrator | 02_planning_engine | `TaskGraph`, `TaskNode`, `NodeStatus`, `plan.json` (the orchestrator reads the persisted plan) |
| 04_orchestrator | 03_session_runner | `SessionRunner`, `WorkspaceInfo`, `SessionOutcome`, `Harvester` (the orchestrator drives sessions and collects outcomes) |
