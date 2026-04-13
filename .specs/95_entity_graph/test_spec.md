# Test Specification: Entity Graph

## Overview

Tests validate the entity graph subsystem across four layers: unit tests for
each module (entity store, static analysis, entity linker, entity query),
property-based tests for correctness invariants, edge case tests for error
handling, and integration smoke tests for each execution path. All DuckDB
tests use real in-memory connections (no mocking of the database layer).
Git subprocess calls are mocked in unit tests and (where necessary) in smoke
tests.

## Test Cases

### TS-95-1: Entity table schema

**Requirement:** 95-REQ-1.1
**Type:** unit
**Description:** Verify the `entity_graph` table is created with the correct
columns and types after migration v8.

**Preconditions:**
- In-memory DuckDB connection with all migrations applied.

**Input:**
- Query `information_schema.columns` for table `entity_graph`.

**Expected:**
- Columns: `id` (UUID), `entity_type` (VARCHAR), `entity_name` (VARCHAR),
  `entity_path` (VARCHAR), `created_at` (TIMESTAMP), `deleted_at` (TIMESTAMP).

**Assertion pseudocode:**
```
columns = query_columns(conn, "entity_graph")
ASSERT columns == {"id": "UUID", "entity_type": "VARCHAR", ...}
```

### TS-95-2: Entity UUID assignment

**Requirement:** 95-REQ-1.2
**Type:** unit
**Description:** Verify that upserted entities receive UUID v4 identifiers.

**Preconditions:**
- In-memory DuckDB connection with migrations applied.

**Input:**
- Upsert an entity with type=FILE, name="foo.py", path="src/foo.py".

**Expected:**
- Returned ID is a valid UUID v4 string.

**Assertion pseudocode:**
```
entity_id = upsert_entities(conn, [entity])
ASSERT uuid.UUID(entity_id, version=4) is valid
```

### TS-95-3: Path normalization on storage

**Requirement:** 95-REQ-1.3
**Type:** unit
**Description:** Verify that entity paths are normalized to repo-relative
format when stored.

**Preconditions:**
- In-memory DuckDB connection with migrations applied.

**Input:**
- Entity with path="/repo/root/src/foo.py" and repo_root="/repo/root".
- Entity with path="./src/../src/bar.py".
- Entity with path="src/baz.py/".

**Expected:**
- Stored paths: "src/foo.py", "src/bar.py", "src/baz.py".

**Assertion pseudocode:**
```
FOR EACH (input_path, expected_path):
    result = normalize_path(input_path)
    ASSERT result == expected_path
    ASSERT not result.startswith("/")
    ASSERT ".." not in result.split("/")
```

### TS-95-4: Entity type support

**Requirement:** 95-REQ-1.4
**Type:** unit
**Description:** Verify all four entity types can be stored and retrieved.

**Preconditions:**
- In-memory DuckDB connection with migrations applied.

**Input:**
- One entity of each type: file, module, class, function.

**Expected:**
- All four entities are stored and retrievable by path.

**Assertion pseudocode:**
```
FOR EACH entity_type IN [FILE, MODULE, CLASS, FUNCTION]:
    upsert_entities(conn, [Entity(type=entity_type, ...)])
    results = find_entities_by_path(conn, path)
    ASSERT any(e.entity_type == entity_type for e in results)
```

### TS-95-5: Edge table schema

**Requirement:** 95-REQ-2.1
**Type:** unit
**Description:** Verify the `entity_edges` table schema after migration v8.

**Preconditions:**
- In-memory DuckDB connection with migrations applied.

**Input:**
- Query `information_schema.columns` for table `entity_edges`.

**Expected:**
- Columns: `source_id` (UUID), `target_id` (UUID), `relationship` (VARCHAR).
- Composite primary key on all three.

**Assertion pseudocode:**
```
columns = query_columns(conn, "entity_edges")
ASSERT columns == {"source_id": "UUID", "target_id": "UUID", "relationship": "VARCHAR"}
```

### TS-95-6: Edge relationship types

**Requirement:** 95-REQ-2.2
**Type:** unit
**Description:** Verify all three relationship types can be stored.

**Preconditions:**
- Two entities exist in `entity_graph`.

**Input:**
- Create edges with relationships: contains, imports, extends.

**Expected:**
- All three edges are stored.

**Assertion pseudocode:**
```
FOR EACH rel IN [CONTAINS, IMPORTS, EXTENDS]:
    upsert_edges(conn, [EntityEdge(source_id, target_id, rel)])
    ASSERT edge exists in entity_edges
```

### TS-95-7: Edge referential integrity

**Requirement:** 95-REQ-2.3
**Type:** unit
**Description:** Verify that edges with missing endpoints are rejected.

**Preconditions:**
- One entity exists; one UUID does not exist in `entity_graph`.

**Input:**
- Edge with valid source_id but non-existent target_id.
- Edge with non-existent source_id but valid target_id.

**Expected:**
- Both raise an error.

