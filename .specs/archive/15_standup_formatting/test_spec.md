# Test Specification: Standup Report Plain-Text Formatting

## Overview

This test spec covers the plain-text standup formatting feature: utility
functions (`_format_tokens`, `_display_node_id`), data model enrichments
(`TaskActivity`, `QueueSummary` new fields, `StandupReport` new fields),
the rewritten `TableFormatter.format_standup()`, and property-based invariants.
Tests map to requirements from `requirements.md` and correctness properties
from `design.md`.

## Test Cases

### TS-15-1: Plain-Text Header Format

**Requirement:** 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.3
**Type:** unit
**Description:** Verifies the standup header line contains the em dash, hours
value, generated timestamp, and trailing blank line.

**Preconditions:**
- A `StandupReport` with `window_hours=24` and
  `window_end="2026-03-02T12:30:00+00:00"`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output starts with `Standup Report — last 24h`
- Second line is `Generated: 2026-03-02T12:30:00+00:00`
- Third line is blank

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
lines = output.split("\n")
ASSERT lines[0] == "Standup Report — last 24h"
ASSERT lines[1] == "Generated: 2026-03-02T12:30:00+00:00"
ASSERT lines[2] == ""
```

---

### TS-15-2: Per-Task Agent Activity Lines

**Requirement:** 15-REQ-2.1, 15-REQ-2.2
**Type:** unit
**Description:** Verifies each task with session activity produces an indented
line with display ID, status, session counts, tokens, and cost.

**Preconditions:**
- A `StandupReport` with `task_activities` containing two entries:
  - `TaskActivity("s_a:1", "completed", 1, 1, 12900, 29500, 0.80)`
  - `TaskActivity("s_a:2", "completed", 1, 2, 14500, 9300, 0.31)`

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Agent Activity` header
- Output contains `  s_a/1: completed. 1/1 sessions. tokens 12.9k in / 29.5k out. $0.80`
- Output contains `  s_a/2: completed. 1/2 sessions. tokens 14.5k in / 9.3k out. $0.31`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Agent Activity" in output
ASSERT "  s_a/1: completed. 1/1 sessions. tokens 12.9k in / 29.5k out. $0.80" in output
ASSERT "  s_a/2: completed. 1/2 sessions. tokens 14.5k in / 9.3k out. $0.31" in output
```

---

### TS-15-3: Human Commits Lines

**Requirement:** 15-REQ-3.1
**Type:** unit
**Description:** Verifies human commit lines show 7-char SHA, author, and subject.

**Preconditions:**
- A `StandupReport` with one `HumanCommit`:
  `sha="fd67aec1234567890abcdef1234567890abcdef0"`, `author="Michael Kuehl"`,
  `subject="updated README"`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Human Commits` header
- Output contains `  fd67aec Michael Kuehl: updated README`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Human Commits" in output
ASSERT "  fd67aec Michael Kuehl: updated README" in output
```

---

### TS-15-4: Queue Status Summary Line

**Requirement:** 15-REQ-4.1, 15-REQ-4.2
**Type:** unit
**Description:** Verifies queue status shows all counts on one line and lists
ready task IDs.

**Preconditions:**
- A `StandupReport` with `QueueSummary(total=76, ready=2, pending=3,
  in_progress=0, blocked=0, failed=0, completed=73,
  ready_task_ids=["fix_01:1", "fix_02:1"])`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Queue Status` header
- Output contains `  76 total: 73 done | 0 in progress | 3 pending | 2 ready | 0 blocked | 0 failed`
- Output contains `  Ready: fix_01/1, fix_02/1` (note: display format uses slashes, but total must account for all statuses: 73+0+3+2+0+0 = 78, but this test uses `total=76` as provided — the property test validates the invariant)

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Queue Status" in output
ASSERT "76 total: 73 done | 0 in progress | 3 pending | 2 ready | 0 blocked | 0 failed" in output
ASSERT "Ready: fix_01/1, fix_02/1" in output
```

---

### TS-15-5: File Overlaps Section

**Requirement:** 15-REQ-5.1
**Type:** unit
**Description:** Verifies file overlap lines use em dash, 7-char SHAs, and
display node IDs.

**Preconditions:**
- A `StandupReport` with one `FileOverlap`:
  `path=".agent-fox/state.jsonl"`,
  `agent_task_ids=["07_ops:3", "10_plat:2"]`,
  `human_commits=["7510417abc...", "77156b5abc..."]`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Heads Up — File Overlaps` header
