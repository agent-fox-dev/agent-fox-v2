Analysis of agent-fox 3.3.2 Runs

Run Overview

┌────────────────────┬────────────────────────────┬───────────────────────────┐
│                    │           Test 1           │          Test 2           │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Run ID             │ 20260423_124348_5dac9f     │ 20260423_200127_76fb9a    │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Sessions completed │ 76                         │ 7                         │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Sessions blocked   │ 6                          │ 0                         │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Duration           │ ~8h (interrupted)          │ ~1h 13m                   │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Cost               │ not recorded (interrupted) │ $20.73                    │
├────────────────────┼────────────────────────────┼───────────────────────────┤
│ Specs covered      │ 9 (01-09)                  │ 3 (04, 08, 09 — leftover) │
└────────────────────┴────────────────────────────┴───────────────────────────┘

Test1 was a full greenfield build that was interrupted via SIGINT. Test2 picked up the remaining blocked tasks (caused by budget exhaustion in test1) and completed them.

---
1. Anomalies and Issues

A. Phantom task group dispatch (BUG)
08_parking_operator_adaptor:7 was dispatched even though the spec only defines 6 task groups (1-6). The coder correctly self-reported "No work performed: There is no task group 7" — but it still 
burned ~1 minute and tokens. The plan graph has 83 nodes but some don't correspond to real work. This means the plan generation or node counting logic is 
off-by-one or doesn't validate against the actual spec's task count.

B. Massive no-work waste (DESIGN ISSUE)
18 of 50 coder session summaries in test1 (36%) reported the work was "already fully implemented" or "no code changes needed." These are sessions where 
the coder launched, read files, verified prior work was done, and exited — typically consuming 1-5 minutes and budget each. Examples:
- 05_parking_fee_service:2 — 1m 48s, "already fully implemented"
- 04_cloud_gateway_client:7 — 3m 5s, "already fully implemented"
- 03_locking_service:5 — 5m 42s, "all items were addressed by prior sessions"

The knowledge system doesn't seem to track subtask completion granularly enough to prevent dispatching already-complete work.

C. Budget exhaustion cascades
Two nodes hit the $8.00/session budget limit and triggered cascade blocks:
- 04_cloud_gateway_client:9 ($7.64 spent) → cascaded block to :10
- 08_parking_operator_adaptor:5 ($7.44 spent) → cascaded block to :6, :7, :8

These were the nodes that required test2 to finish. The cascade mechanism itself works correctly, but the budget of $8 is tight for some complex tasks (integration test work against external APIs).

D. Timeout retries (WORKING)
Three sessions hit the 30-minute timeout:
- 01_project_setup:1, 01_project_setup:2, 08_parking_operator_adaptor:5

All were retried with extended 45-minute timeout. The retries succeeded for setup:1 and setup:2; parking_operator:5 then hit budget exhaustion instead. The retry mechanism is functioning.

E. Double dispatch of 01_project_setup:2 (BUG)
The log shows 01_project_setup:2 transitioning from pending to=in_progress twice (lines 246 and 255), with two separate session lifecycle entries. This suggests the node was 
dispatched twice — once where it timed out, and again with the extended timeout. However, the state machine allowed a second dispatch without a visible intermediate state reset, which is suspicious.

F. 01_project_setup as a resource sink
This spec consumed 8 coder sessions (groups 1-7 plus retries), each running 10-24 minutes, plus reviewer and verifier sessions. Many reported "already addressed by prior commits." 
This spec is the most expensive by far, consuming ~170+ minutes of coder time. The task graph for this spec seems to force serial re-verification of already-completed work.

G. SIGINT/transport handling
Test1 was interrupted with SIGINT → double-SIGINT. The ClaudeBackend stream ended without ResultMessage warning suggests the transport layer wasn't fully clean during shutdown. 
No data corruption observed, but the interrupted run's session_outcomes weren't persisted — only 8 rows exist (all from test2).

H. Database persistence across interrupted runs (DATA INTEGRITY)
The knowledge database has inconsistent state:
- runs table: only 1 entry (test2). Test1's run was lost.
- session_outcomes: only 8 rows (all test2). Test1's 76 completed sessions have no outcome records.
- audit_events: 4,531 rows — appears to accumulate from both runs.
- tool_calls: 4,196 rows — accumulated from both runs.
- errata: 23 entries — persisted from test1.
- review_findings: 0 rows despite hundreds being inserted during both runs.

The fact that review_findings is empty is particularly concerning. The logs show "Inserted 51 review findings for 01_project_setup/", "Inserted 35 review findings for 03_locking_service/", etc. — but they're all gone at rest. 
Either they're being cleaned up by an end-of-run process, or they're being superseded by later reviews but the supersession isn't tracked correctly.

