# Requirements Document

## Introduction

The entity graph extends the agent-fox knowledge system with a structural
representation of the codebase. Codebase entities (files, modules, classes,
functions) are stored as typed graph nodes in DuckDB, connected by directed
edges representing structural relationships (imports, inheritance,
containment). A junction table links existing memory facts to the entities they
reference, enabling retrieval of knowledge based on code topology rather than
semantic similarity alone.

This spec delivers the entity graph as a standalone library. Wiring into the
knowledge harvest pipeline and session context builder is deferred to a future
"knowledge consolidation" spec.

## Glossary

- **Entity** -- A structural element of the codebase: a file, module, class, or
  function. Represented as a node in the entity graph.
- **Entity type** -- Classification of an entity: `file`, `module`, `class`, or
  `function`.
- **Edge** -- A directed relationship between two entities: `contains`,
  `imports`, or `extends`.
- **Fact** -- An existing knowledge record in `memory_facts` (see spec 05).
- **Fact-entity link** -- A row in the `fact_entities` junction table
  associating a fact with an entity it references.
- **Natural key** -- The tuple `(entity_type, entity_path, entity_name)` that
  uniquely identifies an entity independent of its UUID.
- **Repo-relative path** -- A file path relative to the repository root, with
  no leading slash and no `.` or `..` components (e.g.,
  `agent_fox/knowledge/db.py`).
- **Soft-delete** -- Marking an entity as deleted by setting its `deleted_at`
  timestamp, without removing the row from the database.
- **Garbage collection (GC)** -- Hard-deleting soft-deleted entities whose
  `deleted_at` exceeds a retention period, cascading to edges and fact-entity
  links.
- **Qualified name** -- For methods, the dot-separated form
  `ClassName.method_name`. Top-level functions use the bare name.
- **Module map** -- A language-specific mapping from import identifiers to
  repo-relative file paths, built by scanning the directory tree. The format
  varies by language (e.g., dotted paths for Python, package directories for
  Go, relative paths for TypeScript).
- **Traversal** -- A breadth-first walk of the entity graph from one or more
  starting entities, following edges in both directions.
- **Tree-sitter** -- An incremental parsing library used for static analysis of
  source files across all supported languages.
- **Analysis result** -- The return value of a codebase analysis operation,
  containing counts of entities upserted, edges upserted, and entities
  soft-deleted.

## Requirements

### Requirement 1: Entity Node Storage

**User Story:** As a knowledge system, I want to store codebase entities as
typed graph nodes so that structural code topology can be queried alongside
semantic knowledge.

#### Acceptance Criteria

1. [95-REQ-1.1] THE system SHALL store entities in a DuckDB table
   `entity_graph` with columns: `id` (UUID primary key), `entity_type`
   (VARCHAR NOT NULL), `entity_name` (VARCHAR NOT NULL), `entity_path`
   (VARCHAR NOT NULL), `created_at` (TIMESTAMP NOT NULL), `deleted_at`
   (TIMESTAMP, nullable).

2. [95-REQ-1.2] WHEN an entity is stored, THE system SHALL assign it a UUID v4
   identifier.

3. [95-REQ-1.3] WHEN an entity is stored, THE system SHALL normalize its
   `entity_path` to a repo-relative format with no leading slash, no `.` or
   `..` components, and no trailing slash.

4. [95-REQ-1.4] THE system SHALL support four entity types: `file`, `module`,
   `class`, `function`.

#### Edge Cases

1. [95-REQ-1.E1] IF an entity with the same natural key (`entity_type`,
   `entity_path`, `entity_name`) already exists and is not soft-deleted, THEN
   THE system SHALL return the existing entity's ID without creating a
   duplicate.

2. [95-REQ-1.E2] IF an entity with the same natural key exists but is
   soft-deleted, THEN THE system SHALL restore it by clearing `deleted_at` AND
   return its ID.

### Requirement 2: Entity Edge Storage

**User Story:** As a knowledge system, I want to store directed typed edges
between entities so that structural relationships (imports, inheritance,
containment) can be traversed.

#### Acceptance Criteria

