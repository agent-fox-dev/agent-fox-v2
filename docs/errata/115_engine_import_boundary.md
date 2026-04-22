# Erratum: Engine Import Boundary (115-REQ-10.3)

**Spec:** 115 — Pluggable Knowledge Provider
**Requirement:** 115-REQ-10.3
**Date:** 2026-04-22

## Divergence

REQ-10.3 states:

> THE engine SHALL NOT import any module from `agent_fox/knowledge/` other
> than `provider.py`, `db.py`, `review_store.py`, `audit.py`, `sink.py`,
> `duckdb_sink.py`, `blocking_history.py`, `agent_trace.py`, and
> `migrations.py`.

Two divergences from this requirement:

### 1. `fox_provider` added to allowed set

REQ-10.1 requires `run.py` to construct `FoxKnowledgeProvider`, which
necessarily imports `fox_provider`. The test spec (TS-115-34) already
accounts for this by including `fox_provider` in the allowed set.

### 2. `knowledge_harvest.py` excluded from boundary check

`agent_fox/engine/knowledge_harvest.py` is the knowledge-engine integration
pipeline that predates spec 115. It imports from `causal`, `extraction`,
`lifecycle`, `store`, `embeddings`, and `sink` — all knowledge-internal
modules. This module is the designated integration point between the engine
and the knowledge system and cannot operate without these imports.

The import boundary test (TS-115-34) excludes `knowledge_harvest.py` from
the scan to avoid false positives from this pre-existing coupling.

## Rationale

The intent of REQ-10.3 is to prevent core engine modules from tightly
coupling to knowledge internals. `knowledge_harvest.py` is specifically the
knowledge extraction pipeline and is expected to use knowledge internals.
Enforcing the boundary on it would require restructuring the entire
knowledge extraction system, which is out of scope for spec 115.