**Assertion pseudocode:**
```
ASSERT RAISES error: upsert_edges(conn, [edge_with_bad_target])
ASSERT RAISES error: upsert_edges(conn, [edge_with_bad_source])
```

### TS-95-8: Edge deduplication

**Requirement:** 95-REQ-2.4
**Type:** unit
**Description:** Verify duplicate edges are silently ignored.

**Preconditions:**
- Two entities and one edge between them exist.

**Input:**
- Upsert the same edge again.

**Expected:**
- No error. Edge count remains 1.

**Assertion pseudocode:**
```
upsert_edges(conn, [edge])
upsert_edges(conn, [edge])
count = conn.execute("SELECT COUNT(*) FROM entity_edges").fetchone()[0]
ASSERT count == 1
```

### TS-95-9: Fact-entity table schema

**Requirement:** 95-REQ-3.1
**Type:** unit
**Description:** Verify the `fact_entities` table schema after migration v8.

**Preconditions:**
- In-memory DuckDB connection with migrations applied.

**Input:**
- Query `information_schema.columns` for table `fact_entities`.

**Expected:**
- Columns: `fact_id` (UUID), `entity_id` (UUID).
- Composite primary key on both.

**Assertion pseudocode:**
```
columns = query_columns(conn, "fact_entities")
ASSERT columns == {"fact_id": "UUID", "entity_id": "UUID"}
```

### TS-95-10: Fact-entity referential integrity

**Requirement:** 95-REQ-3.2
**Type:** unit
**Description:** Verify that fact-entity links with missing references are
rejected.

**Preconditions:**
- One entity exists in `entity_graph`. One fact exists in `memory_facts`.

**Input:**
- Link with valid fact_id but non-existent entity_id.
- Link with non-existent fact_id but valid entity_id.

**Expected:**
- Both raise an error.

**Assertion pseudocode:**
```
ASSERT RAISES error: create_fact_entity_links(conn, fake_fact_id, [entity_id])
ASSERT RAISES error: create_fact_entity_links(conn, fact_id, [fake_entity_id])
```

### TS-95-11: Fact-entity deduplication

**Requirement:** 95-REQ-3.3
**Type:** unit
**Description:** Verify duplicate fact-entity links are silently ignored.

**Preconditions:**
- One fact and one entity exist. One link between them exists.

**Input:**
- Create the same link again.

**Expected:**
- No error. Link count remains 1.

**Assertion pseudocode:**
```
create_fact_entity_links(conn, fact_id, [entity_id])
create_fact_entity_links(conn, fact_id, [entity_id])
count = conn.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]
ASSERT count == 1
```

### TS-95-12: Python file scanning

**Requirement:** 95-REQ-4.1
**Type:** unit
**Description:** Verify that analysis scans all `.py` files, excluding
`.gitignore`-matched files.

**Preconditions:**
- Temp directory with: `src/a.py`, `src/b.py`, `build/c.py`, and a
  `.gitignore` containing `build/`.

**Input:**
- `_scan_python_files(repo_root)`.

**Expected:**
- Returns `[src/a.py, src/b.py]` (excludes `build/c.py`).

**Assertion pseudocode:**
```
files = _scan_python_files(repo_root)
ASSERT set(f.name for f in files) == {"a.py", "b.py"}
```

### TS-95-13: Entity extraction from Python file

**Requirement:** 95-REQ-4.2
**Type:** unit
**Description:** Verify that tree-sitter extracts file, class, and function
entities from a Python file.

**Preconditions:**
- A Python file containing a class `Foo` with method `bar`, and a top-level
  function `baz`.

**Input:**
- Parse file with tree-sitter, call `_extract_entities(tree, "src/example.py")`.

**Expected:**
- Entities: file("example.py", "src/example.py"),
  class("Foo", "src/example.py"),
  function("Foo.bar", "src/example.py"),
  function("baz", "src/example.py").

**Assertion pseudocode:**
```
entities = _extract_entities(tree, "src/example.py")
names = {e.entity_name for e in entities}
ASSERT "example.py" in names  # file entity
ASSERT "Foo" in names         # class entity
ASSERT "Foo.bar" in names     # method entity
ASSERT "baz" in names         # function entity
```

### TS-95-14: Edge extraction from Python file

**Requirement:** 95-REQ-4.3
**Type:** unit
**Description:** Verify that tree-sitter extracts contains, imports, and
extends edges.

**Preconditions:**
- A Python file with: `from os.path import join` (imports edge),
  `class Sub(Base):` (extends edge), and a top-level function (contains edge).

**Input:**
- Parse file, call `_extract_edges(tree, rel_path, entities, module_map)`.

**Expected:**
- Contains edges from file to class, file to function, class to method.
- Imports edge from file to resolved import target.
- Extends edge from Sub to Base.

**Assertion pseudocode:**
```
edges = _extract_edges(tree, rel_path, entities, module_map)
ASSERT any(e.relationship == CONTAINS for e in edges)
ASSERT any(e.relationship == IMPORTS for e in edges)
ASSERT any(e.relationship == EXTENDS for e in edges)
```

### TS-95-15: Analysis result counts

