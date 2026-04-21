# Agent-Fox Memory

## Spec 113: Knowledge System Effectiveness

### Architecture Decisions

- `reconstruct_transcript()` in `agent_trace.py` reads agent trace JSONL
  events filtered by `node_id` and `event_type == "assistant.message"`. It
  returns concatenated content or empty string on missing file / zero matches.
  `_extract_knowledge_and_findings` in `session_lifecycle.py` tries the
  reconstructed transcript first, falling back to `_build_fallback_input()`
  (commit diff + metadata) when the trace is unavailable.

- `ingest_git_commits` in `ingest.py` is now **async**. It batches commits
  into groups of 20, skips messages < 20 chars, and calls
  `_extract_git_facts_llm()` per batch. The LLM returns structured facts with
  categories (`decision`, `pattern`, `gotcha`, `convention`) and variable
  confidence (`high=0.9`, `medium=0.6`, `low=0.3`). Empty LLM results store
  zero facts; LLM failures skip the batch with a warning.
  `run_background_ingestion` was updated to await the async call.

- `_count_available_facts()` in `retrieval.py` implements cold-start detection.
  If zero non-superseded facts match the spec or exceed the confidence
  threshold, `retrieve()` returns early with `cold_start=True` and skips all
  four signal queries. Database errors on the count query fall through to
  normal retrieval (returns `None`, not 0).

- `_substring_supersede()` in `compaction.py` marks facts whose content is a
  substring of another fact with equal or higher confidence as superseded.
  `_filter_minimum_length()` rejects facts shorter than 50 characters at
  ingestion time. Both are integrated into `compact()`.

- `RetrievalResult` gained two fields: `cold_start: bool` and
  `token_budget_used: int`. After RRF fusion, `_emit_retrieval_event()` emits
  a `knowledge.retrieval` audit event (wrapped in try/except to avoid blocking
  the session). The `retrieval_summary` JSON is stored in `session_outcomes`.

- `_query_prior_touched_files()` on `NodeSessionRunner` queries
  `session_outcomes` for prior completed sessions with the same `spec_name`,
  deduplicates touched paths, and limits to 50 most recent. The result is
  passed to `AdaptiveRetriever.retrieve(touched_files=...)` to activate the
  entity signal.

- Audit findings are persisted to `review_findings` with `category='audit'`
  after `persist_auditor_results` writes the markdown report.
  `_build_prompts` injects audit findings for all coder attempts (not just
  retries) via `query_active_findings`.

### Gotchas

- The `superseded_by` column in `memory_facts` is called `supersedes` in the
  actual DuckDB schema (not `superseded_by`). The cold-start count query
  filters on `supersedes IS NULL`.

- `GIT_EXTRACTION_PROMPT` lives in `extraction.py` alongside the existing
  session extraction prompt.

- The 47 lint warnings in `tests/` are all pre-existing `I001` import-sorting
  issues from other specs — not introduced by spec 113.

- The `session_outcomes` table has a `retrieval_summary TEXT` column added by
  migration. It stores a JSON string with `facts_injected`, `signals_active`,
  and `cold_start`.
