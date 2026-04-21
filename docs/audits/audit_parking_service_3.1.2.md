# Analysis of agent-fox v3.1.2 Run on parking-fee-service

## Overview

  A single run executed 84 sessions across 9 specs with 83 plan nodes (all completed), using claude-sonnet-4-6 throughout. Total cost: $89.20 (197k input / 1.4M output tokens). Four distinct archetypes operated: coder (57 sessions), reviewer (18 sessions), verifier (9 sessions), and one implicit merge-agent
  invocation.

  ---

## Anomalies & Issues

  Session timeout with silent retry (03_locking_service:1)

- The first attempt at 03_locking_service:1 (coder) recorded status=timeout with 0 tokens, 0 cost, 0ms duration — a ghost session. The audit log shows session.fail with "error_message": "Unknown error". The engine then retried (attempt=2) which succeeded with 32k output tokens over 11m39s. The concerning part: the
  failure is logged as "Unknown error" with zero metrics — this suggests the session may have died before any API call was made (possibly a worktree or branch setup failure), but the error is completely opaque. The timeout_override=45 set on the retry session is also interesting — the engine applied a time limit,
  suggesting it detected the first attempt was too long, yet the metrics say 0ms. This is the clearest bug signal: a session recorded 0ms duration but was classified as a timeout.

  Git push race condition (line 359-362)

- develop -> develop (cannot lock ref) — a transient push failure when two merge sequences completed near-simultaneously. The engine recovered (subsequent push succeeded), but the warning path worked correctly here. Not a bug per se, but it reveals that merges and pushes aren't fully serialized despite the merge
  lock; the lock covers merge-to-develop but the push happens after lock release, creating a TOCTOU window.

  Knowledge extraction never fires

- Every single coder session had its transcript flagged as "too short" (minimum 2000 chars). The session summaries shown in the log are 350-918 chars, all well under the threshold. This means zero knowledge was extracted from LLM transcripts during the entire run. The 159 git-category facts and 7 errata were
  ingested from git commits and errata files at end-of-run, not from live session intelligence. The 2000-char minimum may be too high, or the "transcript" being measured isn't the full session transcript but just the summary.

  Reviewer sessions produce no commits (by design, but worth noting)

- All 18 reviewer sessions show "No new commits on feature branch relative to develop, skipping harvest." This is correct — reviewers don't code — but it means the "Skipping LLM knowledge extraction for reviewer archetype" log message is redundant; reviewers never produce harvestable material.

  ---

## Archetype Effectiveness

  Reviewer (pre-review, Skeptic)

- Produced 80 review findings (3 critical, 35 major, 35 minor, 7 observations) across all 9 specs. These were genuinely actionable: the session summaries from coder sessions reference Skeptic findings at least 5 times by name:
  - 04_cloud_gateway_client:1 — "Created errata doc addressing 4 Skeptic findings"
  - 03_locking_service:1 — "Addressed major review findings: added boundary tests for 1.0 km/h threshold"
  - 05_parking_fee_service:3 — "endpoint fallback per Skeptic review finding"
  - 06_cloud_gateway:3 — "addresses Skeptic major finding on the Stop()==false race"
  - 08_parking_operator_adaptor:5 — "The skeptic critical finding (TS-08-SMOKE-3) was addressed"
- Verdict: genuinely working. The reviewer found real spec contradictions and design gaps, and coders demonstrably acted on them.

  Reviewer (audit-review)

- 9 audit-review sessions ran after the first coder task group. They wrote audit reports to .agent-fox/audit/. No direct evidence in the log of these audit reports influencing subsequent coder behavior (the audit reports were cleaned up at end-of-run). Their value may be more for human review than automated
  feedback.

  Verifier

- 9 verifier sessions ran as the final node per spec. Produced 295 verification results (293 PASS, 2 FAIL). The two failures are legitimate:
  - 02_data_broker — image tag mismatch (0.5.0 vs spec 0.6.1) and flag syntax divergence
  - 03_locking_service — missing resubscribe retry limit implementation