**Requirement:** 95-REQ-4.4
**Type:** unit
**Description:** Verify that `analyze_codebase` returns correct counts.

**Preconditions:**
- Temp directory with 2 Python files containing 3 classes total.

**Input:**
- `analyze_codebase(repo_root, conn)`.

**Expected:**
- `AnalysisResult` with `entities_upserted > 0`, `edges_upserted > 0`,
  `entities_soft_deleted == 0` (first run).

**Assertion pseudocode:**
```
result = analyze_codebase(repo_root, conn)
ASSERT result.entities_upserted > 0
ASSERT result.edges_upserted >= 0
ASSERT result.entities_soft_deleted == 0
```

### TS-95-16: Soft-delete on re-analysis

**Requirement:** 95-REQ-4.5
**Type:** unit
**Description:** Verify that entities missing from re-analysis are
soft-deleted.

**Preconditions:**
- Initial analysis with file `src/old.py`. Then `src/old.py` is deleted.

**Input:**
- Re-run `analyze_codebase(repo_root, conn)`.

**Expected:**
- Entity for `old.py` has `deleted_at` set.
- `AnalysisResult.entities_soft_deleted >= 1`.

**Assertion pseudocode:**
```
result = analyze_codebase(repo_root, conn)
ASSERT result.entities_soft_deleted >= 1
old_entity = find_entities_by_path(conn, "src/old.py", include_deleted=True)
ASSERT old_entity[0].deleted_at is not None
```

### TS-95-17: Import resolution via module map

**Requirement:** 95-REQ-4.6
**Type:** unit
**Description:** Verify that dotted Python imports are resolved to
repo-relative file paths via the module map.

**Preconditions:**
- Module map: `{"agent_fox.knowledge.db": "agent_fox/knowledge/db.py"}`.
- Python file with `from agent_fox.knowledge.db import KnowledgeDB`.

**Input:**
- `_extract_edges(tree, rel_path, entities, module_map)`.

**Expected:**
- Imports edge from current file entity to `agent_fox/knowledge/db.py` file
  entity.

**Assertion pseudocode:**
```
edges = _extract_edges(tree, rel_path, entities, module_map)
import_edges = [e for e in edges if e.relationship == IMPORTS]
ASSERT any(target resolves to "agent_fox/knowledge/db.py")
```

### TS-95-18: Git diff path extraction

**Requirement:** 95-REQ-5.1
**Type:** unit
**Description:** Verify that `link_facts` extracts file paths from git diff
for each fact's commit_sha.

**Preconditions:**
- Mock `subprocess.run` to return "src/foo.py\nsrc/bar.py\n" for a given
  commit SHA.
- Entity graph populated with file entities for `src/foo.py` and `src/bar.py`.
- One fact with `commit_sha="abc123"`.

**Input:**
- `link_facts(conn, [fact], repo_root)`.

**Expected:**
- `_extract_paths_from_diff` called with "abc123".
- Returns `["src/foo.py", "src/bar.py"]`.

**Assertion pseudocode:**
```
mock_subprocess returns "src/foo.py\nsrc/bar.py\n"
result = link_facts(conn, [fact], repo_root)
ASSERT result.facts_processed == 1
```

### TS-95-19: Fact-entity link creation from diff

**Requirement:** 95-REQ-5.2
**Type:** unit
**Description:** Verify that fact-entity links are created for matched files.

**Preconditions:**
- Entity graph contains file entities for `src/foo.py` and `src/bar.py`.
- Mock git diff returns both paths.

**Input:**
- `link_facts(conn, [fact_with_sha], repo_root)`.

**Expected:**
- Two rows in `fact_entities` linking the fact to both file entities.

**Assertion pseudocode:**
```
link_facts(conn, [fact], repo_root)
count = conn.execute("SELECT COUNT(*) FROM fact_entities WHERE fact_id = ?", [fact.id]).fetchone()[0]
ASSERT count == 2
```

### TS-95-20: LinkResult counts

**Requirement:** 95-REQ-5.3
**Type:** unit
**Description:** Verify that `link_facts` returns correct counts.

**Preconditions:**
- Two facts: one with commit_sha, one without.
- Mock git diff returns one matching path.

**Input:**
- `link_facts(conn, [fact_with_sha, fact_without_sha], repo_root)`.

**Expected:**
- `LinkResult(facts_processed=1, links_created=1, facts_skipped=1)`.

**Assertion pseudocode:**
```
result = link_facts(conn, facts, repo_root)
ASSERT result.facts_processed == 1
ASSERT result.links_created >= 1
ASSERT result.facts_skipped == 1
```

### TS-95-21: Skip facts without commit_sha

**Requirement:** 95-REQ-5.4
**Type:** unit
**Description:** Verify that facts with null commit_sha are skipped.

**Preconditions:**
- One fact with `commit_sha=None`.

**Input:**
- `link_facts(conn, [fact_no_sha], repo_root)`.

**Expected:**
- `LinkResult(facts_processed=0, links_created=0, facts_skipped=1)`.

