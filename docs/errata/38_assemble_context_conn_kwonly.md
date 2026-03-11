# Errata: assemble_context conn parameter is keyword-only

**Spec:** 38_duckdb_hardening
**Requirement:** 38-REQ-4.1

## Divergence

The design document specifies `conn: duckdb.DuckDBPyConnection` as a
positional parameter in `assemble_context()`. The implementation uses
`*, conn: duckdb.DuckDBPyConnection` (keyword-only) instead.

## Reason

The `conn` parameter was previously `conn: duckdb.DuckDBPyConnection = None`
(the 4th positional parameter, after `memory_facts` which has a default).
Making it required without a default would violate Python syntax rules since
it follows `memory_facts` which retains its `None` default.

Using keyword-only (`*`) avoids reordering parameters which would break all
existing callers. All existing callers already pass `conn=` as a keyword
argument, so this change is backwards-compatible.

## Impact

None. All callers use `conn=` keyword syntax. The type hint correctly
reflects `duckdb.DuckDBPyConnection` (non-optional).
