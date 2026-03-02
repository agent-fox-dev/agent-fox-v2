# PRD: Standup Report Plain-Text Formatting

> Source: [GitHub Issue #45](https://github.com/agent-fox-dev/agent-fox-v2/issues/45)

## Problem

The `agent-fox standup --format table` output uses Rich tables with borders and
column headers. This is hard to scan and wastes vertical space. The v1 format
used compact, indented plain text that is easier to read at a glance.

## Goal

Replace the Rich table output of `agent-fox standup --format table` with a
plain-text indented format matching the agent-fox v1 standup report style. JSON
and YAML output formats are unchanged.

## Target Output Format

The standup report should render exactly like this (with real data):

```
Standup Report — last 24h
Generated: 2026-03-02T12:30:27.726233+00:00

Agent Activity
  01_core_foundation/1: completed. 1/1 sessions. tokens 12.9k in / 29.5k out. $0.80
  01_core_foundation/2: completed. 1/1 sessions. tokens 14.5k in / 9.3k out. $0.31

Human Commits
  fd67aec Michael Kuehl: updated README
  2d3844b Michael Kuehl: bundle skills and added audits

Queue Status
  76 total: 73 done | 0 in progress | 3 pending | 2 ready | 0 blocked | 0 failed
  Ready: fix_01_ruff_format/1, fix_02_unnarrrowed_content_block_union/1

Heads Up — File Overlaps
  .agent-fox/state.jsonl — commits: 7510417, 77156b5 | agents: 07_operational_commands/3, 10_platform_integration/2

Total Cost: $34.64
```

## Detailed Format Specification

### Header

```
Standup Report — last {hours}h
Generated: {ISO 8601 timestamp}
```

- Use an em dash (—) between "Report" and "last".
- `{hours}` is the `--hours` value.
- `Generated` timestamp is the window end time in ISO 8601.

### Agent Activity Section

```
Agent Activity
  {task_id}: {status}. {completed}/{total} sessions. tokens {in} in / {out} out. ${cost}
```

- One line per task that had any session activity in the window.
- `{task_id}` uses slash separator for display: `spec_name/group_number` (internal IDs use colons).
- `{status}` is the task's current status from execution state (e.g., `completed`, `failed`, `in_progress`).
- `{completed}/{total}` is completed session count / total session count for that task in the window.
- Tokens use human-readable formatting with one decimal: `12.9k`, `1.2k`, `345` (no suffix below 1000).
- Cost is formatted as `$X.XX`.
- If no agent activity occurred, print `  (no agent activity)`.

### Human Commits Section

```
Human Commits
  {sha_7} {author}: {subject}
```

- One line per human commit in the window.
- SHA is truncated to 7 characters.
- If no human commits, print `  (no human commits)`.

### Queue Status Section

```
Queue Status
  {total} total: {done} done | {in_progress} in progress | {pending} pending | {ready} ready | {blocked} blocked | {failed} failed
  Ready: {task_id_1}, {task_id_2}, ...
```

- First line shows all status counts on one line. `{total}` is the sum of all tasks.
- `{done}` maps to the `completed` count. Label it "done" in the output.
- `{in_progress}` is tasks currently being executed.
- `{pending}` is tasks waiting but not yet ready (have unmet dependencies).
- `{ready}` is tasks whose dependencies are all met.
- `{blocked}` and `{failed}` as current.
- Second line lists ready task IDs (slash format). If no tasks are ready, omit the "Ready:" line.

### File Overlaps Section

```
Heads Up — File Overlaps
  {file_path} — commits: {sha1}, {sha2} | agents: {task_id_1}, {task_id_2}
```

- Section header uses em dash.
- One line per overlapping file.
- Commit SHAs truncated to 7 characters.
- Task IDs in slash format.
- If no overlaps, omit this section entirely.

### Total Cost Line

```
Total Cost: ${all_time_total}
```

- This is the **all-time** total cost from `ExecutionState.total_cost`, not the
  windowed cost. It provides context for the overall project spend.

## Data Model Changes

The current `StandupReport` model needs enrichment:

1. **Per-task session breakdown** — The `AgentActivity` dataclass currently only
   stores aggregated metrics. Add a list of per-task breakdowns so the formatter
   can render one line per task. Each entry needs: task_id, current_status,
   completed_sessions, total_sessions, input_tokens, output_tokens, cost.

2. **Ready task IDs** — The `QueueSummary` dataclass currently stores only
   counts. Add a `ready_task_ids: list[str]` field.

3. **Total and in_progress counts** — Add `total: int` and `in_progress: int`
   fields to `QueueSummary`.

4. **All-time total cost** — Add a `total_cost: float` field to
   `StandupReport` for the all-time cost.

## Scope

- **In scope:** `TableFormatter.format_standup()` and supporting data model changes.
- **Out of scope:** `format_status()`, `JsonFormatter`, `YamlFormatter`, CLI argument changes.
- **Backward compatibility:** JSON and YAML serialization of the enriched models will naturally include the new fields. This is acceptable — new fields are additive.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 07_operational_commands | 3 | 1 | Uses StandupReport, AgentActivity, QueueSummary, and TableFormatter defined in spec 07 |
