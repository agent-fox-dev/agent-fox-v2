# PRD: Operational Commands

**Source:** `.specs/prd.md` -- Section 5 "Progress and Reporting" (REQ-090
through REQ-092), "State Reset" (REQ-100 through REQ-102), Section 4 "Monitor
Progress", "Daily Standup Report", and "Reset Failed Tasks" workflows, Section
7 "Output Specification" (Status Output, Standup Report).

## Overview

Three operational CLI commands that give developers visibility into execution
progress and the ability to recover from failures: `agent-fox status` (progress
dashboard), `agent-fox standup` (daily activity report), and `agent-fox reset`
(clear failed/incomplete tasks for retry).

## Problem Statement

After kicking off an autonomous coding run, developers need to answer three
questions without reading logs or source code: "Where do things stand?"
(status), "What happened while I was away?" (standup), and "How do I unstick
failed tasks?" (reset). These commands close the feedback loop between the
autonomous engine and the human developer.

## Goals

- Display a progress dashboard with task counts, token usage, cost, and
  blocked/failed task details (REQ-090)
- Generate a standup report covering agent activity, human commits, file
  overlaps, cost breakdown, and queued tasks within a configurable time window
  (REQ-091)
- Support JSON and YAML output formats for both status and standup (REQ-092)
- Reset all incomplete tasks or a single task, cleaning up worktrees and
  branches (REQ-100, REQ-101)
- Re-evaluate blocked tasks after single-task reset (REQ-101)
- Provide a confirmation prompt for full reset, skippable with `--yes`
  (REQ-102)

## Non-Goals

- Modifying the orchestrator's execution loop -- that is spec 04
- Creating or modifying the plan -- that is spec 02
- Running coding sessions -- that is spec 03
- Real-time dashboard or web UI -- agent-fox is a CLI tool
- Modifying completed tasks -- reset only touches incomplete tasks

## Key Decisions

- **Status reads state, not plan.** The `status` command reads
  `.agent-fox/state.jsonl` (execution state from spec 04) and
  `.agent-fox/plan.json` (task graph from spec 02). It never modifies either.
- **Standup uses git log for human commit detection.** Human commits are
  identified by filtering `git log` to exclude the agent's author identity.
  File overlap is computed by intersecting agent-touched files (from
  `state.jsonl` session records) with human-changed files (from `git log`).
- **Reset cleans up worktree directories and feature branches.** A reset task
  has its worktree directory removed (if present under `.agent-fox/worktrees/`)
  and its feature branch deleted (if present). The task status is set back to
  `pending`.
- **Single-task reset re-evaluates downstream blockers.** If the reset task was
  the only reason a downstream task was blocked, that downstream task is
  unblocked (set back to `pending`).
- **Formatters are pluggable.** A common formatter interface supports table
  (Rich, default), JSON, and YAML output. The same data models feed all three
  formats.
- **Standup can write to file.** The `--output` flag writes the report to a
  file path instead of stdout, useful for CI integration or daily logs.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 5 | 1 | `AgentFoxConfig`, `ThemeConfig`, `AppTheme`, `AgentFoxError`, `calculate_cost()`, `resolve_model()`, CLI framework (`main` Click group), logging |
| 04_orchestrator | 6 | 1 | `ExecutionState`, `SessionRecord`, `NodeStatus`, `state.jsonl` format, `plan.json` format |
