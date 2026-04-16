# PRD: Hunt Scan Duplicate Detection and `af:ignore` Label

## Problem

The night-shift hunt scan creates GitHub issues for maintenance findings, but
it sometimes files duplicates or close variants of issues that already exist.
The current dedup system uses SHA-256 fingerprinting of
`category + sorted(affected_files)`, which catches exact duplicates but misses
semantic near-duplicates — the same problem reported with a slightly different
file list, reworded title, or different framing from a different hunt category.

Additionally, some findings are false positives: the hunt scanner flags
something that the user considers acceptable. Currently, users can close these
issues, but the scanner rediscovers and re-files them on the next iteration.
There is no mechanism for users to permanently mark a finding as "not an
issue."

## Solution

Enhance the hunt scan dedup pipeline with two complementary mechanisms:

1. **Embedding-based similarity matching** — compute vector embeddings for new
   finding groups and compare them against existing issues (both `af:hunt` and
   `af:ignore`) using cosine similarity. This catches semantic near-duplicates
   that fingerprint matching misses.

2. **`af:ignore` label** — a new platform label that users can assign to hunt
   issues to indicate that the reported finding is not a real issue. Issues
   with this label are used as negative examples during dedup: future findings
   that are semantically similar to an ignored issue are suppressed. Both open
   and closed `af:ignore` issues are considered.

3. **Knowledge system integration** — ingest `af:ignore` signals as
   `anti_pattern` facts in the knowledge store. These facts are then fed into
   the AI critic's system prompt, allowing the critic to proactively drop
   findings that match known false-positive patterns.

## Scope

- **In scope:**
  - Embedding-based similarity matching in the dedup pipeline
  - `af:ignore` label constant, metadata, and `af init` creation
  - Dedup gate that suppresses findings similar to `af:ignore` issues
  - Knowledge ingestion of `af:ignore` signals as `anti_pattern` facts
  - AI critic prompt enhancement with known false positives
  - Configurable similarity threshold
  - Extending existing dedup to check both open and closed issues

- **Out of scope:**
  - Changes to the fingerprint algorithm itself
  - Changes to the `.night-shift` file-based path exclusion (spec 106)
  - Changes to the fix pipeline or spec executor
  - UI for managing ignored issues (users use GitHub's label UI)

## Behaviour

1. **Enhanced dedup pipeline:** After the AI critic consolidates findings into
   `FindingGroup` objects, the dedup pipeline now runs two gates in sequence:
   - `filter_known_duplicates()` — enhanced to fetch both open and closed
     `af:hunt` issues, and to check both fingerprint matches and embedding
     similarity.
   - `filter_ignored()` — new function that fetches both open and closed
     `af:ignore` issues and suppresses finding groups that are semantically
     similar (above the similarity threshold) to any ignored issue.

2. **Embedding computation:** Uses the existing `EmbeddingGenerator` (local
   sentence-transformers model, no API cost) to compute embeddings for:
   - New finding groups (from their title, category, and affected files)
   - Existing issue content (from their title and body)
   Cosine similarity is computed in-memory. Embeddings are computed on-the-fly
   each scan iteration (no caching).

3. **`af:ignore` label:** A new label with a gray color, defined as a constant
   in `platform/labels.py` and added to `REQUIRED_LABELS`. Created
   automatically on `agent-fox init`.

4. **`af:ignore` — user workflow:** When a user sees a hunt-filed issue that
   is not a real problem, they add the `af:ignore` label via GitHub's UI.
   The issue remains open (the user decides when to close it). On the next
   hunt scan, the dedup pipeline detects the label and suppresses similar
   future findings.

5. **Closed issues:** Both open and closed issues with `af:hunt` or
   `af:ignore` labels are checked during dedup. This prevents re-filing
   findings that were already dealt with, even after issues are closed.

6. **Knowledge ingestion:** During the hunt scan pre-phase, the engine fetches
   all `af:ignore` issues and ingests any not-yet-ingested ones as
   `anti_pattern` facts in the knowledge store. Ingested issues are marked
   with an HTML comment (`<!-- af:knowledge-ingested -->`) in the issue body
   to prevent re-ingestion.

7. **AI critic integration:** Before running the AI critic, the engine queries
   the knowledge store for `anti_pattern` facts and appends them to the
   critic's system prompt. The critic uses these to proactively drop findings
   that match known false-positive patterns.

8. **Similarity threshold:** A configurable float (0.0 to 1.0, default 0.85)
   in `[night_shift]` config. Finding groups with cosine similarity above this
   threshold to any existing issue are considered duplicates.

9. **Fail-open behaviour:** If embedding computation fails (model not loaded,
   unexpected error), the pipeline falls back to fingerprint-only matching.
   If the platform API fails, all groups pass through unfiltered (existing
   fail-open pattern preserved).

## Design Decisions

1. **Embedding-based similarity over fuzzy string matching** — vector
   embeddings capture semantic similarity (e.g., "unused import" and "dead
   import") that string-based methods miss. The project already has a local
   sentence-transformers model (`all-MiniLM-L6-v2`) with no API cost.

2. **On-the-fly embedding computation** — caching embeddings (in issue bodies
   or DuckDB) adds complexity. With a local model and typical issue counts
   (~50), on-the-fly computation is fast enough. Caching can be added later
   if needed.

3. **Separate `filter_ignored()` function** — keeps the `af:hunt` dedup
   and `af:ignore` suppression as distinct concerns, each with clear inputs
   and logging.

4. **Both open and closed issues checked** — users may close issues after
   addressing them, but the scanner should not re-file the same finding.
   This is a deliberate trade-off: genuine regressions of the exact same
   issue won't be re-filed automatically. If a user wants regression
   detection, they can remove the `af:ignore` label or clear the
   fingerprint marker.

5. **`af:ignore` does not auto-close** — the label is a signal to the dedup
   pipeline, not a lifecycle action. Users control when to close issues.

6. **Knowledge ingestion marker** — an HTML comment
   (`<!-- af:knowledge-ingested -->`) in the issue body, consistent with how
   fingerprints are embedded. This avoids external state tracking.

7. **Gray label color** — visually distinct from `af:fix` (green) and
   `af:hunt` (blue). Signals "dismissed" or "not actionable."

8. **Configurable threshold with 0.85 default** — 0.85 cosine similarity is
   a standard threshold for near-duplicate detection with sentence-transformers
   models. Configurable so users can tune sensitivity.
