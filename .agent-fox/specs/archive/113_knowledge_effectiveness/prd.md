> **SUPERSEDED** by spec 114_knowledge_decoupling

# PRD: Knowledge System Effectiveness

## Problem Statement

The knowledge system is largely theater. An end-to-end evaluation on a
9-spec parking-fee-service build (84 sessions, $89 cost) revealed that the
knowledge pipeline produced no actionable value during execution:

1. **Zero live knowledge extraction.** The 2000-char transcript minimum
   blocked every session because the "transcript" passed to extraction is
   actually the session summary (1-3 sentences, 350-918 chars), not the
   full LLM conversation. All 166 facts were ingested at end-of-run
   consolidation — after all coding was finished.

2. **Git facts are noise.** 53% of git-category facts had low confidence.
   Raw commit messages — especially squash-merge boilerplate — are stored
   verbatim at high confidence, flooding retrieval results with text that
   duplicates `git log`.

3. **Entity signal is dead.** The AdaptiveRetriever's entity graph signal
   always receives `touched_files=[]` because retrieval happens before
   coding. The entity graph (1,752 entities, 1,634 edges) is built at
   end-of-run but never queried during sessions.

4. **Audit reports have no downstream consumer.** Audit-review reports are
   written to `.agent-fox/audit/` during the run, then deleted at end-of-run
   with no intermediate consumer.

5. **Compaction barely triggers.** Only 1 fact superseded out of 166 — the
   knowledge base is append-only noise accumulation.

6. **Review findings are the real knowledge system.** The 80 pre-review
   findings genuinely influenced coder behavior (5 documented instances),
   but they travel via direct prompt injection, not through the
   memory_facts/embedding pipeline.

## Goals

- Make the knowledge extraction pipeline produce facts during execution,
  not just at end-of-run.
- Eliminate noise from the fact store so retrieval returns high-signal
  context.
- Activate the entity graph signal so code-structure-aware retrieval works.
- Give audit reports a downstream consumer so their analysis influences
  subsequent coder sessions.
- Improve compaction so the fact store converges toward curated knowledge
  rather than unbounded accumulation.
- Handle cold-start gracefully — skip retrieval overhead when no facts
  exist.

## Design Decisions

1. **Full transcript capture (Q1).** The full LLM conversation transcript
   will be captured from the Claude SDK session and passed to knowledge
   extraction. The agent trace JSONL file (`audit_dir/agent_{run_id}.jsonl`)
   already records every `assistant.message` event via `AgentTraceSink`.
   The extraction pipeline will reconstruct the conversation from these
   trace events rather than relying on the 1-3 sentence session summary.

2. **LLM-powered git commit extraction (Q2).** Instead of storing raw
   commit messages verbatim, the system will use an LLM call to extract
   structured knowledge from commit messages — decisions, patterns,
   gotchas — at ingestion time. Raw messages that yield no extractable
   knowledge will not be stored as facts.

3. **Entity signal activation via post-session touched files (Q3).** The
   entity signal will use touched files from *prior completed sessions*
   for the same spec. After a coder session completes and produces
   `touched_files`, those paths are already stored in `session_outcomes`.
   The retriever will query `session_outcomes` for the current spec's
   prior touched paths and pass them to the entity signal.

4. **Audit reports as review findings + prompt injection (Q4).** Audit
   report content will be both (a) persisted as review findings in the
   database and (b) injected into subsequent coder sessions for the same
   spec, similar to how pre-review findings are already injected.

5. **Retrieval quality improvements (Q5).** The spec also covers
   compaction aggressiveness, confidence recalibration, and overall
   retrieval quality validation.

6. **Cold-start skip (Q6).** When no facts exist for the current spec
   (and no global facts exceed the confidence threshold), the retriever
   will skip the retrieval pipeline entirely and log a debug message
   rather than executing four empty signal queries.

## Non-Goals

- Replacing the review findings system (it already works).
- Changing the AdaptiveRetriever's RRF fusion algorithm or signal weights.
- Adding new signal types beyond the existing four.
- Modifying the embedding model or dimensions.

## Source

Source: https://github.com/agent-fox-dev/agent-fox/issues/504
