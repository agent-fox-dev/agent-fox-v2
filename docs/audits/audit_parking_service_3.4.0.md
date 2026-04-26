Analysis of output_3.4.0.log and Knowledge System

Run Overview

- 83 tasks completed across 9 specs, 5 parallel sessions
- Total cost: $223.40 (433K in / 1.8M out tokens)
- No errors or crashes — every task completed successfully
- All specs implemented through review → code → audit-review → verify cycles

Anomalies Found

1. Audit JSONL Write Failures — 469 occurrences (~8% data loss)

AuditJsonlSink.emit_audit_event() in audit.py:226-233 opens the file with open(path, "a") for every single event, with no file locking. With
parallel = 5, concurrent appends cause OSError. The JSONL file ended up with 5,466 lines, meaning ~469 events were silently dropped.

Root cause: No file lock or buffered writer. Each emit_audit_event call opens/closes the file independently.

2. Agent Trace File Never Found — 83/83 sessions (100% failure rate)

Every session completion logs:
Agent trace file not found: .agent-fox/audit/agent_20260424_104228_037c49.jsonl, falling back to alternative transcript source

The agent_*.jsonl trace file is simply never created. All 83 sessions fall back to the "alternative transcript source" (which appears to be
reconstructed from the claude code session transcripts). The primary trace mechanism is completely non-functional.

3. Legacy Spec Root Warnings — repeated throughout

Using legacy spec root '.specs/' — migrate to '.agent-fox/specs/' or set spec_root in config.toml

The parking-fee-service has .agent-fox/specs/ (confirmed from directory listing), yet this warning fires every time a spec is loaded. Likely
the config doesn't set spec_root explicitly, and the code checks .specs/ first.

4. Untracked Files Removed During Merge (Data Loss Risk)

Line 1873:
Removing 4 untracked file(s) that would block merge: tests/parking-operator-adaptor/go.mod, ...

The harvest system silently deletes untracked files that conflict with a squash merge. In this case it's benign (the merge includes those
files), but this is a silent data-loss vector for any legitimate untracked work in the project.

---
Is the Knowledge System Working or Theater?

Partial theater. Here's the breakdown:

What WORKS (within a single run):

- Review findings flow between sessions: Pre-review inserts findings → fox_provider retrieves them → coder sessions see them. Example:
01_project_setup goes from 0 → 4 → 53 review items across iterations. The coder sessions reference "skeptic review findings" and "critical
review findings" in their summaries. This feedback loop is genuinely influencing code.

What's THEATER:

Errata retrieval — always 0, despite errata being created:
- Sessions create errata files like docs/errata/01_test_scope.md and errata/03_ts_e2_subscription_interrupted.md
- But fox_provider reports 0 errata items for every spec in every session, throughout the entire run
- The errata markdown files are never indexed into the DuckDB errata table
- Subsequent sessions are blind to errata — the entire errata creation workflow is write-only theater

No DuckDB file persists after the run:
- Default store_path is .agent-fox/knowledge.duckdb (from config.py:256)
- This file does not exist on disk
- All review findings, verification results, and accumulated knowledge are gone
- If you rerun, the knowledge system starts from zero — no cross-run learning

Supersession never fires — always (superseded 0):
- Every review_store insert reports superseded 0
- Pre-review findings use key [0], audit-review findings use key [] — they're treated as different entries
- Review findings accumulate but stale findings are never invalidated
- Total review items for 01_project_setup: 8 (pre-review) + 51 (audit) + 56 (verification) = 115 items, all active, none superseded
- This means later coding sessions may be addressing already-resolved review findings

Session summary is incomplete:
- session-summary.json shows "tests_added_or_modified": [] — incorrect given the many tests added

Summary Table:

┌─────────────────────────────┬────────────┬──────────────────────────────────────────────────────────┐
│          Component          │   Status   │                          Impact                          │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Review findings (intra-run) │ Working    │ Coder sessions do receive and act on reviews             │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Errata pipeline             │ Broken     │ Files created but never indexed; always 0 retrieved      │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Knowledge persistence       │ Broken     │ No DuckDB file after run; no cross-run memory            │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Audit trail                 │ Lossy (8%) │ 469 events silently dropped from concurrent writes       │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Agent traces                │ Broken     │ Never created; 100% fallback for all 83 sessions         │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Review supersession         │ Broken     │ Stale findings never invalidated; unbounded accumulation │
├─────────────────────────────┼────────────┼──────────────────────────────────────────────────────────┤
│ Session summaries           │ Incomplete │ tests_added_or_modified always empty                     │
└─────────────────────────────┴────────────┴──────────────────────────────────────────────────────────┘

The knowledge system has the plumbing to be meaningful — the review-to-coder feedback loop within a single run does demonstrably work. But
three of its six subsystems are non-functional (errata, agent traces, persistence), one is lossy (audit), and one has a design flaw
(supersession). The net effect is that the system provides single-run review feedback but no durable organizational memory.