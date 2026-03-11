# Errata: DuckDB confidence column uses DOUBLE not FLOAT

**Spec:** 37_confidence_normalization
**Design reference:** DuckDB Migration (v6) section

## Divergence

The design document specifies using `FLOAT` for the DuckDB `memory_facts.confidence`
column and migration version `v6`. The implementation uses:

- **`DOUBLE`** instead of `FLOAT` — DuckDB's `FLOAT` type is 32-bit IEEE 754,
  which introduces precision errors for the canonical mapping values (e.g.,
  `0.9` becomes `0.8999999761581421`). `DOUBLE` (64-bit) preserves exact values
  for the canonical mapping and round-trip comparisons.

- **Migration version `v5`** instead of `v6` — the design assumed the latest
  migration was `v5` (from spec 34 token tracking), but the actual latest is
  `v4` (drift_findings from spec 32). Migration v5 is therefore correct.

## Rationale

Using `DOUBLE` ensures that `parse_confidence("high")` returns `0.9` and
querying `SELECT confidence FROM memory_facts WHERE confidence = 0.9` matches
correctly without floating-point tolerance issues.
