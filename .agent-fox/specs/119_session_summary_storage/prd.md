# PRD: Session Summary Storage

## Problem

Session summaries are the richest natural-language artifacts produced during a
run. Each coding session generates a summary describing what was built, what
was fixed, and what was left unfinished (e.g., "Implemented task group 3 for
spec 01_audit_hub: SQLite store with WAL mode, busy timeout, and purge
operations"). These summaries are currently:

1. Written to an ephemeral `.agent-fox/session-summary.json` file in the
   worktree, read once by `session_lifecycle.py`, logged to stdout, and then
   deleted.
2. **Not stored in the database.** The `session.complete` audit event payload
   contains `archetype`, `model_id`, `input_tokens`, `output_tokens`, `cost`,
   `duration_ms`, and `files_touched` — but no summary.
3. **Not available to downstream sessions.** The knowledge provider
   (`FoxKnowledgeProvider`) serves review findings, errata, ADRs, and
   verification verdicts, but has no mechanism to serve summaries of what prior
   sessions built.

This is a significant gap. When a coder session starts task group 5, it has no
database-backed knowledge of what task groups 1–4 actually produced. When two
specs modify the same files (e.g., spec 02 changing the auth model that spec 01
depends on), there is no cross-spec awareness of what changed.

## Solution

Store session summaries in the database and serve them to downstream sessions
through the existing knowledge provider infrastructure.

### Storage

Create a dedicated `session_summaries` table (not a column on
`session_outcomes`). While there is a 1:1 relationship between summaries and
session outcomes, `session_outcomes` is a metrics-oriented table. A separate
table keeps concerns cleanly separated and allows independent querying and
indexing.

The table stores the summary text, keyed by `node_id` and `run_id`, with
metadata for filtering (spec name, task group, archetype, attempt number).

### Retrieval

Extend `FoxKnowledgeProvider.retrieve()` to query stored summaries and inject
them into downstream session prompts using a `[CONTEXT]` prefix, alongside the
existing `[REVIEW]`, `[VERIFY]`, and `[CROSS-GROUP]` prefixes.

**Filtering rules:**
- **Only coder summaries** are served. Reviewer and verifier sessions produce
  structured findings, not build context — their output is already captured via
  review findings and verification verdicts.
- **Only prior task groups** are served. For task group N, serve coder
  summaries from groups 1..N-1 within the same spec. Never serve same-group
  summaries (prevents echo). This mirrors the cross-group pattern but for
  summaries.
- **Cross-spec summaries** are also served, capped separately (like
  cross-group findings). This addresses the blind spot where spec 02 changes
  something that spec 01 depends on.

### Append-Only History

Summaries are **never superseded**. When a task group is retried (attempt 2+),
both the attempt-1 and attempt-2 summaries are retained. Downstream sessions
can see the full history. This differs from review findings (which use
supersession) because summaries describe what was done, not what needs fixing.

### Audit Event Enhancement

Add the summary string to the `session.complete` audit event payload. This
makes the event self-contained for observability and log analysis, without
requiring a separate database query.

### Graceful Degradation

If the `session-summary.json` file is missing (session crash, SDK failure),
store `NULL` in the summary column and skip injection for that session. No
synthetic fallback.

## Design Decisions

1. **Separate table over column on session_outcomes.** The `session_outcomes`
   table is a metrics table with numeric columns and fixed-width fields. Adding
   a variable-length TEXT blob changes its character and complicates queries
   that only need metrics. A separate table with a foreign-key-like
   relationship (on `node_id + run_id`) keeps both tables focused.

2. **Inject via retrieve(), not a separate path.** The knowledge provider
   already has the machinery for formatting, capping, and injecting items. A
   new `[CONTEXT]` prefix type slots in naturally. No new infrastructure
   needed.

3. **Cross-spec summaries served.** The original audit analysis identified
   cross-spec blindness as a key gap. Serving capped cross-spec summaries
   (e.g., "spec 02 changed the AuthConfig struct") gives coders awareness of
   changes from parallel specs that may affect their work.

4. **Only prior groups, coder only.** Reviewers and verifiers produce
   structured output (findings, verdicts) that is already served through
   dedicated channels. Serving their summaries would be redundant noise. The
   prior-groups-only filter prevents echo and keeps context focused on what was
   built before the current task.

5. **Append-only (no supersession).** Summaries describe historical actions,
   not current state. Superseding attempt-1's summary when attempt-2 runs
   would lose the "what went wrong" context. Both attempts' summaries provide
   useful signal.

6. **Add summary to audit event payload.** The `session.complete` event is
   the authoritative record of a session's completion. Including the summary
   makes it self-contained for log analysis and monitoring without requiring a
   database join.

7. **NULL on missing summary, no synthetic fallback.** Synthetic summaries
   from metadata ("Session completed, 5m 31s, 3 files") add no value that
   isn't already in session_outcomes. NULL is honest — it means "no summary
   was produced."

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 105_db_plan_state | 2 | 2 | Uses session_outcomes schema pattern and migrations system from group 2; group 2 is where v11 migration and SessionOutcomeRecord are defined |
| 115_pluggable_knowledge | 4 | 3 | Extends FoxKnowledgeProvider.retrieve() from group 4; group 4 is where provider engine wiring is finalized |

## Source

Source: https://github.com/agent-fox-dev/agent-fox/issues/564
