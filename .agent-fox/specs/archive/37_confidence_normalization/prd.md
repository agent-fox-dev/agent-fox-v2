# PRD: Confidence Normalization

## Problem

The agent-fox codebase uses two incompatible confidence representations:
- **Memory/Knowledge system**: String enum (`"high"`, `"medium"`, `"low"`) via
  `ConfidenceLevel` in `memory/types.py`, stored as TEXT in DuckDB
  `memory_facts` table.
- **Routing/Assessment system**: Float `[0.0, 1.0]` via
  `ComplexityAssessment.confidence` in `routing/types.py`, stored as FLOAT in
  DuckDB `complexity_assessments` table.

This inconsistency prevents threshold-based filtering, cross-system comparisons,
and machine learning integration. Downstream specs (predictive planning,
confidence-aware fact selection) require a unified float representation.

## Source

Extracted from research spike `docs/brainstorm/predictive-planning-and-knowledge.md`
(issue #146), specifically:
- Section 2.1: "No confidence filtering: Low-confidence facts treated equally
  to high-confidence"
- Recommendation #3: "Confidence-aware fact selection — filter low-confidence
  facts, dynamic causal budget"

## Goals

1. Normalize all confidence values to `float [0.0, 1.0]` across the codebase.
2. Migrate DuckDB `memory_facts.confidence` from TEXT to FLOAT.
3. Maintain backward compatibility with existing JSONL memory files.
4. Update all consumers: fact extraction, knowledge queries, pattern detection,
   auto-improve analyzer.

## Scope

**In:**
- `Fact` dataclass confidence field (memory/types.py)
- Fact extraction prompt and parsing (memory/extraction.py)
- Fact rendering (memory/render.py)
- DuckDB schema migration (knowledge/db.py, knowledge/migrations.py)
- JSONL serialization/deserialization (memory/memory.py)
- OracleAnswer confidence (knowledge/query.py)
- Pattern confidence (knowledge/query.py)
- Improvement confidence (fix/analyzer.py)
- ConfidenceLevel enum removal or repurposing

**Out:**
- Routing/Assessment confidence (already float — no changes needed)
- Confidence-aware fact filtering (separate spec: predictive planning)
- DuckDB hardening (separate spec)

## Clarifications

1. Canonical mapping for string-to-float conversion:
   `"high"` → `0.9`, `"medium"` → `0.6`, `"low"` → `0.3`
2. Default confidence for unrecognized or missing values: `0.6`
3. Float values clamped to `[0.0, 1.0]`
4. Existing JSONL files with string confidence must continue loading (backward
   compatible deserialization)
5. New JSONL writes always use float

## Affected Files

| File | Change |
|------|--------|
| `agent_fox/memory/types.py` | Change `Fact.confidence` to `float`, update/remove `ConfidenceLevel` enum |
| `agent_fox/memory/extraction.py` | Parse LLM string → float conversion, update prompt |
| `agent_fox/memory/render.py` | Format confidence as float in display |
| `agent_fox/memory/memory.py` | Handle float serialization in JSONL and DuckDB dual-write |
| `agent_fox/knowledge/db.py` | Update `memory_facts` table schema |
| `agent_fox/knowledge/migrations.py` | Add migration: TEXT → FLOAT with canonical mapping |
| `agent_fox/knowledge/query.py` | Update `OracleAnswer.confidence`, `Pattern.confidence`, `_determine_confidence()`, `_assign_confidence()` |
| `agent_fox/fix/analyzer.py` | Update `Improvement.confidence`, filtering threshold |
| `agent_fox/engine/knowledge_harvest.py` | Update fact sync to DuckDB |