---
2. Agent Archetype Effectiveness

Reviewer (pre-review) — WORKING, HIGH VALUE
Found genuine critical issues in specs before coding began:
- 02_data_broker: Image version contradiction, v1/v2 API confusion
- 06_cloud_gateway: Store timeout race condition
- 07_update_service: TOCTOU race in install flow, non-atomic single-adapter check
- 08_parking_operator_adaptor: Missing rate field in proto

All 4 blocking reviews led to errata generation and the coders explicitly addressed these findings. This archetype is the strongest contributor to quality.

Reviewer (audit-review) — WORKING, MODERATE VALUE
Produced audit reports and detailed findings (51 for 01_project_setup, 35 for 03_locking_service, 40 for 07_update_service, etc.). Reports are properly cleaned up when 
specs complete. Two specs received PASS verdicts and had their reports removed immediately (05_parking_fee_service, 06_cloud_gateway). 
However, since the review_findings table is empty at rest, these findings aren't available for cross-run learning.

Coder — WORKING, but WASTEFUL
Successfully:
- Fixed real bugs (kuksa v1→v2 migration, proto field number mismatches, SIGTERM signal races, TOCTOU bugs, store timeout races)
- Added substantial test coverage (property tests, integration tests, edge case tests)
- Created errata documenting spec contradictions (23 errata total)

Tool usage: 2,272 Bash calls, 1,459 Reads, 163 Edits, 89 Writes, 42 Agent calls — reasonable mix.
But 36% of sessions produced no code changes. The coder archetype is being used as an expensive verifier when the actual verifier archetype already exists.

Verifier — WORKING, MODERATE VALUE
9 sessions, 134 verification results (133 PASS, 1 FAIL). The FAIL for 04-REQ-7.E1 (missing test for JSON validation error path in broker_client.rs) is a legitimate gap — but it's 
unclear if this finding was ever acted on. The verifier produces structured verdicts but there's no evidence the pipeline routes failures back into the coder loop.

---
3. Knowledge System Evaluation

What's providing real value:

1. Errata flow (reviewer → errata store → coder injection): The strongest feedback loop. 23 errata captured real spec contradictions. Session summaries show coders 
explicitly referencing them: "Updated errata §4 documenting the --vss vs --metadata discovery", "Created erratum documenting the deviation from design spec."
2. Pre-review blocking: The pre-review → errata → retry pipeline caught 4 specs with critical issues before coding started, preventing wasted implementation effort.
3. Review finding injection: The fox_provider consistently retrieves and injects prior findings. Knowledge grows over time — 07_update_service went from 0 review + 0 errata to 13 review + 6 errata. Coder summaries frequently say "Addressed prior review finding" with specifics.

What's theater or broken:

1. retrieval_summary — EMPTY: The column exists in session_outcomes but is NULL for all 8 recorded sessions. There's no way to tell what knowledge agents actually consumed vs. what was injected but ignored.
2. coverage_data — EMPTY: Same — the column exists but is never populated. No test coverage tracking despite the schema supporting it.
3. review_findings — EMPTY AT REST: Despite inserting 300+ findings across both runs, the table has 0 rows. The knowledge doesn't survive. This makes cross-run learning impossible.
4. drift_findings — 0 ROWS: Drift detection was skipped for all specs ("no existing code to validate"). Correct for greenfield, but the feature is completely untested in this scenario.
5. session_outcomes — BARELY POPULATED: Only 8 of 83+ sessions have outcome records. The interrupted run's data was lost. The system can't learn from 90%+ of the work it did.
6. No-work dispatch: The knowledge system doesn't prevent dispatching to task groups that are already complete. 36% waste rate in coder sessions suggests the plan graph doesn't consult completion state before dispatch.
7. Plan version mismatch: plan_meta shows version: '3.3.1' but the tool is 3.3.2. The plan was likely carried forward and not regenerated, meaning new planner improvements in 3.3.2 may not be reflected.

---
Summary Verdict

The archetype system is working. Reviewers catch real bugs, coders fix them, verifiers confirm. The reviewer→errata→coder pipeline is the strongest feature.

The knowledge system is half-theater. The errata and review-finding injection into coders provides genuine value. 
But the persistence layer is broken: review_findings empties itself, session_outcomes only captures 10% of sessions, retrieval_summary and coverage_data 
are never populated, and drift_findings is completely dormant. The database schema promises cross-run learning but delivers within-run coordination at best.

The biggest implementation issues are:
1. 36% coder sessions doing no work (plan graph over-dispatch)
2. Phantom task group dispatch (off-by-one in plan generation)
3. review_findings table not persisting
4. Interrupted run data loss in session_outcomes and runs
5. Double dispatch of 01_project_setup:2