- Output contains `  .agent-fox/state.jsonl — commits: 7510417, 77156b5 | agents: 07_ops/3, 10_plat/2`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Heads Up — File Overlaps" in output
ASSERT "  .agent-fox/state.jsonl — commits: 7510417, 77156b5 | agents: 07_ops/3, 10_plat/2" in output
```

---

### TS-15-6: Total Cost Line

**Requirement:** 15-REQ-6.1
**Type:** unit
**Description:** Verifies the all-time total cost line appears at the end.

**Preconditions:**
- A `StandupReport` with `total_cost=34.64`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Total Cost: $34.64`
- This line appears after all other sections.

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Total Cost: $34.64" in output
last_section_idx = max(output.index("Queue Status"), output.index("Total Cost"))
ASSERT output.index("Total Cost") == last_section_idx
```

---

### TS-15-7: Token Formatting Function

**Requirement:** 15-REQ-7.1
**Type:** unit
**Description:** Verifies `_format_tokens()` produces correct output for
various input ranges.

**Preconditions:**
- None (pure function).

**Input/Expected pairs:**
- `0` -> `"0"`
- `345` -> `"345"`
- `999` -> `"999"`
- `1000` -> `"1.0k"`
- `12900` -> `"12.9k"`
- `29500` -> `"29.5k"`
- `100000` -> `"100.0k"`

**Assertion pseudocode:**
```
ASSERT _format_tokens(0) == "0"
ASSERT _format_tokens(345) == "345"
ASSERT _format_tokens(999) == "999"
ASSERT _format_tokens(1000) == "1.0k"
ASSERT _format_tokens(12900) == "12.9k"
ASSERT _format_tokens(29500) == "29.5k"
ASSERT _format_tokens(100000) == "100.0k"
```

---

### TS-15-8: Display Node ID Function

**Requirement:** 15-REQ-8.1
**Type:** unit
**Description:** Verifies `_display_node_id()` replaces colons with slashes.

**Preconditions:**
- None (pure function).

**Input/Expected pairs:**
- `"01_core_foundation:1"` -> `"01_core_foundation/1"`
- `"fix_01_ruff_format:1"` -> `"fix_01_ruff_format/1"`
- `"s:10"` -> `"s/10"`

**Assertion pseudocode:**
```
ASSERT _display_node_id("01_core_foundation:1") == "01_core_foundation/1"
ASSERT _display_node_id("fix_01_ruff_format:1") == "fix_01_ruff_format/1"
ASSERT _display_node_id("s:10") == "s/10"
```

---

### TS-15-9: Per-Task Activity Generation

**Requirement:** 15-REQ-2.3
**Type:** unit
**Description:** Verifies `generate_standup()` produces per-task breakdowns
from windowed session records.

**Preconditions:**
- State with 3 sessions for 2 tasks in window:
  - `s:1` completed, 1000 in, 500 out, $0.10
  - `s:1` failed, 500 in, 200 out, $0.05
  - `s:2` completed, 2000 in, 1000 out, $0.20

**Input:**
- Call `generate_standup(state_path, plan_path, repo_path, hours=24)`

**Expected:**
- `report.task_activities` has 2 entries
- `s:1` entry: `completed_sessions=1, total_sessions=2, input_tokens=1500, output_tokens=700, cost=0.15`
- `s:2` entry: `completed_sessions=1, total_sessions=1, input_tokens=2000, output_tokens=1000, cost=0.20`

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path, hours=24)
ASSERT len(report.task_activities) == 2
s1 = [t for t in report.task_activities if t.task_id == "s:1"][0]
ASSERT s1.completed_sessions == 1
ASSERT s1.total_sessions == 2
ASSERT s1.input_tokens == 1500
s2 = [t for t in report.task_activities if t.task_id == "s:2"][0]
ASSERT s2.completed_sessions == 1
ASSERT s2.total_sessions == 1
```

---

### TS-15-10: Enriched Queue Summary Generation

**Requirement:** 15-REQ-4.3
**Type:** unit
**Description:** Verifies `generate_standup()` populates the enriched
`QueueSummary` fields: `total`, `in_progress`, and `ready_task_ids`.

**Preconditions:**
- Plan with 5 tasks, no dependencies
- State: 2 completed, 1 in_progress, 2 pending (both ready since no deps)

**Input:**
- Call `generate_standup(state_path, plan_path, repo_path, hours=24)`

**Expected:**
- `report.queue.total == 5`
- `report.queue.in_progress == 1`
- `report.queue.ready == 2`
- `report.queue.ready_task_ids` contains the 2 pending task IDs

**Assertion pseudocode:**
```
report = generate_standup(state_path, plan_path, repo_path, hours=24)
ASSERT report.queue.total == 5
ASSERT report.queue.in_progress == 1
ASSERT report.queue.ready == 2
ASSERT set(report.queue.ready_task_ids) == {"s:4", "s:5"}
```

