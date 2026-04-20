# PRD: Structured Knowledge Records for Skeptic/Verifier Output

## Problem

Spec 26 (Agent Archetypes) introduced Skeptic and Verifier agents that produce
markdown files as their primary output:

- **Skeptic** writes `.specs/{spec_name}/review.md` with severity-categorized
  findings (critical, major, minor, observation).
- **Verifier** writes `.specs/{spec_name}/verification.md` with per-requirement
  PASS/FAIL verdicts.

These files are read back into the Coder's context via `prompt.py`'s
`_SPEC_FILES` list. This approach has several architectural issues:

1. **Dead-end artifacts** — The markdown files sit in `.specs/` as local-only
   state that doesn't participate in the project's version history or knowledge
   pipeline.
2. **Disconnected from the knowledge store** — Agent Fox already has a
   DuckDB-based knowledge pipeline with facts, embeddings, causal links, and
   session outcomes. Skeptic/Verifier findings bypass this entirely.
3. **Redundant with GitHub issues** — `github_issues.py` files GitHub issues
   for blocking findings. The markdown files duplicate this information.
4. **Unstructured data** — While `convergence.py` parses findings into
   `Finding` dataclasses for multi-instance dedup, the upstream data (markdown)
   requires fragile parsing.
5. **Fragile context handoff** — The Coder receives Skeptic/Verifier output by
   reading raw markdown files. Format drift degrades context quality silently.

## Proposed Solution

Replace file-based output with **structured DuckDB records** using the existing
knowledge pipeline:

### Structured output from agents

Change Skeptic and Verifier templates to instruct agents to output structured
JSON (one JSON block per finding/verdict). The session runner parses this
structured output after the agent completes and ingests records into DuckDB.

### New DuckDB tables

- `review_findings` — Skeptic findings: severity, description, requirement
  reference, spec_name, task_group, session_id.
- `verification_results` — Verifier verdicts: requirement_id, verdict
  (PASS/FAIL), evidence text, spec_name, task_group, session_id.

Both tables support supersession (re-runs produce new records that supersede
old ones) and link into the causal graph.

### On-the-fly context rendering

Instead of reading static files, `prompt.py` queries DuckDB and renders
findings/verdicts into markdown for the Coder's context window. Same UX, live
queryable backing store.

### Causal graph integration

Findings and verdicts get causal links to the session that produced them,
the spec they evaluate, and any predecessor records they supersede.

### Convergence on DB records

`convergence.py` operates directly on DB records instead of parsed markdown,
eliminating the parsing layer.

### GitHub issue sourcing from DB

`github_issues.py` sources finding text from DB records rather than markdown.

## Scope

- New DuckDB tables (`review_findings`, `verification_results`) with schema
  migration.
- Ingestion module to parse structured agent output and write to DuckDB.
- Updated Skeptic/Verifier templates for structured JSON output.
- Updated `prompt.py` to render context from DB queries.
- Updated `convergence.py` to work with DB records.
- Updated `github_issues.py` to source from DB records.
- Backward-compatibility: migrate any existing `review.md` /
  `verification.md` files on first run.

## Out of Scope

- Changes to Coder, Librarian, or Cartographer archetypes.
- Changes to the embedding pipeline (findings are stored as structured records,
  not embedded text — semantic search is not a goal here).
- Changes to the session runner's core loop (only the post-processing step
  changes).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 26_agent_archetypes | 8 | 1 | Skeptic/Verifier archetypes, convergence, and github_issues defined in group 8; this spec modifies their output pipeline |
| 11_duckdb_knowledge_store | 3 | 2 | DuckDB schema, KnowledgeDB, and fact storage from group 3; this spec adds new tables |

## References

- GitHub Issue: #117
- Spec 26: `.specs/26_agent_archetypes/`
- Knowledge pipeline: `agent_fox/knowledge/`
- Session modules: `agent_fox/session/`
