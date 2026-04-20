# PRD: DuckDB Knowledge Store

**Source:** `.specs/prd.md` -- REQ-140 through REQ-146.
`.specs/v2.md` -- Section 5 (DuckDB Knowledge Store), schema sketch,
audit log integration, SessionSink abstraction, operational notes.

## Overview

Establish the DuckDB-backed persistence layer for agent-fox v2. This spec
creates the embedded database infrastructure, schema management, and the
composable sink abstraction that decouples recording from the session runner.
Session outcomes are recorded unconditionally; tool signals and raw audit
content are recorded only when debug mode is enabled.

This is the foundation for the Fox Ball (spec 12) and Time Vision (spec 13).
Without this spec, there is no structured, queryable knowledge store.

## Problem Statement

agent-fox v1 persists session data exclusively as JSONL files. This format is
append-only, human-readable, and adequate for sequential replay, but it cannot
support the cross-session analytical queries, vector search, and causal graph
traversal that v2 requires. A structured database is needed alongside JSONL
(not replacing it) to enable these capabilities.

## Goals

- Provide a DuckDB database at `.agent-fox/knowledge.duckdb` with a versioned
  schema covering session outcomes, memory facts, embeddings, causal links,
  tool calls, and tool errors
- Implement forward-only schema migrations so the database evolves safely
  across releases
- Define a `SessionSink` protocol (composable sink abstraction) that decouples
  recording logic from the session runner
- Implement a DuckDB sink that writes session outcomes unconditionally and
  tool signals when debug mode is active
- Implement a JSONL sink that preserves the existing v1 raw audit behavior
  (debug-only)
- Degrade gracefully when the database is corrupted, locked, or inaccessible --
  never block coding sessions

## Non-Goals

- Embedding generation -- that is spec 12 (Fox Ball)
- Vector search queries (HNSW index creation, `ask` command) -- spec 12
- Causal graph traversal and temporal queries -- spec 13 (Time Vision)
- Migrating existing v1 JSONL data into DuckDB -- future `--rebuild-knowledge`
- Replacing JSONL as the source of truth for fact content
- Real-time streaming from sinks -- batch append only

## Key Decisions

- **DuckDB over SQLite + sqlite-vec** -- DuckDB covers both columnar analytics
  (Time Vision) and vector search (Fox Ball via VSS extension) in a single
  embedded file, eliminating a second database dependency.
- **SessionSink as Protocol, not base class** -- Protocols are structurally
  typed, composable, and testable without inheritance coupling. Sinks can be
  mixed and matched without an abstract base hierarchy.
- **Three-layer recording model** -- Session outcomes always go to DuckDB;
  tool signals go to DuckDB only in debug mode; raw content goes to JSONL only
  in debug mode. This splits the v1 all-or-nothing `--debug` gate.
- **Forward-only migrations** -- Rollback adds complexity with minimal value
  for an embedded, single-user database. If a migration fails, the user
  re-initializes from JSONL (future `--rebuild-knowledge`).
- **VSS extension installed on first use** -- `INSTALL vss; LOAD vss;` on
  initial schema creation; subsequent connections only `LOAD vss;`. No
  network dependency after the first run.
- **WAL for crash safety** -- DuckDB's write-ahead log provides crash safety
  for append-only writes without explicit transaction management.
- **Parallel session writes serialized through existing state lock** -- DuckDB
  supports one writer at a time; parallel session outcome writes are
  serialized through the orchestrator's existing state lock, matching the
  post-harvest serial design.

## Dependencies

| Dependency | Spec | What This Spec Uses |
|------------|------|---------------------|
| Config system | 01 | `KnowledgeConfig` (store_path, embedding_dimensions) |
| Error hierarchy | 01 | `KnowledgeStoreError`, `AgentFoxError` |
| Logging | 01 | Named loggers for knowledge module |