## Edge Case Tests

### TS-15-E1: No Agent Activity

**Requirement:** 15-REQ-2.E1
**Type:** unit
**Description:** When no sessions exist in the window, output shows
`(no agent activity)`.

**Preconditions:**
- A `StandupReport` with empty `task_activities`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `  (no agent activity)`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "  (no agent activity)" in output
```

---

### TS-15-E2: No Human Commits

**Requirement:** 15-REQ-3.E1
**Type:** unit
**Description:** When no human commits exist, output shows
`(no human commits)`.

**Preconditions:**
- A `StandupReport` with empty `human_commits`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `  (no human commits)`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "  (no human commits)" in output
```

---

### TS-15-E3: No File Overlaps

**Requirement:** 15-REQ-5.E1
**Type:** unit
**Description:** When no file overlaps exist, the `Heads Up` section is
omitted entirely.

**Preconditions:**
- A `StandupReport` with empty `file_overlaps`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output does NOT contain `Heads Up`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Heads Up" not in output
```

---

### TS-15-E4: No Ready Tasks

**Requirement:** 15-REQ-4.E1
**Type:** unit
**Description:** When no tasks are ready, the `Ready:` line is omitted.

**Preconditions:**
- A `StandupReport` with `queue.ready_task_ids=[]` and `queue.ready=0`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Queue Status` header
- Output does NOT contain `Ready:`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Queue Status" in output
ASSERT "Ready:" not in output
```

---

### TS-15-E5: Total Cost Zero

**Requirement:** 15-REQ-6.E1
**Type:** unit
**Description:** When no execution state exists, total cost shows $0.00.

**Preconditions:**
- A `StandupReport` with `total_cost=0.0`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output contains `Total Cost: $0.00`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT "Total Cost: $0.00" in output
```

---

### TS-15-E6: Hours Value of 1

**Requirement:** 15-REQ-1.E1
**Type:** unit
**Description:** Header correctly shows singular `1h`.

**Preconditions:**
- A `StandupReport` with `window_hours=1`.

**Input:**
- Call `TableFormatter().format_standup(report)`

**Expected:**
- Output starts with `Standup Report — last 1h`

**Assertion pseudocode:**
```
output = TableFormatter().format_standup(report)
ASSERT output.startswith("Standup Report — last 1h")
```

## Property Test Cases

### TS-15-P1: Token Format Consistency

**Property:** Property 1 from design.md
**Validates:** 15-REQ-7.1
**Type:** property
**Description:** For any non-negative integer, `_format_tokens` produces output
matching the expected regex pattern.

**For any:** `n` drawn from `st.integers(min_value=0, max_value=10_000_000)`
**Invariant:** If `n < 1000`, result matches `r"^\d+$"`. If `n >= 1000`, result
matches `r"^\d+\.\d{1}k$"`.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(min_value=0, max_value=10_000_000):
    result = _format_tokens(n)
    IF n < 1000:
        ASSERT re.fullmatch(r"\d+", result)
        ASSERT result == str(n)
    ELSE:
        ASSERT re.fullmatch(r"\d+\.\dk", result)
```

---

### TS-15-P2: Display Node ID Roundtrip

**Property:** Property 2 from design.md
**Validates:** 15-REQ-8.1
**Type:** property
**Description:** Colon-to-slash replacement is the only transformation applied.

**For any:** `spec` drawn from `st.text(st.characters(whitelist_categories=("L", "N", "Pc")), min_size=1, max_size=30)`,
  `group` drawn from `st.integers(min_value=1, max_value=99)`
**Invariant:** `_display_node_id(f"{spec}:{group}")` equals `f"{spec}/{group}"`.

**Assertion pseudocode:**
```
FOR ANY spec IN text_strategy, group IN st.integers(1, 99):
    node_id = f"{spec}:{group}"
    ASSERT _display_node_id(node_id) == f"{spec}/{group}"
```

---

### TS-15-P3: Per-Task Activity Session Sum

**Property:** Property 3 from design.md
**Validates:** 15-REQ-2.2, 15-REQ-2.3
**Type:** property
**Description:** Sum of total_sessions across all TaskActivity entries equals
the count of windowed sessions.

**For any:** List of session records with timestamps within the window
**Invariant:** `sum(ta.total_sessions for ta in activities) == len(windowed_sessions)`

**Assertion pseudocode:**
```
FOR ANY sessions IN lists_of_session_records:
    activities = _compute_task_activities(sessions, node_states)
    ASSERT sum(ta.total_sessions for ta in activities) == len(sessions)