1. [95-REQ-2.1] THE system SHALL store edges in a DuckDB table `entity_edges`
   with columns: `source_id` (UUID NOT NULL), `target_id` (UUID NOT NULL),
   `relationship` (VARCHAR NOT NULL), with a composite primary key on all three
   columns.

2. [95-REQ-2.2] THE system SHALL support three relationship types: `contains`,
   `imports`, `extends`.

3. [95-REQ-2.3] WHEN an edge is stored, THE system SHALL verify that both
   `source_id` and `target_id` exist in `entity_graph` AND raise an error if
   either is missing.

4. [95-REQ-2.4] IF an edge with the same (`source_id`, `target_id`,
   `relationship`) already exists, THEN THE system SHALL silently ignore the
   duplicate.

#### Edge Cases

1. [95-REQ-2.E1] IF `source_id` equals `target_id`, THEN THE system SHALL
   reject the edge with a ValueError.

### Requirement 3: Fact-Entity Junction

**User Story:** As a knowledge system, I want to link facts to the codebase
entities they reference so that facts can be retrieved based on code topology.

#### Acceptance Criteria

1. [95-REQ-3.1] THE system SHALL store fact-entity links in a DuckDB table
   `fact_entities` with columns: `fact_id` (UUID NOT NULL), `entity_id` (UUID
   NOT NULL), with a composite primary key on both columns.

2. [95-REQ-3.2] WHEN a link is created, THE system SHALL verify that `fact_id`
   exists in `memory_facts` AND `entity_id` exists in `entity_graph` AND raise
   an error if either is missing.

3. [95-REQ-3.3] IF a link with the same (`fact_id`, `entity_id`) already
   exists, THEN THE system SHALL silently ignore the duplicate.

#### Edge Cases

1. [95-REQ-3.E1] IF the referenced entity is soft-deleted (`deleted_at IS NOT
   NULL`), THEN THE system SHALL still allow link creation (soft-deleted
   entities retain their associations).

### Requirement 4: Tree-Sitter Static Analysis

**User Story:** As a developer, I want to analyze a codebase using tree-sitter
to automatically populate the entity graph with structural information for all
supported languages.

#### Acceptance Criteria

1. [95-REQ-4.1] WHEN the analysis function is invoked with a repository root
   path, THE system SHALL scan all source files matching extensions registered
   in the language analyzer registry, excluding files matched by `.gitignore`.

2. [95-REQ-4.2] WHEN a source file is parsed, THE system SHALL extract entities
   of type `file` (one per source file), `module` (language-specific: Python
   packages, Go packages, Rust modules, Java packages, C++ namespaces, Ruby
   modules), `class` (language-specific: classes, structs, interfaces, enums,
   traits), and `function` (one per function or method definition, using
   qualified names for methods) AND upsert them into `entity_graph`.

3. [95-REQ-4.3] WHEN a source file is parsed, THE system SHALL extract
   `contains` edges (module to file, file to class, file to function, class to
   method), `imports` edges (file to imported file or module), and `extends`
   edges (subclass to superclass, where the language supports inheritance) AND
   upsert them into `entity_edges`.

4. [95-REQ-4.4] WHEN the analysis function completes, THE system SHALL return
   an `AnalysisResult` containing counts of entities upserted, edges upserted,
   and entities soft-deleted to the caller.

5. [95-REQ-4.5] WHEN an entity that exists in `entity_graph` is not found
   during a re-analysis of the same repository root, THE system SHALL set its
   `deleted_at` timestamp rather than hard-deleting it.

6. [95-REQ-4.6] WHEN resolving an import statement to a target entity, THE
   system SHALL use a language-specific module map to resolve import
   identifiers to repo-relative file paths AND skip unresolvable imports with
   a logged warning.

#### Edge Cases

1. [95-REQ-4.E1] IF a source file cannot be parsed by tree-sitter (e.g.,
   syntax error), THEN THE system SHALL log a warning, skip that file, and
   continue with the remaining files.

2. [95-REQ-4.E2] IF the repository root path does not exist or is not a
   directory, THEN THE system SHALL raise a ValueError.

3. [95-REQ-4.E3] IF no source files are found under the repository root for
   any registered language, THEN THE system SHALL return an `AnalysisResult`
   with all counts set to zero.