**Assertion pseudocode:**
```
result = link_facts(conn, [fact_no_sha], repo_root)
ASSERT result.facts_skipped == 1
ASSERT result.facts_processed == 0
```

### TS-95-22: Graph traversal within max_depth

**Requirement:** 95-REQ-6.1
**Type:** unit
**Description:** Verify BFS traversal returns neighbors within max_depth hops.

**Preconditions:**
- Linear graph: A -> B -> C -> D (contains edges).

**Input:**
- `traverse_neighbors(conn, [A.id], max_depth=2)`.

**Expected:**
- Returns A, B, C (depth 0, 1, 2). Does not return D (depth 3).

**Assertion pseudocode:**
```
result = traverse_neighbors(conn, [A.id], max_depth=2)
ids = {e.id for e in result}
ASSERT A.id in ids
ASSERT B.id in ids
ASSERT C.id in ids
ASSERT D.id not in ids
```

### TS-95-23: Traversal max_entities limit

**Requirement:** 95-REQ-6.2
**Type:** unit
**Description:** Verify traversal respects max_entities limit.

**Preconditions:**
- Star graph: A connected to B1..B10 (10 neighbors at depth 1).

**Input:**
- `traverse_neighbors(conn, [A.id], max_depth=1, max_entities=5)`.

**Expected:**
- Returns exactly 5 entities (A + 4 nearest, ordered by name).

**Assertion pseudocode:**
```
result = traverse_neighbors(conn, [A.id], max_depth=1, max_entities=5)
ASSERT len(result) == 5
```

### TS-95-24: Traversal relationship type filtering

**Requirement:** 95-REQ-6.3
**Type:** unit
**Description:** Verify traversal respects relationship_types filter.

**Preconditions:**
- Entity A has `contains` edge to B and `imports` edge to C.

**Input:**
- `traverse_neighbors(conn, [A.id], relationship_types=[IMPORTS])`.

**Expected:**
- Returns A and C. Does not include B.

**Assertion pseudocode:**
```
result = traverse_neighbors(conn, [A.id], relationship_types=[IMPORTS])
ids = {e.id for e in result}
ASSERT C.id in ids
ASSERT B.id not in ids
```

### TS-95-25: Fact retrieval for entities

**Requirement:** 95-REQ-6.4
**Type:** unit
**Description:** Verify that `get_facts_for_entities` returns non-superseded
facts linked to the given entities.

**Preconditions:**
- Entity E linked to fact F1 (active) and F2 (superseded).

**Input:**
- `get_facts_for_entities(conn, [E.id])`.

**Expected:**
- Returns [F1]. Does not return F2.

**Assertion pseudocode:**
```
facts = get_facts_for_entities(conn, [E.id])
ASSERT len(facts) == 1
ASSERT facts[0].id == F1.id
```

### TS-95-26: Convenience function find_related_facts

**Requirement:** 95-REQ-6.5
**Type:** unit
**Description:** Verify the convenience function resolves a path to entities,
traverses neighbors, and returns associated facts.

**Preconditions:**
- Entity graph with file entity for "src/foo.py" linked to fact F1.
- "src/foo.py" has a `contains` edge to class entity, which is linked to F2.

**Input:**
- `find_related_facts(conn, "src/foo.py", max_depth=1)`.

**Expected:**
- Returns [F1, F2] (deduplicated).

**Assertion pseudocode:**
```
facts = find_related_facts(conn, "src/foo.py", max_depth=1)
ids = {f.id for f in facts}
ASSERT F1.id in ids
ASSERT F2.id in ids
```

### TS-95-27: Soft-delete sets deleted_at

**Requirement:** 95-REQ-7.1
**Type:** unit
**Description:** Verify soft-delete sets the timestamp and preserves edges and
links.

**Preconditions:**
- Entity E with edges and fact-entity links.

**Input:**
- `soft_delete_missing(conn, set())` (empty found set, so E is missing).

**Expected:**
- E.deleted_at is set.
- Edges and fact-entity links for E still exist.

**Assertion pseudocode:**
```
soft_delete_missing(conn, set())
entity = query_entity_by_id(conn, E.id)
ASSERT entity.deleted_at is not None
edge_count = query_edge_count(conn, E.id)
ASSERT edge_count > 0
```

### TS-95-28: Garbage collection cascade

**Requirement:** 95-REQ-7.2
**Type:** unit
**Description:** Verify GC hard-deletes stale entities and cascades to edges
and links.

**Preconditions:**
- Entity E soft-deleted 30 days ago with edges and fact-entity links.

**Input:**
- `gc_stale_entities(conn, retention_days=7)`.

**Expected:**
- E removed from `entity_graph`.
- All edges referencing E removed from `entity_edges`.
- All links referencing E removed from `fact_entities`.
- Returns 1.

**Assertion pseudocode:**
```
count = gc_stale_entities(conn, retention_days=7)
ASSERT count == 1
ASSERT query_entity_by_id(conn, E.id) is None
ASSERT query_edge_count(conn, E.id) == 0
ASSERT query_link_count(conn, E.id) == 0
```

