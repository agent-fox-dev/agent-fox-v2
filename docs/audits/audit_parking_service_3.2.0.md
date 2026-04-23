Analysis of agent-fox 3.2.0 Test Runs

1. Anomalies, Errors, and Warnings

Session Timeouts and Interrupts
- Tests 1 and 2 were both killed by the user (SIGINT → double interrupt). Both times, ClaudeBackend stream ended without ResultMessage warnings appeared
during shutdown. This is benign — just the in-flight Claude session being terminated mid-stream.
- 08_parking_operator_adaptor:5 timed out in test 3 after 30 minutes (session_outcomes records status=timeout). The engine successfully retried it with a
timeout_override=45 and it completed on the second attempt (17m 10s). The retry/escalation logic is working, but the original 30-minute default timeout was
too tight for this particular task.

Security Blocking (test 1 only)
- The pre-reviewer flagged 09_mock_apps:1 with a critical security finding (F-1f4960f3), which cascade-blocked all 7 downstream nodes (09_mock_apps:2 through
  :7). This is the correct behavior — the system is designed to halt spec work when the pre-reviewer finds critical issues. However:
  - This only happened in test 1, not in test 2 where the same spec ran without being blocked. The pre-reviewer is non-deterministic; the same spec input
produced a critical finding in one run but not another. This raises questions about the reliability of the security gate.
  - The blocking_history table has 0 rows — the blocking event was not persisted there, even though it clearly happened. This is a bug: the audit trail for
blocking decisions is broken.

Verification Failures
- 7 of 168 verification results are FAIL, all for 08_parking_operator_adaptor. The root cause is identical across all 7: the Go integration tests reference a
  gen/kuksa/val/v1 package that doesn't exist in the gen module. The tests were written but the code generation step was never wired up. The verifier
correctly caught this, but the coder archetype that produced the tests (:5) didn't validate that the proto-generated Go package was available before
committing test code that imports it.

Untracked File Removal During Merge
- In test 3 line 256: Removing 5 untracked file(s) that would block merge: tests/parking-operator-adaptor/go.mod, go.sum, helpers_test.go,
integration_test.go, smoke_test.go. These files were silently deleted to enable the squash merge. This is risky — the harvest/merge logic is destroying work
products that the coder created but didn't commit in the worktree. Worth investigating whether the coder session's git hygiene is consistently failing to
commit these files.

---
2. Agent Archetypes: Are They Actually Working?

Reviewer (pre-review) — Working but non-deterministic. It produces review findings (7-12 per spec) and stores them. The security gate works when triggered.
But the same input produced a critical security block in one run and not another. Finding counts: 7-12 per spec, consistent.

Reviewer (audit-review) — Working well. Produces much richer output: 16-51 findings per spec. These findings are fed back to subsequent coder sessions (e.g.,
  01_project_setup:2 received 43 review items). The audit reports are written to disk and cleaned up after spec completion.

Coder — Working. Successfully implements task groups, runs tests, fixes issues, and merges into develop. Session summaries are detailed and specific
(referencing exact test IDs, test counts, clippy status). The one concern: 09_mock_apps:2 in test 2 completed with no commits and no gotchas — the log shows
No new commits on 'feature/09_mock_apps/2' relative to 'develop', skipping harvest and Ingested 0 gotchas. This looks like a session that did nothing.

Verifier — Working. Produces detailed per-requirement verdicts (25-51 per spec). The 161 PASS / 7 FAIL split shows it's actually validating, not
rubber-stamping. The FAILs are genuine and well-evidenced.

Escalation System — Working. Reviewers start at STANDARD tier (Sonnet), coders escalate to ADVANCED tier (Opus with adaptive thinking). The barrier
synchronization correctly drains in-flight tasks and triggers sync points.

---
3. Knowledge System: Value or Theater?

This is the weakest part of the system. The knowledge database has 17 schema migrations and 22 tables, but the vast majority are empty or filled with noise.

Gotchas — Mostly Theater (246 rows)

This is the most actively populated knowledge store, and it's largely garbage:

- 36% are literally empty complaints about missing context: "**Spec**: unknown", "**Touched files**: none", "**Status**: completed". These are the gotcha
extractor hallucinating when it doesn't have enough session context. They appear identically across all 9 specs.
- Every session produces exactly 3 gotchas (with rare exceptions of 1-2). This is a fixed extraction quota, not driven by actual content. When a session has
nothing noteworthy, the extractor invents filler.
- ~71 gotchas look like real technical insights, but even these are speculative rather than observed. They read like "things that could go wrong" rather than
  things actually encountered: "NATS message ordering and subscription timing", "Geo-coordinates have implicit precision/rounding expectations". Many use
hedging language ("likely", "may", "can").
- 19 gotcha texts appear across 2+ specs identically — the extractor is producing generic boilerplate that isn't spec-specific.
- All 246 gotchas have category "gotcha" — no sub-classification.

Empty Knowledge Tables — The Graph is Unpopulated

┌───────────────────┬──────┬──────────────────────────────────────────────┐
│       Table       │ Rows │                   Concern                    │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ entity_graph      │ 0    │ Code entity tracking never runs              │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ entity_edges      │ 0    │ Relationship graph never populated           │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ memory_facts      │ 0    │ Semantic memory completely empty             │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ memory_embeddings │ 0    │ Embedding store unused                       │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ fact_causes       │ 0    │ Causal knowledge graph empty                 │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ fact_entities     │ 0    │ Fact-entity links empty                      │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ errata_index      │ 0    │ Despite errata docs being created            │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ drift_findings    │ 0    │ Drift review skipped for all specs           │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ blocking_history  │ 0    │ Bug: blocking DID happen but wasn't recorded │
├───────────────────┼──────┼──────────────────────────────────────────────┤
│ sleep_artifacts   │ 0    │ Pre-computed outputs never used              │
└───────────────────┴──────┴──────────────────────────────────────────────┘

The system has infrastructure for a semantic knowledge graph with embeddings, entity tracking, causal chains, and memory facts — none of it is populated.
These features appear to be schema-only with no active code path filling them.

Retrieval Summaries — All NULL

Every session_outcomes.retrieval_summary is NULL. The system has a column to record what knowledge was retrieved and fed to each session, but it's never
populated. This means there's no observability into whether the knowledge being injected into sessions is actually useful.

What IS Working (Review Findings & Verification)

The review_findings (43 rows) and verification_results (168 rows) tables contain genuinely useful, specific content. Review findings identify concrete
missing assertions with severity ratings. Verification results map to specific requirement IDs with evidence. However, these only persist from the most
recent run — they don't accumulate across runs (previous runs' data is superseded).

The logs do show that review findings ARE fed back to coder sessions (e.g., Retrieved 43 items for 01_project_setup: 0 errata, 43 reviews, 0 gotchas), and
the coder summaries reference addressing review findings (e.g., "Addressed all 4 Skeptic major findings"). So the review→coder feedback loop is the one part
of the knowledge system providing real value.

---
Summary

┌───────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────┐
│                     Area                      │                             Verdict                             │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Engine orchestration                          │ Solid — barriers, merge locks, escalation, parallelism all work │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Agent archetypes                              │ All functional; pre-reviewer has non-determinism concern        │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Gotchas system                                │ ~70% noise; fixed-quota extraction produces filler              │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Review→Coder feedback                         │ Working and valuable — the one knowledge loop with clear impact │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Knowledge graph (entities, facts, embeddings) │ Complete theater — 6+ tables with 0 rows                        │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Blocking history                              │ Bug — events not persisted                                      │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Retrieval observability                       │ Broken — all summaries NULL                                     │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Errata indexing                               │ Not functioning — 0 rows despite errata docs existing           │
└───────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────┘

The knowledge system's value is almost entirely carried by the review findings pipeline. The gotcha store needs either major quality improvement
(context-aware extraction, no fixed quota) or removal. The semantic knowledge graph infrastructure (entity tracking, memory facts, embeddings) is dead code
with schema overhead.