# Errata: Skipped Test Removal (Specs 103, 104)

## Context

Spec 104 (`104_adaptive_retrieval`) removed legacy JSONL-based fact storage,
cross-spec retrieval, and confidence-aware filtering. Spec 103 refactored
sinks and removed `JsonlSink`. The underlying code was deleted, but 25 tests
were left behind as `pytest.skip()` stubs rather than being removed outright.

This errata documents their removal.

## Fully Deleted Test Files (9 files)

These files contained only skipped tests and were deleted in their entirety.

| File | Skip Reason |
|------|-------------|
| `tests/integration/engine/test_cross_spec_retrieval_smoke.py` | Legacy cross-spec retrieval removed per spec 104-REQ-6 |
| `tests/property/engine/test_cross_spec_retrieval_props.py` | Legacy cross-spec retrieval removed per spec 104-REQ-6 |
| `tests/property/knowledge/test_filter_props.py` | Legacy function removed per spec 104-REQ-6 |
| `tests/property/knowledge/test_knowledge_context_props.py` | Legacy function removed per spec 104-REQ-6 |
| `tests/unit/engine/test_cross_spec_retrieval.py` | Legacy cross-spec retrieval removed per spec 104-REQ-6 |
| `tests/unit/engine/test_fact_cache.py` | Legacy function removed per spec 104-REQ-6 |
| `tests/unit/knowledge/test_filter.py` | Legacy function removed per spec 104-REQ-6 |
| `tests/unit/knowledge/test_knowledge_context.py` | Legacy function removed per spec 104-REQ-6 |
| `tests/unit/knowledge/test_store.py` | Legacy function removed per spec 104-REQ-6 |

## Partially Edited Test Files (8 files)

These files had a mix of active and skipped tests. Only the skipped
tests/classes were removed; active tests remain unchanged.

### tests/property/test_review_visibility_props.py

| Removed | Reason |
|---------|--------|
| `TestResponseTruncationProperty` class | JsonlSink removed in refactor(103); `_truncate_response` no longer exists |

### tests/unit/cli/test_knowledge_wiring.py

| Removed | Reason |
|---------|--------|
| `TestKnowledgeInjectionIntoContext.test_memory_facts_passed_to_context` | Legacy function removed per spec 104-REQ-6 |
| `TestKnowledgeInjectionIntoContext.test_empty_facts_passes_none` | Legacy function removed per spec 104-REQ-6 |
| `TestSinkWiring.test_sink_records_outcome_on_completion` | Legacy function removed per spec 104-REQ-6 |
| `TestSinkWiring.test_sink_failure_does_not_block_session` | Legacy function removed per spec 104-REQ-6 |

### tests/unit/knowledge/test_confidence.py

| Removed | Reason |
|---------|--------|
| `TestJsonlConfidence.test_write_float_confidence` | JSONL `append_facts` removed per spec 104-REQ-6 |

### tests/unit/knowledge/test_confidence_filter.py

| Removed | Reason |
|---------|--------|
| `TestConfidenceFiltering.test_threshold_filtering` | `select_relevant_facts` removed per spec 104-REQ-6 |
| `TestConfidenceFiltering.test_filter_before_scoring` | `select_relevant_facts` removed per spec 104-REQ-6 |
| `TestConfidenceFiltering.test_default_threshold` | `select_relevant_facts` removed per spec 104-REQ-6 |

### tests/unit/knowledge/test_consolidation_store.py

| Removed | Reason |
|---------|--------|
| `TestJSONLExport` class | `export_facts_to_jsonl` removed per spec 104-REQ-6 |
| `TestJSONLExportFailure` class | `export_facts_to_jsonl` removed per spec 104-REQ-6 |

### tests/property/knowledge/test_consolidation_props.py

| Removed | Reason |
|---------|--------|
| `TestExportImportRoundTrip` class | `export_facts_to_jsonl` removed per spec 104-REQ-6 |

### tests/unit/knowledge/test_package_consolidation.py

| Removed | Reason |
|---------|--------|
| `TestModuleExistence.test_filtering_module` | Legacy function removed per spec 104-REQ-6 |

### tests/unit/knowledge/test_read_all_facts.py

| Removed | Reason |
|---------|--------|
| `TestReadAllFactsFallbackToJSONL` class | JSONL fallback removed per spec 104-REQ-6 |
| `TestReadAllFactsFallbackOnConnFailure.test_falls_back_to_jsonl_on_all_db_failure` | JSONL fallback removed per spec 104-REQ-6 |