## Edge Case Tests

### TS-95-E1: Upsert existing active entity

**Requirement:** 95-REQ-1.E1
**Type:** unit
**Description:** Verify that upserting an entity with an existing natural key
returns the original ID.

**Preconditions:**
- Entity E already stored with natural key (FILE, "src/foo.py", "foo.py").

**Input:**
- Upsert a new Entity with the same natural key.

**Expected:**
- Returns E.id, not a new UUID.
- Entity count remains 1.

**Assertion pseudocode:**
```
id1 = upsert_entities(conn, [entity1])[0]
id2 = upsert_entities(conn, [entity2_same_key])[0]
ASSERT id1 == id2
```

### TS-95-E2: Upsert restores soft-deleted entity

**Requirement:** 95-REQ-1.E2
**Type:** unit
**Description:** Verify that upserting an entity matching a soft-deleted
natural key restores it.

**Preconditions:**
- Entity E stored and then soft-deleted (deleted_at set).

**Input:**
- Upsert an entity with E's natural key.

**Expected:**
- Returns E.id.
- E.deleted_at is now NULL.

**Assertion pseudocode:**
```
id_restored = upsert_entities(conn, [entity_same_key])[0]
ASSERT id_restored == E.id
entity = query_entity_by_id(conn, E.id)
ASSERT entity.deleted_at is None
```

### TS-95-E3: Self-referencing edge rejected

**Requirement:** 95-REQ-2.E1
**Type:** unit
**Description:** Verify that edges where source equals target are rejected.

**Preconditions:**
- Entity A exists.

**Input:**
- `upsert_edges(conn, [EntityEdge(A.id, A.id, CONTAINS)])`.

**Expected:**
- Raises ValueError.

**Assertion pseudocode:**
```
ASSERT RAISES ValueError: upsert_edges(conn, [self_edge])
```

### TS-95-E4: Fact-entity link to soft-deleted entity

**Requirement:** 95-REQ-3.E1
**Type:** unit
**Description:** Verify that links to soft-deleted entities are allowed.

**Preconditions:**
- Entity E soft-deleted. Fact F exists.

**Input:**
- `create_fact_entity_links(conn, F.id, [E.id])`.

**Expected:**
- Link created successfully.

**Assertion pseudocode:**
```
create_fact_entity_links(conn, F.id, [E.id])
count = query_link_count_for_fact(conn, F.id)
ASSERT count == 1
```

### TS-95-E5: Unparseable Python file

**Requirement:** 95-REQ-4.E1
**Type:** unit
**Description:** Verify that files with syntax errors are skipped with a
warning.

**Preconditions:**
- Temp directory with `good.py` (valid) and `bad.py` (syntax error).

**Input:**
- `analyze_codebase(repo_root, conn)`.

**Expected:**
- Entities extracted from `good.py`. `bad.py` skipped.
- Warning logged for `bad.py`.

**Assertion pseudocode:**
```
result = analyze_codebase(repo_root, conn)
ASSERT result.entities_upserted > 0  # from good.py
ASSERT "bad.py" in caplog.text
```

### TS-95-E6: Non-existent repo root

**Requirement:** 95-REQ-4.E2
**Type:** unit
**Description:** Verify ValueError on non-existent repo root.

**Preconditions:**
- Path "/nonexistent/path" does not exist.

**Input:**
- `analyze_codebase(Path("/nonexistent/path"), conn)`.

**Expected:**
- Raises ValueError.

**Assertion pseudocode:**
```
ASSERT RAISES ValueError: analyze_codebase(bad_path, conn)
```

### TS-95-E7: Empty repository (no Python files)

**Requirement:** 95-REQ-4.E3
**Type:** unit
**Description:** Verify zero-count result when no Python files exist.

**Preconditions:**
- Temp directory with no `.py` files.

**Input:**
- `analyze_codebase(repo_root, conn)`.

**Expected:**
- `AnalysisResult(0, 0, 0)`.

**Assertion pseudocode:**
```
result = analyze_codebase(repo_root, conn)
ASSERT result.entities_upserted == 0
ASSERT result.edges_upserted == 0
```

### TS-95-E8: Missing commit_sha in git repo

**Requirement:** 95-REQ-5.E1
**Type:** unit
**Description:** Verify that a missing commit_sha is skipped gracefully.

**Preconditions:**
- Mock `subprocess.run` to return non-zero exit code for "deadbeef".

**Input:**
- Fact with `commit_sha="deadbeef"`.
- `link_facts(conn, [fact], repo_root)`.

**Expected:**
- Fact skipped. Warning logged.
- `LinkResult(facts_processed=0, links_created=0, facts_skipped=1)`.

**Assertion pseudocode:**
```
result = link_facts(conn, [fact_with_bad_sha], repo_root)
ASSERT result.facts_skipped == 1
ASSERT "deadbeef" in caplog.text
```

### TS-95-E9: Git diff paths with no matching entities

**Requirement:** 95-REQ-5.E2
**Type:** unit
**Description:** Verify that unmatched diff paths are skipped silently.