### Requirement 5: Fact-Entity Linking via Git Diff

**User Story:** As a knowledge system, I want to automatically link facts to
the files they affected using the fact's `commit_sha` to determine which files
were changed.

#### Acceptance Criteria

1. [95-REQ-5.1] WHEN the linking function is invoked with a list of facts and
   a repository root, THE system SHALL, for each fact with a non-null
   `commit_sha`, run `git diff --name-only` to extract the list of affected
   file paths AND return those paths as repo-relative strings to the caller.

2. [95-REQ-5.2] WHEN affected file paths are extracted for a fact, THE system
   SHALL look up corresponding file entities in `entity_graph` AND create
   `fact_entities` links for each match.

3. [95-REQ-5.3] WHEN the linking function completes, THE system SHALL return a
   `LinkResult` containing counts of facts processed, links created, and facts
   skipped to the caller.

4. [95-REQ-5.4] IF a fact has no `commit_sha` (null), THEN THE system SHALL
   skip it and increment the skipped count.

#### Edge Cases

1. [95-REQ-5.E1] IF the `commit_sha` does not exist in the local repository,
   THEN THE system SHALL log a warning, skip that fact, and continue with the
   remaining facts.

2. [95-REQ-5.E2] IF `git diff` returns file paths that do not correspond to
   any entity in `entity_graph`, THEN THE system SHALL skip those paths without
   creating links.

### Requirement 6: Graph Traversal and Fact Retrieval

**User Story:** As a knowledge consumer, I want to traverse the entity graph
from a file path to find structurally related facts so that I can retrieve
knowledge based on code topology.

#### Acceptance Criteria

1. [95-REQ-6.1] WHEN a traversal is requested for one or more entity IDs, THE
   system SHALL return all neighboring entities reachable within `max_depth`
   hops (default 2), following edges in both directions.

2. [95-REQ-6.2] THE system SHALL enforce a `max_entities` limit (default 50)
   on traversal results, returning the closest entities first (ordered by depth
   ascending, then by entity name for deterministic ordering within a depth).

3. [95-REQ-6.3] WHEN a traversal specifies `relationship_types`, THE system
   SHALL only follow edges whose relationship is in the specified set.

4. [95-REQ-6.4] WHEN facts are requested for a set of entity IDs, THE system
   SHALL return all facts linked via `fact_entities` whose `superseded_by` is
   NULL in `memory_facts` AND return them as a deduplicated list to the caller.

5. [95-REQ-6.5] WHEN a convenience function is called with a file path, THE
   system SHALL resolve the path to entities, traverse neighbors, and return
   associated facts AND return the `list[Fact]` to the caller for use in
   context assembly.

#### Edge Cases

1. [95-REQ-6.E1] IF no entities match the starting path or IDs, THEN THE
   system SHALL return an empty list.

2. [95-REQ-6.E2] WHILE traversing, THE system SHALL exclude soft-deleted
   entities (where `deleted_at IS NOT NULL`) unless `include_deleted=True` is
   specified.

### Requirement 7: Soft-Delete and Garbage Collection

**User Story:** As a system maintainer, I want stale entities to be
soft-deleted and eventually garbage-collected so that the entity graph stays
accurate without losing historical associations prematurely.

#### Acceptance Criteria

1. [95-REQ-7.1] WHEN an entity is soft-deleted, THE system SHALL set its
   `deleted_at` to the current timestamp AND preserve all existing edges and
   fact-entity links.

2. [95-REQ-7.2] WHEN the garbage collection function is invoked with a
   `retention_days` parameter, THE system SHALL hard-delete all entities whose
   `deleted_at` is older than `retention_days` days ago AND cascade-delete
   their edges from `entity_edges` AND cascade-delete their links from
   `fact_entities` AND return the count of entities removed to the caller.

#### Edge Cases

1. [95-REQ-7.E1] IF `retention_days` is zero or negative, THEN THE system
   SHALL raise a ValueError.

2. [95-REQ-7.E2] IF no entities are eligible for garbage collection, THEN THE
   system SHALL return zero without modifying the database.
