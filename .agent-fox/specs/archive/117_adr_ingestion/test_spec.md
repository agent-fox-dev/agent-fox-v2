# Test Specification: ADR Ingestion

## Overview

Tests are organized into acceptance-criterion tests (one per requirement
criterion), property tests (one per correctness property), edge-case tests,
and integration smoke tests (one per execution path). All tests use an
in-memory DuckDB connection for database operations. No external services
are required.

## Test Cases

### TS-117-1: Detect ADR paths in touched_files

**Requirement:** 117-REQ-1.1
**Type:** unit
**Description:** Verify that detect_adr_changes filters touched_files for
docs/adr/*.md paths only.

**Preconditions:**
- None (pure function, no database needed).

**Input:**
- `touched_files = ["docs/adr/01-use-claude.md", "agent_fox/cli/code.py", "docs/adr/02-remove-fox.md", "README.md"]`

**Expected:**
- Returns `["docs/adr/01-use-claude.md", "docs/adr/02-remove-fox.md"]`

**Assertion pseudocode:**
```
result = adr.detect_adr_changes(touched_files)
ASSERT result == ["docs/adr/01-use-claude.md", "docs/adr/02-remove-fox.md"]
```

### TS-117-2: No ADR paths returns empty list

**Requirement:** 117-REQ-1.2
**Type:** unit
**Description:** Verify that detect_adr_changes returns empty list when no
ADR paths match.

**Preconditions:**
- None.

**Input:**
- `touched_files = ["agent_fox/cli/code.py", "tests/test_foo.py"]`

**Expected:**
- Returns `[]`

**Assertion pseudocode:**
```
result = adr.detect_adr_changes(touched_files)
ASSERT result == []
```

### TS-117-3: Parse valid MADR content

**Requirement:** 117-REQ-2.1
**Type:** unit
**Description:** Verify that parse_madr extracts all fields from valid MADR
content.

**Preconditions:**
- None.

**Input:**
- MADR markdown string with H1 title "Use Widget Framework", three
  considered options, and Decision Outcome choosing option 1.

**Expected:**
- ADREntry with title="Use Widget Framework", len(considered_options)==3,
  chosen_option non-empty, justification non-empty.

**Assertion pseudocode:**
```
content = VALID_MADR_FIXTURE
entry = adr.parse_madr(content)
ASSERT entry is not None
ASSERT entry.title == "Use Widget Framework"
ASSERT len(entry.considered_options) == 3
ASSERT entry.chosen_option != ""
ASSERT entry.justification != ""
```

### TS-117-4: Parse YAML frontmatter status

**Requirement:** 117-REQ-2.2
**Type:** unit
**Description:** Verify that status is extracted from YAML frontmatter.

**Preconditions:**
- None.

**Input:**
- MADR content with `status: accepted` in YAML frontmatter.

**Expected:**
- ADREntry with status="accepted".

**Assertion pseudocode:**
```
entry = adr.parse_madr(content_with_frontmatter)
ASSERT entry.status == "accepted"
```

### TS-117-5: Parse status from H2 section

**Requirement:** 117-REQ-2.3
**Type:** unit
**Description:** Verify status extraction from ## Status section when no
frontmatter.

**Preconditions:**
- None.

**Input:**
- MADR content with `## Status\n\nAccepted` and no YAML frontmatter.

**Expected:**
- ADREntry with status="accepted" (lowercased).

**Assertion pseudocode:**
```
entry = adr.parse_madr(content_with_status_section)
ASSERT entry.status == "accepted"
```

### TS-117-6: Default status when absent

**Requirement:** 117-REQ-2.4
**Type:** unit
**Description:** Verify default status "proposed" when neither frontmatter
nor Status section exists.

**Preconditions:**
- None.

**Input:**
- MADR content with no frontmatter and no ## Status section.

**Expected:**
- ADREntry with status="proposed".

**Assertion pseudocode:**
```
entry = adr.parse_madr(content_no_status)
ASSERT entry.status == "proposed"
```

### TS-117-7: Parse synonym section headings

**Requirement:** 117-REQ-2.5
**Type:** unit
**Description:** Verify that accepted synonyms for Considered Options are
recognized.

**Preconditions:**
- None.

**Input:**
- MADR content using `## Options Considered` heading with 3 bullet items.

**Expected:**
- ADREntry with len(considered_options)==3.

**Assertion pseudocode:**
```
entry = adr.parse_madr(content_with_synonym)
ASSERT len(entry.considered_options) == 3
```

### TS-117-8: Parse Decision Outcome chosen option

**Requirement:** 117-REQ-2.6
**Type:** unit
**Description:** Verify extraction of chosen option and justification from
Decision Outcome section.

**Preconditions:**
- None.

**Input:**
- MADR content with `## Decision Outcome\n\nChosen option: "Option A", because it is simpler.`

**Expected:**
- ADREntry with chosen_option="Option A", justification contains "simpler".

**Assertion pseudocode:**
```
entry = adr.parse_madr(content)
ASSERT entry.chosen_option == "Option A"
ASSERT "simpler" in entry.justification
```

### TS-117-9: Validation passes with 3+ options

**Requirement:** 117-REQ-3.1, 117-REQ-3.4
**Type:** unit
**Description:** Verify validation passes for a well-formed ADREntry.

**Preconditions:**
- None.

**Input:**
- ADREntry with title, 3 considered options, chosen_option, and all
  mandatory sections found.

**Expected:**
- ADRValidationResult with passed=True, diagnostics=[].

**Assertion pseudocode:**
```
result = adr.validate_madr(valid_entry)
ASSERT result.passed is True
ASSERT result.diagnostics == []
```

### TS-117-10: Validation fails with < 3 options

**Requirement:** 117-REQ-3.2
**Type:** unit
**Description:** Verify validation fails when fewer than 3 options.

**Preconditions:**
- None.

**Input:**
- ADREntry with 2 considered options.

**Expected:**
- ADRValidationResult with passed=False, diagnostics containing count message.

**Assertion pseudocode:**
```
result = adr.validate_madr(entry_with_2_options)
ASSERT result.passed is False
ASSERT any("3" in d for d in result.diagnostics)
```

### TS-117-11: Validation fails with empty chosen option

**Requirement:** 117-REQ-3.3
**Type:** unit
**Description:** Verify validation fails when chosen_option is empty.

**Preconditions:**
- None.

**Input:**
- ADREntry with empty chosen_option string.

**Expected:**
- ADRValidationResult with passed=False.

**Assertion pseudocode:**
```
result = adr.validate_madr(entry_no_chosen)
ASSERT result.passed is False
```

### TS-117-12: Store ADR entry in DuckDB

**Requirement:** 117-REQ-4.1
**Type:** integration
**Description:** Verify that store_adr inserts a row into adr_entries.

**Preconditions:**
- In-memory DuckDB connection with adr_entries table created via migration.

**Input:**
- Valid ADREntry with all fields populated.

**Expected:**
- Returns 1 (one row inserted).
- Row exists in adr_entries with matching id and file_path.

**Assertion pseudocode:**
```
count = adr.store_adr(conn, entry)
ASSERT count == 1
rows = conn.execute("SELECT * FROM adr_entries WHERE id = ?", [entry.id]).fetchall()
ASSERT len(rows) == 1
ASSERT rows[0][1] == entry.file_path  # file_path column
```

### TS-117-13: Content hash is SHA-256

**Requirement:** 117-REQ-4.2
**Type:** unit
**Description:** Verify content_hash computation.

**Preconditions:**
- None.

**Input:**
- Known content string "hello world".

**Expected:**
- SHA-256 hex digest matches expected value.

**Assertion pseudocode:**
```
import hashlib
content = "hello world"
expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
# ingest_adr computes content_hash internally; verify by inspecting stored entry
```

### TS-117-14: Supersede on content change

**Requirement:** 117-REQ-5.1
**Type:** integration
**Description:** Verify that modifying an ADR file supersedes the old entry.

**Preconditions:**
- In-memory DuckDB connection with adr_entries table.
- One active entry for file_path "docs/adr/01-test.md" with content_hash "aaa".

**Input:**
- New ADREntry for same file_path with content_hash "bbb".

**Expected:**
- Old entry has superseded_at IS NOT NULL.
- New entry has superseded_at IS NULL.
- Two total rows for that file_path.

**Assertion pseudocode:**
```
adr.store_adr(conn, entry_v1)
adr.store_adr(conn, entry_v2)
rows = conn.execute(
    "SELECT superseded_at FROM adr_entries WHERE file_path = ? ORDER BY created_at",
    ["docs/adr/01-test.md"]
).fetchall()
ASSERT len(rows) == 2
ASSERT rows[0][0] is not None  # v1 superseded
ASSERT rows[1][0] is None      # v2 active
```

### TS-117-15: Skip duplicate ingestion

**Requirement:** 117-REQ-5.2, 117-REQ-4.E2
**Type:** integration
**Description:** Verify that re-ingesting same content_hash is a no-op.

**Preconditions:**
- In-memory DuckDB with one active entry for file_path with hash "aaa".

**Input:**
- Same file_path, same content_hash "aaa".

**Expected:**
- Returns 0 (no insertion).
- Still one row for that file_path.

**Assertion pseudocode:**
```
adr.store_adr(conn, entry)
count = adr.store_adr(conn, entry_same_hash)
ASSERT count == 0
rows = conn.execute("SELECT COUNT(*) FROM adr_entries WHERE file_path = ?", [fp]).fetchone()
ASSERT rows[0] == 1
```

### TS-117-16: Query ADRs by spec_refs match

**Requirement:** 117-REQ-6.1
**Type:** integration
**Description:** Verify retrieval matches by spec reference.

**Preconditions:**
- In-memory DuckDB with one active ADR entry whose spec_refs contains "42".

**Input:**
- spec_name="42_rate_limiting", task_description="implement rate limiter"

**Expected:**
- Returns list with one ADREntry matching spec "42".

**Assertion pseudocode:**
```
results = adr.query_adrs(conn, "42_rate_limiting", "implement rate limiter")
ASSERT len(results) == 1
ASSERT "42" in results[0].spec_refs
```

### TS-117-17: Format ADR for prompt

**Requirement:** 117-REQ-6.2
**Type:** unit
**Description:** Verify prompt formatting produces [ADR]-prefixed string.

**Preconditions:**
- None.

**Input:**
- ADREntry with title="Use DuckDB", chosen_option="DuckDB",
  considered_options=["DuckDB", "SQLite", "PostgreSQL", "Redis"],
  justification="embedded, zero-config".

**Expected:**
- List with one string: `[ADR] Use DuckDB: Chose "DuckDB" over "SQLite", "PostgreSQL", "Redis". embedded, zero-config`

**Assertion pseudocode:**
```
result = adr.format_adrs_for_prompt([entry])
ASSERT len(result) == 1
ASSERT result[0].startswith("[ADR] ")
ASSERT '"DuckDB"' in result[0]
ASSERT '"SQLite"' in result[0]
```

### TS-117-18: FoxKnowledgeProvider.retrieve includes ADRs

**Requirement:** 117-REQ-6.3
**Type:** integration
**Description:** Verify that FoxKnowledgeProvider.retrieve returns ADR strings
alongside reviews and errata.

**Preconditions:**
- In-memory DuckDB with adr_entries table containing one matching ADR.
- FoxKnowledgeProvider instantiated with the DB.

**Input:**
- spec_name matching the stored ADR's spec_refs.

**Expected:**
- Retrieved list contains at least one string starting with "[ADR]".

**Assertion pseudocode:**
```
provider = FoxKnowledgeProvider(knowledge_db, config)
results = provider.retrieve(spec_name, task_description)
adr_items = [r for r in results if r.startswith("[ADR]")]
ASSERT len(adr_items) >= 1
```

### TS-117-19: Extract spec refs from content

**Requirement:** 117-REQ-6.4
**Type:** unit
**Description:** Verify spec reference extraction from ADR content.

**Preconditions:**
- None.

**Input:**
- Content containing "42-REQ-1.1", "spec 15", and "03_base_app".

**Expected:**
- spec_refs contains "42", "15", "03".

**Assertion pseudocode:**
```
refs = adr.extract_spec_refs(content)
ASSERT "42" in refs
ASSERT "15" in refs
ASSERT "03" in refs
```

### TS-117-20: Extract keywords from title

**Requirement:** 117-REQ-6.5
**Type:** unit
**Description:** Verify keyword extraction from ADR title.

**Preconditions:**
- None.

**Input:**
- Title "Use Claude Exclusively for Coding Agents"

**Expected:**
- Keywords include "claude", "exclusively", "coding", "agents".
- Keywords exclude "use" (stop word) and "for" (stop word/short).

**Assertion pseudocode:**
```
keywords = adr.extract_keywords("Use Claude Exclusively for Coding Agents")
ASSERT "claude" in keywords
ASSERT "exclusively" in keywords
ASSERT "use" not in keywords
ASSERT "for" not in keywords
```

### TS-117-21: Validation warning emits audit event

**Requirement:** 117-REQ-7.2
**Type:** unit
**Description:** Verify that a failed validation emits ADR_VALIDATION_FAILED
audit event.

**Preconditions:**
- Mock SinkDispatcher to capture audit events.

**Input:**
- ADR file with only 1 considered option (fails validation).

**Expected:**
- Audit event emitted with event_type ADR_VALIDATION_FAILED, severity WARNING.

**Assertion pseudocode:**
```
sink = MockSinkDispatcher()
adr.ingest_adr(conn, file_path, project_root, sink=sink, run_id="test")
events = sink.captured_events
ASSERT any(e.event_type == "adr.validation_failed" for e in events)
```

### TS-117-22: Successful ingestion emits audit event

**Requirement:** 117-REQ-7.4
**Type:** unit
**Description:** Verify that successful ingestion emits ADR_INGESTED event.

**Preconditions:**
- Mock SinkDispatcher.
- Valid MADR file on disk.

**Input:**
- Valid MADR file with 3+ options.

**Expected:**
- Audit event emitted with event_type ADR_INGESTED, severity INFO.

**Assertion pseudocode:**
```
sink = MockSinkDispatcher()
entry = adr.ingest_adr(conn, file_path, project_root, sink=sink, run_id="test")
ASSERT entry is not None
events = sink.captured_events
ASSERT any(e.event_type == "adr.ingested" for e in events)
```

## Property Test Cases

### TS-117-P1: Detection accuracy

**Property:** Property 1 from design.md
**Validates:** 117-REQ-1.1, 117-REQ-1.2, 117-REQ-1.E2
**Type:** property
**Description:** For any list of paths, detect_adr_changes returns exactly
those matching docs/adr/*.md.

**For any:** lists of strings drawn from a strategy mixing ADR paths
(`docs/adr/{name}.md`), non-ADR paths (`agent_fox/{name}.py`), deep ADR
paths (`docs/adr/sub/{name}.md`), and non-md ADR paths
(`docs/adr/{name}.txt`).

**Invariant:** The result set equals the subset of input paths matching the
glob `docs/adr/*.md` (one level, .md extension).

**Assertion pseudocode:**
```
FOR ANY paths IN mixed_path_strategy:
    result = adr.detect_adr_changes(paths)
    expected = [p for p in paths if matches_glob(p, "docs/adr/*.md")]
    ASSERT set(result) == set(expected)
```

### TS-117-P2: Parse completeness

**Property:** Property 2 from design.md
**Validates:** 117-REQ-2.1, 117-REQ-2.5, 117-REQ-2.6
**Type:** property
**Description:** For any valid MADR content, parse_madr extracts all key
fields.

**For any:** MADR content strings generated with: a random H1 title,
N ≥ 1 random option names in a Considered Options section, and a
Decision Outcome referencing the first option.

**Invariant:** The returned ADREntry has title matching the H1,
len(considered_options) == N, and chosen_option matching the first option.

**Assertion pseudocode:**
```
FOR ANY (title, options, content) IN madr_content_strategy:
    entry = adr.parse_madr(content)
    ASSERT entry is not None
    ASSERT entry.title == title
    ASSERT len(entry.considered_options) == len(options)
    ASSERT entry.chosen_option == options[0]
```

### TS-117-P3: Validation consistency

**Property:** Property 3 from design.md
**Validates:** 117-REQ-3.1, 117-REQ-3.2, 117-REQ-3.3, 117-REQ-3.4
**Type:** property
**Description:** Well-formed entries always pass; malformed entries always
fail.

**For any:** ADREntry instances generated with either (a) ≥ 3 options and
non-empty chosen_option and all mandatory sections, or (b) < 3 options or
empty chosen_option.

**Invariant:** Case (a) → passed=True, diagnostics=[]. Case (b) →
passed=False.

**Assertion pseudocode:**
```
FOR ANY entry IN valid_entry_strategy:
    result = adr.validate_madr(entry)
    ASSERT result.passed is True
    ASSERT result.diagnostics == []

FOR ANY entry IN invalid_entry_strategy:
    result = adr.validate_madr(entry)
    ASSERT result.passed is False
```

### TS-117-P4: Supersession idempotency

**Property:** Property 4 from design.md
**Validates:** 117-REQ-5.1, 117-REQ-5.2, 117-REQ-5.3
**Type:** property
**Description:** Storing the same content twice is idempotent; storing
changed content supersedes.

**For any:** ADREntry pairs sharing the same file_path but with either
identical or different content_hash values.

**Invariant:** After both stores, exactly one active row exists
(superseded_at IS NULL). If hashes differ, the active row has the
second hash. If hashes match, only one row exists total.

**Assertion pseudocode:**
```
FOR ANY (entry1, entry2) IN same_path_entry_pairs:
    store_adr(conn, entry1)
    store_adr(conn, entry2)
    active = conn.execute(
        "SELECT content_hash FROM adr_entries WHERE file_path = ? AND superseded_at IS NULL",
        [entry1.file_path]
    ).fetchall()
    ASSERT len(active) == 1
    if entry1.content_hash != entry2.content_hash:
        ASSERT active[0][0] == entry2.content_hash
```

### TS-117-P5: Retrieval excludes superseded

**Property:** Property 5 from design.md
**Validates:** 117-REQ-6.1, 117-REQ-5.3
**Type:** property
**Description:** Superseded entries never appear in query results.

**For any:** Sets of ADR entries with random superseded_at values (some NULL,
some non-NULL), query_adrs returns only entries with superseded_at IS NULL.

**Invariant:** Every returned entry has superseded_at IS NULL.

**Assertion pseudocode:**
```
FOR ANY entries IN mixed_supersession_entries:
    # Insert all entries
    for e in entries:
        conn.execute("INSERT INTO adr_entries ...")
    results = adr.query_adrs(conn, spec_name, task_desc)
    ASSERT all(r.superseded_at is None for r in results)
```

### TS-117-P6: Summary format compliance

**Property:** Property 6 from design.md
**Validates:** 117-REQ-6.2
**Type:** property
**Description:** Formatted output always starts with "[ADR] ".

**For any:** ADREntry instances with non-empty title and chosen_option.

**Invariant:** Each formatted string starts with "[ADR] ".

**Assertion pseudocode:**
```
FOR ANY entry IN valid_entry_strategy:
    result = adr.format_adrs_for_prompt([entry])
    ASSERT len(result) == 1
    ASSERT result[0].startswith("[ADR] ")
```

### TS-117-P7: Content hash determinism

**Property:** Property 7 from design.md
**Validates:** 117-REQ-4.2, 117-REQ-5.2
**Type:** property
**Description:** SHA-256 of the same content always produces the same hash.

**For any:** Arbitrary UTF-8 strings.

**Invariant:** `sha256(s) == sha256(s)` for all s.

**Assertion pseudocode:**
```
FOR ANY s IN text_strategy:
    h1 = hashlib.sha256(s.encode()).hexdigest()
    h2 = hashlib.sha256(s.encode()).hexdigest()
    ASSERT h1 == h2
```

## Edge Case Tests

### TS-117-E1: Empty touched_files

**Requirement:** 117-REQ-1.E1
**Type:** unit
**Description:** Verify detect_adr_changes handles empty and None inputs.

**Preconditions:**
- None.

**Input:**
- `touched_files = []` and `touched_files = None` (if supported).

**Expected:**
- Returns `[]`.

**Assertion pseudocode:**
```
ASSERT adr.detect_adr_changes([]) == []
```

### TS-117-E2: Non-.md ADR path excluded

**Requirement:** 117-REQ-1.E2
**Type:** unit
**Description:** Verify that non-.md files under docs/adr/ are excluded.

**Preconditions:**
- None.

**Input:**
- `touched_files = ["docs/adr/01-test.markdown", "docs/adr/notes.txt"]`

**Expected:**
- Returns `[]`.

**Assertion pseudocode:**
```
ASSERT adr.detect_adr_changes(["docs/adr/01-test.markdown", "docs/adr/notes.txt"]) == []
```

### TS-117-E3: No H1 heading parse failure

**Requirement:** 117-REQ-2.E1
**Type:** unit
**Description:** Verify parse_madr returns None when content has no H1.

**Preconditions:**
- None.

**Input:**
- Content "## Some H2 heading\n\nBody text" (no H1).

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
result = adr.parse_madr("## Some H2 heading\n\nBody text")
ASSERT result is None
```

### TS-117-E4: Empty title validation failure

**Requirement:** 117-REQ-3.E1
**Type:** unit
**Description:** Verify validation fails with empty title.

**Preconditions:**
- None.

**Input:**
- ADREntry with title="" but otherwise valid.

**Expected:**
- ADRValidationResult with passed=False.

**Assertion pseudocode:**
```
entry = ADREntry(id="x", file_path="x", title="", ...)
result = adr.validate_madr(entry)
ASSERT result.passed is False
```

### TS-117-E5: DB unavailable during store

**Requirement:** 117-REQ-4.E1
**Type:** unit
**Description:** Verify store_adr returns 0 when DB is unavailable.

**Preconditions:**
- Closed or invalid DuckDB connection.

**Input:**
- Valid ADREntry.

**Expected:**
- Returns 0, logs WARNING.

**Assertion pseudocode:**
```
conn.close()
result = adr.store_adr(conn, entry)
ASSERT result == 0
```

### TS-117-E6: adr_entries table missing during query

**Requirement:** 117-REQ-6.E1
**Type:** unit
**Description:** Verify query_adrs returns empty list when table missing.

**Preconditions:**
- DuckDB connection with no adr_entries table.

**Input:**
- Any spec_name and task_description.

**Expected:**
- Returns [].

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
result = adr.query_adrs(conn, "any_spec", "any task")
ASSERT result == []
```

### TS-117-E7: No matching ADRs

**Requirement:** 117-REQ-6.E2
**Type:** unit
**Description:** Verify query_adrs returns empty when no ADRs match.

**Preconditions:**
- DuckDB with adr_entries table but entries with unrelated spec_refs.

**Input:**
- spec_name="99_unrelated", task_description="unrelated task"

**Expected:**
- Returns [].

**Assertion pseudocode:**
```
result = adr.query_adrs(conn, "99_unrelated", "unrelated task")
ASSERT result == []
```

### TS-117-E8: Superseded file_path with new content

**Requirement:** 117-REQ-5.E1
**Type:** integration
**Description:** Verify new entry is active when all existing entries for
file_path are superseded.

**Preconditions:**
- DuckDB with one superseded entry for file_path (superseded_at set).

**Input:**
- New ADREntry for same file_path with new content_hash.

**Expected:**
- New entry inserted with superseded_at IS NULL.

**Assertion pseudocode:**
```
# Manually insert a superseded entry
conn.execute("INSERT INTO adr_entries (..., superseded_at) VALUES (..., NOW())")
adr.store_adr(conn, new_entry)
active = conn.execute(
    "SELECT id FROM adr_entries WHERE file_path = ? AND superseded_at IS NULL",
    [file_path]
).fetchall()
ASSERT len(active) == 1
ASSERT active[0][0] == new_entry.id
```

## Integration Smoke Tests

### TS-117-SMOKE-1: Full Ingest Pipeline

**Execution Path:** Path 1 from design.md
**Description:** Verify the complete ADR detection → parse → validate → store
pipeline using real components.

**Setup:** Write a valid MADR file to a temp directory under `docs/adr/`.
Create an in-memory DuckDB with adr_entries table via migration. No mocks
on adr.py functions.

**Trigger:** Call `ingest_adr(conn, "docs/adr/07-test.md", project_root)`.

**Expected side effects:**
- Returns a non-None ADREntry.
- One row exists in adr_entries with matching file_path and title.
- content_hash matches SHA-256 of the file content.

**Must NOT satisfy with:** Mocking parse_madr, validate_madr, or store_adr.

**Assertion pseudocode:**
```
# Setup
project_root = tmp_path
adr_dir = project_root / "docs" / "adr"
adr_dir.mkdir(parents=True)
(adr_dir / "07-test.md").write_text(VALID_MADR_CONTENT)
conn = duckdb.connect(":memory:")
run_migrations(conn)

# Execute
entry = adr.ingest_adr(conn, "docs/adr/07-test.md", project_root)

# Verify
ASSERT entry is not None
rows = conn.execute("SELECT title FROM adr_entries WHERE file_path = ?",
                     ["docs/adr/07-test.md"]).fetchall()
ASSERT len(rows) == 1
```

### TS-117-SMOKE-2: Full Retrieve Pipeline

**Execution Path:** Path 2 from design.md
**Description:** Verify the complete ADR query → format → inject pipeline
via FoxKnowledgeProvider.retrieve().

**Setup:** In-memory DuckDB with adr_entries table containing one active ADR
entry whose spec_refs include "42". Create FoxKnowledgeProvider with this DB.
No mocks on adr.py or fox_provider.py.

**Trigger:** Call `provider.retrieve("42_rate_limiting", "implement rate limiter")`.

**Expected side effects:**
- Returned list contains at least one string starting with "[ADR]".

**Must NOT satisfy with:** Mocking query_adrs or format_adrs_for_prompt.

**Assertion pseudocode:**
```
# Setup
conn = duckdb.connect(":memory:")
run_migrations(conn)
adr.store_adr(conn, entry_with_spec_ref_42)
provider = FoxKnowledgeProvider(knowledge_db, config)

# Execute
results = provider.retrieve("42_rate_limiting", "implement rate limiter")

# Verify
adr_items = [r for r in results if r.startswith("[ADR]")]
ASSERT len(adr_items) >= 1
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 117-REQ-1.1 | TS-117-1 | unit |
| 117-REQ-1.2 | TS-117-2 | unit |
| 117-REQ-1.3 | (covered by TS-117-SMOKE-1 setup) | integration |
| 117-REQ-1.E1 | TS-117-E1 | unit |
| 117-REQ-1.E2 | TS-117-E2 | unit |
| 117-REQ-2.1 | TS-117-3 | unit |
| 117-REQ-2.2 | TS-117-4 | unit |
| 117-REQ-2.3 | TS-117-5 | unit |
| 117-REQ-2.4 | TS-117-6 | unit |
| 117-REQ-2.5 | TS-117-7 | unit |
| 117-REQ-2.6 | TS-117-8 | unit |
| 117-REQ-2.E1 | TS-117-E3 | unit |
| 117-REQ-2.E2 | (covered by TS-117-SMOKE-1) | integration |
| 117-REQ-3.1 | TS-117-9 | unit |
| 117-REQ-3.2 | TS-117-10 | unit |
| 117-REQ-3.3 | TS-117-11 | unit |
| 117-REQ-3.4 | TS-117-9 | unit |
| 117-REQ-3.E1 | TS-117-E4 | unit |
| 117-REQ-4.1 | TS-117-12 | integration |
| 117-REQ-4.2 | TS-117-13 | unit |
| 117-REQ-4.3 | TS-117-SMOKE-1 | integration |
| 117-REQ-4.4 | TS-117-12 | integration |
| 117-REQ-4.E1 | TS-117-E5 | unit |
| 117-REQ-4.E2 | TS-117-15 | integration |
| 117-REQ-5.1 | TS-117-14 | integration |
| 117-REQ-5.2 | TS-117-15 | integration |
| 117-REQ-5.3 | TS-117-14 | integration |
| 117-REQ-5.E1 | TS-117-E8 | integration |
| 117-REQ-6.1 | TS-117-16 | integration |
| 117-REQ-6.2 | TS-117-17 | unit |
| 117-REQ-6.3 | TS-117-18 | integration |
| 117-REQ-6.4 | TS-117-19 | unit |
| 117-REQ-6.5 | TS-117-20 | unit |
| 117-REQ-6.E1 | TS-117-E6 | unit |
| 117-REQ-6.E2 | TS-117-E7 | unit |
| 117-REQ-7.1 | TS-117-21 | unit |
| 117-REQ-7.2 | TS-117-21 | unit |
| 117-REQ-7.3 | TS-117-21 | unit |
| 117-REQ-7.4 | TS-117-22 | unit |
| 117-REQ-7.E1 | (covered by TS-117-21 with sink=None) | unit |
| Property 1 | TS-117-P1 | property |
| Property 2 | TS-117-P2 | property |
| Property 3 | TS-117-P3 | property |
| Property 4 | TS-117-P4 | property |
| Property 5 | TS-117-P5 | property |
| Property 6 | TS-117-P6 | property |
| Property 7 | TS-117-P7 | property |