**Preconditions:**
- Mock git diff returns "src/unknown.py". No entity exists for that path.

**Input:**
- `link_facts(conn, [fact], repo_root)`.

**Expected:**
- No links created for unmatched paths.
- `LinkResult(facts_processed=1, links_created=0, facts_skipped=0)`.

**Assertion pseudocode:**
```
result = link_facts(conn, [fact], repo_root)
ASSERT result.links_created == 0
```

### TS-95-E10: Traversal with no matching entities

**Requirement:** 95-REQ-6.E1
**Type:** unit
**Description:** Verify empty result when no entities match the starting
path.

**Preconditions:**
- Entity graph exists but no entity for "nonexistent.py".

**Input:**
- `find_related_facts(conn, "nonexistent.py")`.

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
facts = find_related_facts(conn, "nonexistent.py")
ASSERT facts == []
```

### TS-95-E11: Traversal excludes soft-deleted entities

**Requirement:** 95-REQ-6.E2
**Type:** unit
**Description:** Verify that soft-deleted entities are excluded from
traversal by default.

**Preconditions:**
- Entity A (active) with `contains` edge to Entity B (soft-deleted).

**Input:**
- `traverse_neighbors(conn, [A.id], max_depth=1)`.

**Expected:**
- Returns [A]. Does not include B.

**Assertion pseudocode:**
```
result = traverse_neighbors(conn, [A.id], max_depth=1)
ASSERT B.id not in {e.id for e in result}
```

### TS-95-E12: GC with invalid retention_days

**Requirement:** 95-REQ-7.E1
**Type:** unit
**Description:** Verify ValueError on zero or negative retention_days.

**Preconditions:**
- None.

**Input:**
- `gc_stale_entities(conn, retention_days=0)`.
- `gc_stale_entities(conn, retention_days=-5)`.

**Expected:**
- Both raise ValueError.

**Assertion pseudocode:**
```
ASSERT RAISES ValueError: gc_stale_entities(conn, 0)
ASSERT RAISES ValueError: gc_stale_entities(conn, -5)
```

### TS-95-E13: GC with no eligible entities

**Requirement:** 95-REQ-7.E2
**Type:** unit
**Description:** Verify zero return when no entities are eligible.

**Preconditions:**
- All entities are active (no soft-deleted entities).

**Input:**
- `gc_stale_entities(conn, retention_days=7)`.

**Expected:**
- Returns 0. No rows deleted.

**Assertion pseudocode:**
```
count = gc_stale_entities(conn, retention_days=7)
ASSERT count == 0
```

## Property Test Cases

### TS-95-P1: Path normalization invariant

**Property:** Property 1 from design.md
**Validates:** 95-REQ-1.3
**Type:** property
**Description:** For any valid file path string, normalized output has no
leading slash, no `.` or `..` components, and no trailing slash.

**For any:** `path` generated as a combination of path components (letters,
digits, underscores, slashes, dots).
**Invariant:** `normalize_path(path)` has no leading `/`, no component equal
to `.` or `..`, no trailing `/`.

**Assertion pseudocode:**
```
FOR ANY path IN st.text(alphabet="abcdefghijklmnop_./ ", min_size=1):
    result = normalize_path(path)
    ASSERT not result.startswith("/")
    ASSERT ".." not in result.split("/")
    ASSERT not result.endswith("/")
```

### TS-95-P2: Upsert idempotency

**Property:** Property 2 from design.md
**Validates:** 95-REQ-1.E1, 95-REQ-2.4, 95-REQ-3.3
**Type:** property
**Description:** Upserting the same set of entities/edges twice produces
identical database state.

**For any:** List of 1-10 entities with random types, names, and paths.
**Invariant:** After upserting the list twice, the entity count, edge count,
and specific IDs are identical.

**Assertion pseudocode:**
```
FOR ANY entities IN list_of_entities(min=1, max=10):
    upsert_entities(conn, entities)
    state1 = snapshot(conn)
    upsert_entities(conn, entities)
    state2 = snapshot(conn)
    ASSERT state1 == state2
```

### TS-95-P3: Traversal bound

**Property:** Property 3 from design.md
**Validates:** 95-REQ-6.1, 95-REQ-6.2
**Type:** property
**Description:** Traversal results never exceed max_entities and max_depth.

**For any:** Graph of 2-20 entities with random edges, max_depth in [1, 5],
max_entities in [1, 20].
**Invariant:** `len(result) <= max_entities` and all returned entities have
depth <= max_depth.

**Assertion pseudocode:**
```
FOR ANY (graph, start_id, max_depth, max_entities) IN graph_strategy:
    result = traverse_neighbors(conn, [start_id], max_depth, max_entities)
    ASSERT len(result) <= max_entities
    FOR EACH entity IN result:
        ASSERT entity.depth <= max_depth  (if depth is tracked)
