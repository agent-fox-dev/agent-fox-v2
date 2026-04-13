# Errata: Spec 96 Property Test File Naming

**Spec:** 96_knowledge_consolidation
**Section:** tasks.md, task 1.4

## Deviation

The `tasks.md` for spec 96 specifies the property test file as:

```
tests/property/knowledge/test_consolidation_props.py
```

However, this file already exists and contains tests for spec 39
(DuckDB consolidation store — TS-39-P2, TS-39-P3, TS-39-P4).
Overwriting it would delete existing spec 39 property tests.

## Resolution

The spec 96 property tests are placed in:

```
tests/property/knowledge/test_knowledge_consolidation_props.py
```

This name is unambiguous and avoids breaking spec 39's test coverage.

## Impact

- No spec 39 tests are affected.
- All spec 96 property tests (TS-96-P1 through TS-96-P6) are covered.
- The test command in tasks.md must use the actual filename:
  ```
  uv run pytest -q tests/property/knowledge/test_knowledge_consolidation_props.py
  ```
