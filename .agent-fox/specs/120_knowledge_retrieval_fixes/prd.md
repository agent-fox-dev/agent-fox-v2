# PRD: Knowledge Retrieval Fixes

## Problem

An audit of the knowledge system (af-hub v3.5.3, run cost $111.18) revealed
that the read side of the knowledge system is essentially nonfunctional. The
system stores data but does not use it to inform subsequent sessions:

1. **Session summaries are stored but never retrieved.** The
   `FoxKnowledgeProvider._run_id` field is initialized to `None` and never
   assigned by the engine. Both `_query_same_spec_summaries()` and
   `_query_cross_spec_summaries()` early-return empty lists when `_run_id` is
   falsy. Summaries are successfully stored (because `_store_summary` falls
   back to the context dict's `run_id`), but every `fox_provider` log line
   shows `0 context + 0 cross-spec items`. A coder in group 7 has no idea
   what groups 1-6 built.

2. **Pre-review findings delivered as untracked cross-group context.** The
   group 0 skeptic review produces findings tagged `task_group="0"`. When
   group 1 coder runs with `task_group="1"`, these appear only as
   `[CROSS-GROUP]` items -- not tracked in `finding_injections`, not
   superseded on session completion. The pre-review's purpose (catching spec
   issues before code is written) is undermined because its output is treated
   as informational noise rather than actionable feedback.

3. **Only coder sessions produce summaries.** The `_store_summary()` method
   stores whatever it receives, but the engine only populates `summary` in
   the context dict for coder sessions. Reviewer sessions (what was flagged,
   how many findings) and verifier sessions (pass/fail ratio, which
   requirements failed) produce valuable context that is discarded.

4. **Orphaned findings across runs.** When a run stalls (both runs in the
   audit ended `stalled`), active review findings and FAIL verdicts remain in
   the database with no mechanism to surface them in a subsequent run. The
   af-hub audit left 50 active critical/major findings permanently orphaned.
   A new run starts with zero knowledge of unresolved issues from prior runs.

## Solution

Fix the knowledge retrieval pipeline so that knowledge genuinely accumulates
across sessions and across runs.

### Fix 1: Wire `_run_id` to FoxKnowledgeProvider

Add a `set_run_id(run_id: str)` method to `FoxKnowledgeProvider`. Call it from
the engine immediately after `generate_run_id()`. This unblocks same-spec and
cross-spec summary retrieval -- the existing query logic is correct, it just
never receives the run_id it needs.

### Fix 2: Elevate Pre-Review Findings

When `FoxKnowledgeProvider.retrieve()` is called for a coder session, include
group 0 (pre-review) findings in the primary `_query_reviews()` result set --
not just as cross-group items. This means pre-review findings are:

- Tracked in `finding_injections` (so we know what the coder saw)
- Superseded when the coder session completes (so they don't persist forever)
- Sorted alongside same-group findings by severity and relevance

The change: when `task_group` is provided and is not `"0"`, query
`review_findings` for `task_group IN (?, '0')` instead of `task_group = ?`.
Remove group 0 findings from the cross-group query to avoid duplication.

### Fix 3: All-Archetype Summary Storage

Extend the engine's session completion path to populate the `summary` field
in the context dict for reviewer and verifier sessions. Generate a structured
summary from their output:

- **Reviewer:** Number of findings by severity, top 3 finding descriptions.
- **Verifier:** Pass/fail counts, list of FAIL requirement IDs.

These summaries are stored via the existing `_store_summary()` method and
retrieved via the existing `_query_same_spec_summaries()` query (which already
filters to `archetype='coder'` only). Update the same-spec query to include
all archetypes, so downstream sessions see reviewer and verifier context too.

### Fix 4: Cross-Run Finding Carry-Forward

At the start of a new run, query the database for active (non-superseded)
critical/major review findings and FAIL verdicts from the most recent prior
run. Surface them to the first session of each affected spec as `[PRIOR-RUN]`
context items. These are informational (not tracked for injection) -- they
alert the coder that prior issues exist but do not create supersession
obligations.

Cap at a configurable limit (default: 5 per spec) to avoid overwhelming
the prompt. Findings from the same spec take priority; findings from other
specs that touch the same files are secondary.

## Design Decisions

1. **`set_run_id()` rather than constructor parameter.** The provider is
   constructed before the engine generates the run ID (in `run.py` vs
   `engine.py`). Adding it to the constructor would require restructuring
   the initialization order. A setter is simpler and matches the existing
   pattern (the provider is a long-lived singleton mutated by the engine).

2. **Pre-review findings elevated for all non-zero task groups.** An
   alternative was to only elevate for group 1 (the first coder). But
   pre-review findings may be relevant to any group (e.g., a design concern
   about a module implemented in group 4). Including them for all groups
   and relying on supersession to clear them after the first coder
   addresses them is safer.

3. **Reviewer/verifier summaries are auto-generated, not SDK-produced.**
   The SDK summary comes from the LLM's self-description of what it did.
   Reviewers and verifiers produce structured output (findings, verdicts)
   that can be summarized programmatically. This avoids requiring the
   reviewer/verifier profiles to produce natural-language summaries.

4. **Cross-run carry-forward is informational, not tracked.** Tracking
   cross-run findings for injection/supersession would create complex
   lifecycle management (when does a finding from run N get superseded by
   run N+1?). Informational context (`[PRIOR-RUN]` prefix) is sufficient
   to alert the coder without creating obligations.

5. **Summary retrieval includes all archetypes.** The current
   `query_same_spec_summaries` filters `archetype='coder'`. This filter
   is removed so that reviewer and verifier summaries (once stored) are
   also served. The `[CONTEXT]` prefix already includes the archetype
   in the formatted string.

## Source

Source: /Users/candlekeep/devel/workspace/af-hub/docs/audits/audit_3.5.3_1.md
and interactive analysis of af-hub knowledge.duckdb database.