```

### TS-95-P4: Soft-delete exclusion

**Property:** Property 4 from design.md
**Validates:** 95-REQ-6.E2, 95-REQ-7.1
**Type:** property
**Description:** Soft-deleted entities never appear in default traversal
results.

**For any:** Graph with a mix of active and soft-deleted entities.
**Invariant:** `traverse_neighbors(conn, ids, include_deleted=False)` returns
no entity whose `deleted_at` is set.

**Assertion pseudocode:**
```
FOR ANY graph WITH some deleted entities:
    result = traverse_neighbors(conn, [start_id], include_deleted=False)
    FOR EACH entity IN result:
        ASSERT entity.deleted_at is None
```

### TS-95-P5: Referential integrity

**Property:** Property 5 from design.md
**Validates:** 95-REQ-2.3, 95-REQ-3.2
**Type:** property
**Description:** No edge or fact-entity link references a non-existent entity
or fact.

**For any:** Database state after a series of upsert operations.
**Invariant:** Every `source_id` and `target_id` in `entity_edges` exists in
`entity_graph`. Every `entity_id` in `fact_entities` exists in `entity_graph`.
Every `fact_id` in `fact_entities` exists in `memory_facts`.

**Assertion pseudocode:**
```
FOR ANY sequence of operations:
    edges = query_all_edges(conn)
    FOR EACH edge IN edges:
        ASSERT entity_exists(conn, edge.source_id)
        ASSERT entity_exists(conn, edge.target_id)
    links = query_all_links(conn)
    FOR EACH link IN links:
        ASSERT entity_exists(conn, link.entity_id)
        ASSERT fact_exists(conn, link.fact_id)
```

### TS-95-P6: GC cascade completeness

**Property:** Property 6 from design.md
**Validates:** 95-REQ-7.2
**Type:** property
**Description:** After GC, no orphaned edges or links reference deleted
entities.

**For any:** Graph with 1-5 soft-deleted entities and associated edges/links.
**Invariant:** After `gc_stale_entities`, no row in `entity_edges` or
`fact_entities` references any of the hard-deleted entity IDs.

**Assertion pseudocode:**
```
FOR ANY (deleted_ids, retention_days):
    gc_stale_entities(conn, retention_days)
    FOR EACH deleted_id IN deleted_ids:
        ASSERT edge_count_referencing(conn, deleted_id) == 0
        ASSERT link_count_referencing(conn, deleted_id) == 0