```

---

### TS-15-P4: Queue Summary Total Equals Component Sum

**Property:** Property 4 from design.md
**Validates:** 15-REQ-4.1, 15-REQ-4.3
**Type:** property
**Description:** QueueSummary.total equals the sum of all status counts and
len(ready_task_ids) equals ready count.

**For any:** Task graph and execution state
**Invariant:** `total == ready + pending + in_progress + blocked + failed + completed`
and `len(ready_task_ids) == ready`

**Assertion pseudocode:**
```
FOR ANY graph, state IN task_graph_strategy:
    queue = _build_queue_summary(graph, state)
    ASSERT queue.total == queue.ready + queue.pending + queue.in_progress + queue.blocked + queue.failed + queue.completed
    ASSERT len(queue.ready_task_ids) == queue.ready
```

---

### TS-15-P5: Section Ordering

**Property:** Property 5 from design.md
**Validates:** 15-REQ-1.1, 15-REQ-2.1, 15-REQ-3.1, 15-REQ-4.1, 15-REQ-5.1, 15-REQ-6.1
**Type:** property
**Description:** Sections appear in the fixed order regardless of report content.

**For any:** StandupReport (with various populated/empty sections)
**Invariant:** Index of `"Agent Activity"` < index of `"Human Commits"` <
index of `"Queue Status"` < index of `"Total Cost"`. If `"Heads Up"` is
present, it appears between `"Queue Status"` and `"Total Cost"`.

**Assertion pseudocode:**
```
FOR ANY report IN standup_report_strategy:
    output = TableFormatter().format_standup(report)
    idx_agent = output.index("Agent Activity")
    idx_human = output.index("Human Commits")
    idx_queue = output.index("Queue Status")
    idx_cost = output.index("Total Cost")
    ASSERT idx_agent < idx_human < idx_queue < idx_cost
    IF "Heads Up" in output:
        idx_overlap = output.index("Heads Up")
        ASSERT idx_queue < idx_overlap < idx_cost
```

---

### TS-15-P6: Empty Sections Handling

**Property:** Property 6 from design.md
**Validates:** 15-REQ-2.E1, 15-REQ-3.E1, 15-REQ-5.E1
**Type:** property
**Description:** Empty sections produce correct placeholder text or are omitted.

**For any:** StandupReport with empty task_activities, human_commits, or
file_overlaps
**Invariant:** Empty task_activities -> `"(no agent activity)"` in output.
Empty human_commits -> `"(no human commits)"` in output. Empty
file_overlaps -> `"Heads Up"` NOT in output.

**Assertion pseudocode:**
```
FOR ANY report IN standup_report_with_empties:
    output = TableFormatter().format_standup(report)
    IF len(report.task_activities) == 0:
        ASSERT "(no agent activity)" in output
    IF len(report.human_commits) == 0:
        ASSERT "(no human commits)" in output
    IF len(report.file_overlaps) == 0:
        ASSERT "Heads Up" not in output
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 15-REQ-1.1 | TS-15-1 | unit |
| 15-REQ-1.2 | TS-15-1 | unit |
| 15-REQ-1.3 | TS-15-1 | unit |
| 15-REQ-1.E1 | TS-15-E6 | unit |
| 15-REQ-2.1 | TS-15-2 | unit |
| 15-REQ-2.2 | TS-15-2 | unit |
| 15-REQ-2.3 | TS-15-9 | unit |
| 15-REQ-2.E1 | TS-15-E1 | unit |
| 15-REQ-3.1 | TS-15-3 | unit |
| 15-REQ-3.E1 | TS-15-E2 | unit |
| 15-REQ-4.1 | TS-15-4 | unit |
| 15-REQ-4.2 | TS-15-4 | unit |
| 15-REQ-4.3 | TS-15-10 | unit |
| 15-REQ-4.E1 | TS-15-E4 | unit |
| 15-REQ-5.1 | TS-15-5 | unit |
| 15-REQ-5.E1 | TS-15-E3 | unit |
| 15-REQ-6.1 | TS-15-6 | unit |
| 15-REQ-6.2 | TS-15-6 | unit |
| 15-REQ-6.E1 | TS-15-E5 | unit |
| 15-REQ-7.1 | TS-15-7 | unit |
| 15-REQ-8.1 | TS-15-8 | unit |
| 15-REQ-8.2 | TS-15-2, TS-15-4, TS-15-5 | unit |
| Property 1 | TS-15-P1 | property |
| Property 2 | TS-15-P2 | property |
| Property 3 | TS-15-P3 | property |
| Property 4 | TS-15-P4 | property |
| Property 5 | TS-15-P5 | property |
| Property 6 | TS-15-P6 | property |
