# Entity Graph

## Problem

The agent-fox knowledge system stores facts with spec-name, keywords,
embeddings, and causal links -- but has no first-class representation of the
codebase's structure. Modules, files, classes, functions, and their dependency
relationships are not modeled as queryable graph nodes.

When a coding session is about to modify `agent_fox/knowledge/search.py`, the
system cannot traverse a structural graph to find all facts about that module,
its dependencies (`embeddings.py`, `db.py`), the modules that depend on it
(`lifecycle.py`, `fact_cache.py`), and the tests that cover it. The existing
vector search (spec 94) finds semantically similar text, but structural
retrieval based on code topology is fundamentally different and complementary.

## Solution

Add an entity graph subsystem to the knowledge layer:

1. **Three new DuckDB tables:**
   - `entity_graph` -- nodes representing codebase entities (files, modules,
     classes, functions) with UUID identity, typed classification, repo-relative
     paths, and soft-delete support.
   - `entity_edges` -- directed typed edges between entities (imports, extends,
     contains).
   - `fact_entities` -- junction table linking existing facts to the entities
     they reference.

2. **Population via tree-sitter static analysis:**
   - Parse source files using tree-sitter to extract entity nodes (modules,
     classes, functions) and relationship edges (imports, inheritance,
     containment) for all supported languages.
   - Produce a complete entity graph for the codebase in a single analysis pass.
   - Support incremental updates: re-analyze changed files, soft-delete removed
     entities, add new ones.

3. **Fact-entity linking via git diff:**
   - For facts with a `commit_sha`, run `git diff` to extract affected file
     paths.
   - Create `fact_entities` links between the fact and the file entities it
     touches.
   - All paths normalized to repo-relative format.

4. **Graph traversal queries:**
   - Find entities by path or name.
   - Walk neighbors up to a configurable `max_depth` with optional
     relationship-type filtering.
   - Retrieve all facts associated with a set of entities (via junction table).

## Design Decisions

1. **Entity identity: UUID.** Entities use UUID primary keys, not deterministic
   path-based IDs. This allows the same logical path to appear as different
   entities over time (after deletion and re-creation) and simplifies the schema.

2. **Three tables, not two.** The junction table `fact_entities` is separate
   from `entity_edges` because fact-entity links have different semantics
   (provenance) than entity-entity relationships (structure).

3. **Complementary to spec 94.** The entity graph and cross-spec vector
   retrieval are independent retrieval channels. In a future spec, both will
   feed into the context builder as parallel signals, with results merged and
   deduplicated before causal enhancement.

4. **Standalone, not wired.** This spec builds the entity graph infrastructure
   as a callable library. It does NOT wire into the knowledge harvest pipeline
   or context builder. Integration will happen in a future "knowledge
   consolidation" agent spec.

5. **Entity staleness: soft-delete + GC.** Entities are never hard-deleted
   during analysis. When a file/class/function disappears from the codebase, its
   `deleted_at` timestamp is set. A separate garbage collection function removes
   soft-deleted entities (and their edges/fact-links) after a configurable
   retention period.

6. **Tree-sitter (richer approach).** This spec implements full static analysis
   using tree-sitter, not just lightweight regex-based path extraction.
   Tree-sitter provides module-level, class-level, and function-level entity
   extraction with accurate import/inheritance resolution.

7. **Causal graph interaction.** Entity-fact links and causal links are
   independent retrieval channels. When eventually wired (future spec), the
   context builder will: (a) retrieve structurally-related facts via entity
   graph, (b) retrieve cross-spec facts via vector search, (c) merge all
   channels, (d) enhance the merged set with causal traversal. Entity graph
   retrieval happens before causal enhancement.

8. **Path normalization.** All entity paths are normalized to repo-relative
   format (e.g., `agent_fox/knowledge/db.py`, not
   `/Users/x/project/agent_fox/knowledge/db.py`). Paths outside the repository
   should not occur; if encountered, they are silently skipped.

9. **Graph traversal bounds.** Neighbor walks use a `max_depth` parameter
   (default 2) and `max_entities` limit (default 50) to prevent unbounded
   expansion on large codebases.

10. **Git diff availability.** The fact-linking function assumes the commit
    exists in the local repo. It must be called before local branches are
    deleted. If the commit is unavailable, the function logs a warning and skips
    that fact (graceful degradation).

11. **Transcript path extraction.** File path extraction from session
    transcripts uses regex heuristics. Accuracy may vary; false positives are
    acceptable (extra links) but false negatives mean missed associations. This
    is a best-effort enrichment, not a guarantee.

12. **Multi-language static analysis.** Tree-sitter analysis supports all
    major programming languages via per-language analyzer modules. Each
    language has its own tree-sitter grammar, entity extraction rules, and
    import resolution strategy. Spec 102 provides the detailed per-language
    implementation plan. All languages are treated equally -- there is no
    "primary" or "fallback" language.

13. **Qualified names for methods.** Top-level functions use their bare name
    (e.g., `embed_text`). Methods use a dot-qualified name (e.g.,
    `KnowledgeDB.connect`). This ensures uniqueness within a file without
    requiring a parent entity reference.
