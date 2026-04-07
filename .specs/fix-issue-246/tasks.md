# Tasks — Fix Issue #246: Generator fixture return types

## Task Group 1: Fix type annotations

- [x] Update `tests/integration/test_quality_gate.py`: change `integration_db` return type from `duckdb.DuckDBPyConnection` to `Generator[duckdb.DuckDBPyConnection, None, None]` and add `Generator` import
- [x] Update `tests/test_routing/conftest.py`: change `routing_db` return type from `duckdb.DuckDBPyConnection` to `Generator[duckdb.DuckDBPyConnection, None, None]` and add `Generator` import
- [x] Verify lint and tests pass
