# ADR: Structured Review Records in DuckDB

## Status

Accepted

## Context

Skeptic and Verifier agents previously wrote their output as markdown files
(`review.md`, `verification.md`). Downstream consumers (context rendering,
convergence, GitHub issue filing) parsed these files with fragile regex,
leading to data loss on format changes and preventing queryable lifecycle
management.

## Decision

Replace file-based Skeptic/Verifier output with structured JSON that is
parsed after agent completion and ingested into two DuckDB tables:

- `review_findings` -- stores individual Skeptic findings with severity,
  description, requirement references, and supersession tracking.
- `verification_results` -- stores individual Verifier verdicts with
  requirement ID, PASS/FAIL status, and evidence.

Agents are instructed (via updated templates) to emit a JSON block in their
response. The session runner extracts, validates, and inserts records. Context
rendering, convergence, and GitHub issue filing all operate on DB records
instead of files.

### Key design choices

1. **Supersession over deletion.** Re-runs set `superseded_by` on prior
   records rather than deleting them, preserving full history with causal
   links via `fact_causes`.
2. **File fallback.** When the DB connection is unavailable, context assembly
   falls back to reading `review.md` / `verification.md` files, ensuring
   zero downtime during migration.
3. **Legacy migration on first read.** Existing markdown files are parsed and
   ingested into the DB on first context assembly if no DB records exist,
   preventing historical data loss.
4. **Severity normalization.** Unknown severity values are normalized to
   `"observation"` rather than rejected, maximizing data capture from
   potentially non-conforming agent output.

## Consequences

- All Skeptic/Verifier output is queryable via SQL.
- Convergence operates on typed records, eliminating the markdown parsing
  layer.
- Context rendering is deterministic and always reflects the latest DB state.
- Legacy markdown files remain as a fallback but are no longer the primary
  data source.
- Schema migration v2 adds both tables idempotently alongside existing
  knowledge store tables.