- Verdict: working and honest. The verifier didn't rubber-stamp everything — it caught genuine spec deviations. The 99.3% pass rate is reasonable given that coders had already iterated through multiple task groups.

  Coder

- 57 sessions, all completed (1 after retry). Successfully implemented 9 complete specs from scratch across a polyglot Rust+Go monorepo with proto definitions, docker-compose, and integration tests. Produced errata docs when diverging from specs. The TDD approach (failing tests first, then implementation) executed
  correctly across the board.

  Merge Agent

- Invoked twice (lines 343-344, 385-387) to resolve merge conflicts when parallel branches touched overlapping files. Both times it resolved conflicts and the merge succeeded. Minimal but effective.

  ---

## Knowledge System Evaluation

  What's actually in it:

  ┌──────────┬───────┬────────────────┬──────────────────────────────────┐
  │ Category │ Count │ Avg Confidence │              Source              │
  ├──────────┼───────┼────────────────┼──────────────────────────────────┤
  │ git      │ 159   │ 0.66           │ End-of-run git commit ingestion  │
  ├──────────┼───────┼────────────────┼──────────────────────────────────┤
  │ errata   │ 7     │ 0.90           │ End-of-run errata file ingestion │
  └──────────┴───────┴────────────────┴──────────────────────────────────┘

  The knowledge system is largely theater for this run. Here's why:

  1. Zero live knowledge extraction. The 2000-char transcript minimum meant no knowledge was extracted during execution. All 166 facts were ingested at end-of-run consolidation — after all coding was already finished. By definition, this knowledge could not have influenced any coding session.
  2. Git facts are low quality. 85 of 159 git facts (53%) have confidence 0.45 — the bottom tier. Samples show these are raw squash-merge commit messages and housekeeping commits ("hard reset before running on v3.1.0", "back to the baseline for 3.0.1 test"). These are noise, not knowledge.
  3. Entity graph is populated but disconnected from decisions. 1,752 entities with 1,634 edges were created by static analysis at end-of-run. The fact-entity linkage (7,747 links) connects git commit facts to code entities, which could be useful for future queries ("what changed function X?"). But there's no evidence
   this graph was queried during the run.
  4. Memory embeddings exist (166 rows with 384-dim vectors) but with no visible retrieval path during sessions.
  5. The review findings are the real knowledge system. The 80 findings from pre-review actually influenced coder behavior (5 documented instances). These travel via a different path — injected directly into coder prompts, not through the memory_facts/embedding pipeline.
  6. Only 1 fact superseded out of 166 — the compaction system barely triggered (166→165). This suggests the knowledge base is append-only noise accumulation rather than a curated, evolving understanding.

  Bright spots:

- Errata ingestion works and has reasonable confidence (0.90)
- The entity graph + static analysis infrastructure is solid — 1,789 entities across Go, Rust, and JSON
- Review findings genuinely influenced outcomes
- Verification results provide honest pass/fail signals

  Structural issues to investigate:

- The 2000-char transcript minimum for knowledge extraction needs tuning — it locked out every session in this run
- Git commit ingestion at 0.45 confidence for squash commits is noise; consider filtering these more aggressively
- The embedding/retrieval pipeline may not be wired into session prompts — no evidence of semantic fact recall during coding
- The audit-review reports are written and deleted with no clear downstream consumer

  ---

## Summary

  The orchestration engine is solid — 83/83 tasks completed, concurrent execution with merge locks worked, escalation/retry handled the one failure, and the barrier system correctly gated dependent work. The reviewer and verifier archetypes are genuinely working and influencing code quality. But the knowledge system
  (memory_facts, embeddings, entity graph) is mostly write-only theater for this run — review findings deliver the real cross-session intelligence, and they travel through a separate mechanism. The most actionable bugs to investigate are the 0ms/0-token timeout on 03_locking_service:1 and the transcript length
  threshold that suppressed all knowledge extraction.