```

## Integration Smoke Tests

### TS-95-SMOKE-1: Full codebase analysis end-to-end

**Execution Path:** Path 1 from design.md
**Description:** Verify that analyzing a small Python codebase populates
the entity graph with correct entities and edges.

**Setup:**
- Temp directory with a Python package:
  - `pkg/__init__.py` (empty)
  - `pkg/models.py` (class `User` with method `save`)
  - `pkg/service.py` (function `create_user`, imports `User` from
    `pkg.models`, class `Service(Base)`)
- Real DuckDB in-memory connection with migrations applied.
- Real tree-sitter parser.

**Trigger:** `analyze_codebase(repo_root, conn)`

**Expected side effects:**
- `entity_graph` contains entities: module("pkg"), file("__init__.py"),
  file("models.py"), file("service.py"), class("User"), function("User.save"),
  function("create_user"), class("Service").
- `entity_edges` contains: module contains files, files contain classes/
  functions, `service.py` imports `models.py`, `Service` extends `Base`.
- `AnalysisResult` has non-zero counts.

**Must NOT satisfy with:** Mocked tree-sitter parser, mocked entity store.

**Assertion pseudocode:**
```
result = analyze_codebase(repo_root, conn)
ASSERT result.entities_upserted >= 6
ASSERT result.edges_upserted >= 4
entities = conn.execute("SELECT * FROM entity_graph").fetchall()
names = {e[2] for e in entities}  # entity_name column
ASSERT "User" in names
ASSERT "create_user" in names
```

### TS-95-SMOKE-2: Fact-entity linking end-to-end

**Execution Path:** Path 2 from design.md
**Description:** Verify that facts are linked to entities via git diff.

**Setup:**
- Real DuckDB in-memory connection with migrations and entity graph populated
  (file entities for "src/foo.py" and "src/bar.py").
- One fact inserted into `memory_facts` with `commit_sha="abc123"`.
- Mock `subprocess.run` to return "src/foo.py\nsrc/bar.py\n" for the diff
  command.

**Trigger:** `link_facts(conn, [fact], repo_root)`

**Expected side effects:**
- `fact_entities` table has 2 rows linking the fact to both file entities.
- `LinkResult.links_created == 2`.

**Must NOT satisfy with:** Mocked entity store, mocked DuckDB connection.

**Assertion pseudocode:**
```
result = link_facts(conn, [fact], repo_root)
ASSERT result.links_created == 2
rows = conn.execute("SELECT * FROM fact_entities WHERE fact_id = ?", [fact.id]).fetchall()
ASSERT len(rows) == 2
```

### TS-95-SMOKE-3: Graph query for related facts end-to-end

**Execution Path:** Path 3 from design.md
**Description:** Verify that traversing from a file path returns associated
facts from neighboring entities.

**Setup:**
- Real DuckDB in-memory connection with:
  - File entity "src/foo.py" linked to fact F1.
  - Class entity "Foo" contained by "src/foo.py", linked to fact F2.
  - File entity "src/bar.py" importing "src/foo.py", linked to fact F3.

**Trigger:** `find_related_facts(conn, "src/foo.py", max_depth=1)`

**Expected side effects:**
- Returns facts [F1, F2, F3] (all reachable within depth 1).

**Must NOT satisfy with:** Mocked traversal, mocked entity store.

**Assertion pseudocode:**
```
facts = find_related_facts(conn, "src/foo.py", max_depth=1)
fact_ids = {f.id for f in facts}
ASSERT F1.id in fact_ids
ASSERT F2.id in fact_ids
ASSERT F3.id in fact_ids
```

### TS-95-SMOKE-4: Garbage collection end-to-end

**Execution Path:** Path 4 from design.md
**Description:** Verify GC removes stale entities and cascades to edges and
links.

**Setup:**
- Real DuckDB in-memory connection with:
  - Entity E1 soft-deleted 30 days ago, with one edge and one fact-entity link.
  - Entity E2 active (not soft-deleted).

**Trigger:** `gc_stale_entities(conn, retention_days=7)`

**Expected side effects:**
- E1 removed from `entity_graph`.
- E1's edge removed from `entity_edges`.
- E1's link removed from `fact_entities`.
- E2 untouched.
- Returns 1.

**Must NOT satisfy with:** Mocked DuckDB connection.

**Assertion pseudocode:**
```
count = gc_stale_entities(conn, retention_days=7)
ASSERT count == 1
ASSERT conn.execute("SELECT * FROM entity_graph WHERE id = ?", [E1.id]).fetchone() is None
ASSERT conn.execute("SELECT * FROM entity_graph WHERE id = ?", [E2.id]).fetchone() is not None
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 95-REQ-1.1 | TS-95-1 | unit |
| 95-REQ-1.2 | TS-95-2 | unit |
| 95-REQ-1.3 | TS-95-3 | unit |
| 95-REQ-1.4 | TS-95-4 | unit |
| 95-REQ-1.E1 | TS-95-E1 | unit |
| 95-REQ-1.E2 | TS-95-E2 | unit |
| 95-REQ-2.1 | TS-95-5 | unit |
| 95-REQ-2.2 | TS-95-6 | unit |
| 95-REQ-2.3 | TS-95-7 | unit |
| 95-REQ-2.4 | TS-95-8 | unit |
| 95-REQ-2.E1 | TS-95-E3 | unit |
| 95-REQ-3.1 | TS-95-9 | unit |
| 95-REQ-3.2 | TS-95-10 | unit |
| 95-REQ-3.3 | TS-95-11 | unit |
| 95-REQ-3.E1 | TS-95-E4 | unit |
| 95-REQ-4.1 | TS-95-12 | unit |
| 95-REQ-4.2 | TS-95-13 | unit |
| 95-REQ-4.3 | TS-95-14 | unit |
| 95-REQ-4.4 | TS-95-15 | unit |
| 95-REQ-4.5 | TS-95-16 | unit |
| 95-REQ-4.6 | TS-95-17 | unit |
| 95-REQ-4.E1 | TS-95-E5 | unit |
| 95-REQ-4.E2 | TS-95-E6 | unit |
| 95-REQ-4.E3 | TS-95-E7 | unit |
| 95-REQ-5.1 | TS-95-18 | unit |
| 95-REQ-5.2 | TS-95-19 | unit |
| 95-REQ-5.3 | TS-95-20 | unit |
| 95-REQ-5.4 | TS-95-21 | unit |
| 95-REQ-5.E1 | TS-95-E8 | unit |
| 95-REQ-5.E2 | TS-95-E9 | unit |
| 95-REQ-6.1 | TS-95-22 | unit |
| 95-REQ-6.2 | TS-95-23 | unit |
| 95-REQ-6.3 | TS-95-24 | unit |
| 95-REQ-6.4 | TS-95-25 | unit |
| 95-REQ-6.5 | TS-95-26 | unit |
| 95-REQ-6.E1 | TS-95-E10 | unit |
| 95-REQ-6.E2 | TS-95-E11 | unit |
| 95-REQ-7.1 | TS-95-27 | unit |
| 95-REQ-7.2 | TS-95-28 | unit |
| 95-REQ-7.E1 | TS-95-E12 | unit |
| 95-REQ-7.E2 | TS-95-E13 | unit |
| Property 1 | TS-95-P1 | property |
| Property 2 | TS-95-P2 | property |
| Property 3 | TS-95-P3 | property |
| Property 4 | TS-95-P4 | property |
| Property 5 | TS-95-P5 | property |
| Property 6 | TS-95-P6 | property |
| Path 1 | TS-95-SMOKE-1 | integration |
| Path 2 | TS-95-SMOKE-2 | integration |
| Path 3 | TS-95-SMOKE-3 | integration |
| Path 4 | TS-95-SMOKE-4 | integration |
