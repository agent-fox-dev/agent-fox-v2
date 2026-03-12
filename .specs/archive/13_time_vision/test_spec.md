# Test Specification: Time Vision -- Temporal Reasoning

## Overview

Tests for the Time Vision temporal reasoning system: causal graph operations,
temporal queries, pattern detection, timeline rendering, extraction prompt
enrichment, and context enhancement. Tests map to requirements in
`requirements.md` and correctness properties in `design.md`.

## Test Fixtures

All tests that require DuckDB use an in-memory database with the following
seeded data:

```python
@pytest.fixture
def causal_db():
    """In-memory DuckDB with schema and seeded causal data."""
    conn = duckdb.connect(":memory:")
    # Create schema (memory_facts, fact_causes, session_outcomes)
    conn.execute(SCHEMA_SQL)
    # Seed facts
    conn.execute("""
        INSERT INTO memory_facts (id, content, spec_name, session_id,
                                  commit_sha, category, confidence, created_at)
        VALUES
            ('aaa...', 'User.email changed to nullable', '07_oauth', '07/3',
             'a1b2c3d', 'decision', 'high', '2025-11-03 14:22:00'),
            ('bbb...', 'test_user_model.py assertions failed', '09_user_tests', '09/1',
             'e4f5g6h', 'gotcha', 'high', '2025-11-17 09:15:00'),
            ('ccc...', 'Added migration for nullable email', '12_auth_fix', '12/2',
             'i7j8k9l', 'pattern', 'high', '2025-11-18 11:30:00'),
            ('ddd...', 'Isolated root fact with no links', '05_setup', '05/1',
             NULL, 'convention', 'medium', '2025-10-01 08:00:00'),
            ('eee...', 'Auth module refactored', '17_auth_v2', '17/1',
             'm0n1o2p', 'decision', 'high', '2025-12-01 10:00:00')
    """)
    # Seed causal links: aaa -> bbb -> ccc, aaa -> eee
    conn.execute("""
        INSERT INTO fact_causes (cause_id, effect_id) VALUES
            ('aaa...', 'bbb...'),
            ('bbb...', 'ccc...'),
            ('aaa...', 'eee...')
    """)
    # Seed session outcomes for pattern detection
    conn.execute("""
        INSERT INTO session_outcomes (id, spec_name, task_group, node_id,
                                      touched_path, status, created_at)
        VALUES
            ('s1', '07_oauth', '3', '07/3', 'src/auth/user.py', 'completed',
             '2025-11-03 14:00:00'),
            ('s2', '09_user_tests', '1', '09/1', 'tests/test_user_model.py', 'failed',
             '2025-11-03 15:00:00'),
            ('s3', '14_billing', '2', '14/2', 'src/auth/session.py', 'completed',
             '2025-12-10 10:00:00'),
            ('s4', '15_payments', '1', '15/1', 'tests/test_payments.py', 'failed',
             '2025-12-10 11:00:00'),
            ('s5', '20_auth_v3', '1', '20/1', 'src/auth/user.py', 'completed',
             '2026-01-05 09:00:00'),
            ('s6', '21_user_tests_v2', '1', '21/1', 'tests/test_user_model.py', 'failed',
             '2026-01-05 10:00:00')
    """)
    yield conn
    conn.close()
```

## Test Cases

### TS-13-1: Add causal link succeeds

**Requirement:** 13-REQ-3.1
**Type:** unit
**Description:** Verify that a causal link between two existing facts is
inserted into the `fact_causes` table.

**Preconditions:**
- In-memory DuckDB with seeded facts `aaa` and `ddd` (no existing link
  between them).

**Input:**
- `add_causal_link(conn, cause_id="ddd...", effect_id="aaa...")`

**Expected:**
- Returns True.
- `fact_causes` contains a row `(ddd..., aaa...)`.

**Assertion pseudocode:**
```
result = add_causal_link(conn, "ddd...", "aaa...")
ASSERT result == True
rows = conn.execute("SELECT * FROM fact_causes WHERE cause_id='ddd...' AND effect_id='aaa...'").fetchall()
ASSERT len(rows) == 1
```

---

### TS-13-2: Add causal link rejects non-existent fact

**Requirement:** 13-REQ-3.1, 13-REQ-2.E2
**Type:** unit
**Description:** Verify that a causal link referencing a non-existent fact
is rejected without error.

**Preconditions:**
- In-memory DuckDB with seeded facts.

**Input:**
- `add_causal_link(conn, cause_id="aaa...", effect_id="nonexistent")`

**Expected:**
- Returns False.
- No row inserted into `fact_causes` with effect_id `nonexistent`.

**Assertion pseudocode:**
```
result = add_causal_link(conn, "aaa...", "nonexistent")
ASSERT result == False
rows = conn.execute("SELECT * FROM fact_causes WHERE effect_id='nonexistent'").fetchall()
ASSERT len(rows) == 0
```

---

### TS-13-3: Get direct causes

**Requirement:** 13-REQ-3.2
**Type:** unit
**Description:** Verify that querying causes of a fact returns the correct
direct causes.

**Preconditions:**
- In-memory DuckDB with seeded causal links: `aaa -> bbb`.

**Input:**
- `get_causes(conn, fact_id="bbb...")`

**Expected:**
- Returns a list with one CausalFact whose `fact_id` is `aaa...`.

**Assertion pseudocode:**
```
causes = get_causes(conn, "bbb...")
ASSERT len(causes) == 1
ASSERT causes[0].fact_id == "aaa..."
ASSERT causes[0].content == "User.email changed to nullable"
```

---

### TS-13-4: Get direct effects

**Requirement:** 13-REQ-3.3
**Type:** unit
**Description:** Verify that querying effects of a fact returns the correct
direct effects.

**Preconditions:**
- In-memory DuckDB with seeded causal links: `aaa -> bbb`, `aaa -> eee`.

**Input:**
- `get_effects(conn, fact_id="aaa...")`

**Expected:**
- Returns a list with two CausalFact entries: `bbb...` and `eee...`.

**Assertion pseudocode:**
```
effects = get_effects(conn, "aaa...")
ASSERT len(effects) == 2
effect_ids = {e.fact_id for e in effects}
ASSERT "bbb..." IN effect_ids
ASSERT "eee..." IN effect_ids
```

---

### TS-13-5: Traverse causal chain forward

**Requirement:** 13-REQ-3.4
**Type:** unit
**Description:** Verify that traversing effects from a root fact returns the
full downstream chain.

**Preconditions:**
- In-memory DuckDB with seeded chain: `aaa -> bbb -> ccc`, `aaa -> eee`.

**Input:**
- `traverse_causal_chain(conn, fact_id="aaa...", direction="effects")`

**Expected:**
- Returns 4 facts: `aaa` (depth 0), `bbb` (depth 1), `ccc` (depth 2),
  `eee` (depth 1).

**Assertion pseudocode:**
```
chain = traverse_causal_chain(conn, "aaa...", direction="effects")
ASSERT len(chain) == 4
depths = {f.fact_id: f.depth for f in chain}
ASSERT depths["aaa..."] == 0
ASSERT depths["bbb..."] == 1
ASSERT depths["ccc..."] == 2
ASSERT depths["eee..."] == 1
```

---

### TS-13-6: Traverse causal chain backward

**Requirement:** 13-REQ-3.4
**Type:** unit
**Description:** Verify that traversing causes from an effect fact returns
the upstream chain.

**Preconditions:**
- In-memory DuckDB with seeded chain: `aaa -> bbb -> ccc`.

**Input:**
- `traverse_causal_chain(conn, fact_id="ccc...", direction="causes")`

**Expected:**
- Returns 3 facts: `ccc` (depth 0), `bbb` (depth -1), `aaa` (depth -2).

**Assertion pseudocode:**
```
chain = traverse_causal_chain(conn, "ccc...", direction="causes")
ASSERT len(chain) == 3
depths = {f.fact_id: f.depth for f in chain}
ASSERT depths["ccc..."] == 0
ASSERT depths["bbb..."] == -1
ASSERT depths["aaa..."] == -2
```

---

### TS-13-7: Traverse respects max depth

**Requirement:** 13-REQ-3.4
**Type:** unit
**Description:** Verify that traversal stops at the configured max depth.

**Preconditions:**
- In-memory DuckDB with seeded chain: `aaa -> bbb -> ccc`.

**Input:**
- `traverse_causal_chain(conn, fact_id="aaa...", max_depth=1, direction="effects")`

**Expected:**
- Returns 3 facts: `aaa` (depth 0), `bbb` (depth 1), `eee` (depth 1).
  `ccc` (depth 2) is excluded.

**Assertion pseudocode:**
```
chain = traverse_causal_chain(conn, "aaa...", max_depth=1, direction="effects")
fact_ids = {f.fact_id for f in chain}
ASSERT "aaa..." IN fact_ids
ASSERT "bbb..." IN fact_ids
ASSERT "eee..." IN fact_ids
ASSERT "ccc..." NOT IN fact_ids
```

---

### TS-13-8: Traverse isolated fact returns only itself

**Requirement:** 13-REQ-3.4
**Type:** unit
**Description:** Verify that traversing from a fact with no causal links
returns only that fact.

**Preconditions:**
- In-memory DuckDB with seeded fact `ddd` (no causal links).

**Input:**
- `traverse_causal_chain(conn, fact_id="ddd...")`

**Expected:**
- Returns a list with one CausalFact: `ddd` at depth 0 with relationship
  "root".

**Assertion pseudocode:**
```
chain = traverse_causal_chain(conn, "ddd...")
ASSERT len(chain) == 1
ASSERT chain[0].fact_id == "ddd..."
ASSERT chain[0].depth == 0
ASSERT chain[0].relationship == "root"
```

---

### TS-13-9: Build timeline from seed facts

**Requirement:** 13-REQ-4.1, 13-REQ-6.1, 13-REQ-6.2
**Type:** unit
**Description:** Verify that building a timeline from seed facts produces
an ordered, indented timeline.

**Preconditions:**
- In-memory DuckDB with seeded facts and causal links.

**Input:**
- `build_timeline(conn, seed_fact_ids=["aaa..."])`

**Expected:**
- Timeline contains nodes for `aaa`, `bbb`, `ccc`, `eee`.
- Nodes are ordered by timestamp.
- Root node has depth 0; effects have increasing depth.

**Assertion pseudocode:**
```
timeline = build_timeline(conn, ["aaa..."])
ASSERT len(timeline.nodes) == 4
ASSERT timeline.nodes[0].fact_id == "aaa..."
ASSERT timeline.nodes[0].depth == 0
# Timestamps are in ascending order
for i in range(1, len(timeline.nodes)):
    ASSERT timeline.nodes[i].timestamp >= timeline.nodes[i-1].timestamp
```

---

### TS-13-10: Timeline render produces plain text

**Requirement:** 13-REQ-6.3
**Type:** unit
**Description:** Verify that timeline rendering with `use_color=False`
produces plain text without ANSI escape codes.

**Preconditions:**
- A Timeline with seeded nodes.

**Input:**
- `timeline.render(use_color=False)`

**Expected:**
- Output is a non-empty string.
- Output contains no ANSI escape sequences (`\x1b[`).
- Output contains fact content and provenance.

**Assertion pseudocode:**
```
text = timeline.render(use_color=False)
ASSERT len(text) > 0
ASSERT "\x1b[" NOT IN text
ASSERT "User.email changed to nullable" IN text
ASSERT "07_oauth" IN text
```

---

### TS-13-11: Detect patterns finds recurring co-occurrences

**Requirement:** 13-REQ-5.1, 13-REQ-5.2
**Type:** unit
**Description:** Verify that pattern detection identifies recurring
path-change-to-failure sequences.

**Preconditions:**
- In-memory DuckDB with seeded session outcomes showing `src/auth/user.py`
  changes followed by test failures (at least 2 occurrences).

**Input:**
- `detect_patterns(conn, min_occurrences=2)`

**Expected:**
- Returns at least one Pattern.
- The pattern's trigger mentions `src/auth/` paths.
- `occurrences >= 2`.
- `confidence` is one of "high", "medium", "low".

**Assertion pseudocode:**
```
patterns = detect_patterns(conn, min_occurrences=2)
ASSERT len(patterns) >= 1
ASSERT any("src/auth/" in p.trigger for p in patterns)
ASSERT all(p.occurrences >= 2 for p in patterns)
ASSERT all(p.confidence in ("high", "medium", "low") for p in patterns)
```

---

### TS-13-12: Detect patterns with insufficient data

**Requirement:** 13-REQ-5.E1
**Type:** unit
**Description:** Verify that pattern detection returns an empty list when
there is insufficient data.

**Preconditions:**
- In-memory DuckDB with empty `session_outcomes` table.

**Input:**
- `detect_patterns(conn, min_occurrences=2)`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
conn_empty = create_empty_db()
patterns = detect_patterns(conn_empty, min_occurrences=2)
ASSERT len(patterns) == 0
```

---

### TS-13-13: Render patterns as text

**Requirement:** 13-REQ-5.3
**Type:** unit
**Description:** Verify that pattern rendering produces readable text output.

**Preconditions:**
- A list of Pattern objects.

**Input:**
- `render_patterns(patterns, use_color=False)`

**Expected:**
- Output contains trigger and effect text.
- Output contains occurrence count.
- No ANSI escape codes when `use_color=False`.

**Assertion pseudocode:**
```
patterns = [Pattern(trigger="src/auth/", effect="test failures",
                    occurrences=3, last_seen="2026-01-05", confidence="medium")]
text = render_patterns(patterns, use_color=False)
ASSERT "src/auth/" IN text
ASSERT "test failures" IN text
ASSERT "3" IN text
ASSERT "\x1b[" NOT IN text
```

---

### TS-13-14: Enrich extraction prompt includes prior facts

**Requirement:** 13-REQ-2.1
**Type:** unit
**Description:** Verify that the enriched extraction prompt includes causal
instructions and prior fact references.

**Preconditions:**
- A base extraction prompt string.
- A list of prior fact dictionaries.

**Input:**
- `enrich_extraction_with_causal(base_prompt, prior_facts)`

**Expected:**
- Result contains the base prompt.
- Result contains "Causal Relationships" section.
- Result contains prior fact content.

**Assertion pseudocode:**
```
prior = [{"id": "aaa", "content": "User.email nullable"}]
result = enrich_extraction_with_causal("Extract facts:", prior)
ASSERT "Extract facts:" IN result
ASSERT "Causal Relationships" IN result
ASSERT "User.email nullable" IN result
```

---

### TS-13-15: Parse causal links from extraction response

**Requirement:** 13-REQ-2.2
**Type:** unit
**Description:** Verify that causal link pairs are correctly parsed from the
extraction model's response.

**Preconditions:** None.

**Input:**
- A string containing JSON causal link objects.

**Expected:**
- Returns a list of (cause_id, effect_id) tuples.

**Assertion pseudocode:**
```
response = '[{"cause_id": "aaa", "effect_id": "bbb"}, {"cause_id": "ccc", "effect_id": "ddd"}]'
links = parse_causal_links(response)
ASSERT len(links) == 2
ASSERT links[0] == ("aaa", "bbb")
ASSERT links[1] == ("ccc", "ddd")
```

---

### TS-13-16: Parse causal links handles malformed input

**Requirement:** 13-REQ-2.E1
**Type:** unit
**Description:** Verify that malformed causal link JSON is silently skipped.

**Preconditions:** None.

**Input:**
- A string with a mix of valid and malformed JSON entries.

**Expected:**
- Only valid entries are returned; malformed entries are skipped.

**Assertion pseudocode:**
```
response = '[{"cause_id": "aaa", "effect_id": "bbb"}, {"bad": "entry"}, "not json"]'
links = parse_causal_links(response)
ASSERT len(links) == 1
ASSERT links[0] == ("aaa", "bbb")
```

---

### TS-13-17: Context enhancement adds causal facts

**Requirement:** 13-REQ-7.1, 13-REQ-7.2
**Type:** unit
**Description:** Verify that context selection includes causally-linked facts
alongside keyword-matched facts.

**Preconditions:**
- In-memory DuckDB with seeded facts and causal links.
- Keyword facts include fact `aaa`.

**Input:**
- `select_context_with_causal(conn, spec_name="07_oauth",
   touched_files=["src/auth/user.py"],
   keyword_facts=[{"id": "aaa...", "content": "..."}],
   max_facts=50, causal_budget=10)`

**Expected:**
- Result includes fact `aaa` (keyword match).
- Result includes facts `bbb` and `eee` (causal links from `aaa`).
- Total facts <= 50.

**Assertion pseudocode:**
```
result = select_context_with_causal(
    conn, "07_oauth", ["src/auth/user.py"],
    keyword_facts=[{"id": "aaa...", "content": "..."}],
    max_facts=50, causal_budget=10
)
result_ids = {f["id"] for f in result}
ASSERT "aaa..." IN result_ids
ASSERT "bbb..." IN result_ids OR "eee..." IN result_ids
ASSERT len(result) <= 50
```

---

### TS-13-18: Context enhancement respects budget

**Requirement:** 13-REQ-7.2
**Type:** unit
**Description:** Verify that context selection does not exceed the max_facts
budget even when many causal links exist.

**Preconditions:**
- In-memory DuckDB with many facts and causal links.
- Keyword facts fill most of the budget.

**Input:**
- `select_context_with_causal(conn, ..., keyword_facts=forty_five_facts,
   max_facts=50, causal_budget=10)`

**Expected:**
- Total facts <= 50.

**Assertion pseudocode:**
```
keyword_facts = [{"id": f"kw_{i}", "content": f"fact {i}"} for i in range(45)]
result = select_context_with_causal(
    conn, "test_spec", [],
    keyword_facts=keyword_facts,
    max_facts=50, causal_budget=10
)
ASSERT len(result) <= 50
```

---

### TS-13-19: Fact provenance populated on storage

**Requirement:** 13-REQ-1.1, 13-REQ-1.2
**Type:** unit
**Description:** Verify that facts stored in memory_facts carry provenance
metadata.

**Preconditions:**
- In-memory DuckDB with seeded facts.

**Input:**
- Query facts from `memory_facts` table.

**Expected:**
- Facts have `spec_name`, `session_id` populated.
- `commit_sha` may be NULL for facts where it was unavailable.

**Assertion pseudocode:**
```
row = conn.execute("SELECT spec_name, session_id, commit_sha FROM memory_facts WHERE id='aaa...'").fetchone()
ASSERT row[0] == "07_oauth"
ASSERT row[1] == "07/3"
ASSERT row[2] == "a1b2c3d"

row2 = conn.execute("SELECT commit_sha FROM memory_facts WHERE id='ddd...'").fetchone()
ASSERT row2[0] IS None  # commit_sha can be NULL
```

## Property Test Cases

### TS-13-P1: Causal link idempotency

**Property:** Property 2 from design.md
**Validates:** 13-REQ-3.E1
**Type:** property
**Description:** Inserting the same causal link twice results in exactly one row.

**For any:** pair of existing fact IDs (cause_id, effect_id)
**Invariant:** After two calls to `add_causal_link(conn, cause_id, effect_id)`,
exactly one row exists in `fact_causes` for that pair.

**Assertion pseudocode:**
```
FOR ANY cause_id, effect_id IN existing_fact_ids():
    add_causal_link(conn, cause_id, effect_id)
    add_causal_link(conn, cause_id, effect_id)
    count = conn.execute(
        "SELECT COUNT(*) FROM fact_causes WHERE cause_id=? AND effect_id=?",
        [cause_id, effect_id]
    ).fetchone()[0]
    ASSERT count == 1
```

---

### TS-13-P2: Traversal depth bound

**Property:** Property 3 from design.md
**Validates:** 13-REQ-3.4
**Type:** property
**Description:** No fact in a traversal result exceeds the configured max depth.

**For any:** starting fact_id and max_depth in [1, 20]
**Invariant:** All returned CausalFact entries have `abs(depth) <= max_depth`.

**Assertion pseudocode:**
```
FOR ANY fact_id IN existing_fact_ids(),
        max_depth IN integers(min=1, max=20):
    chain = traverse_causal_chain(conn, fact_id, max_depth=max_depth)
    FOR EACH fact IN chain:
        ASSERT abs(fact.depth) <= max_depth
```

---

### TS-13-P3: Timeline ordering

**Property:** Property 5 from design.md
**Validates:** 13-REQ-6.1, 13-REQ-6.2
**Type:** property
**Description:** Timeline nodes are always ordered by timestamp.

**For any:** set of seed fact IDs from the database
**Invariant:** The timeline's nodes are in non-decreasing timestamp order.

**Assertion pseudocode:**
```
FOR ANY seed_ids IN subsets_of(existing_fact_ids()):
    timeline = build_timeline(conn, seed_ids)
    timestamps = [n.timestamp for n in timeline.nodes if n.timestamp]
    ASSERT timestamps == sorted(timestamps)
```

---

### TS-13-P4: Pattern minimum threshold

**Property:** Property 6 from design.md
**Validates:** 13-REQ-5.1, 13-REQ-5.2
**Type:** property
**Description:** Every detected pattern meets the minimum occurrence threshold.

**For any:** min_occurrences in [1, 10]
**Invariant:** All returned patterns have `occurrences >= min_occurrences`.

**Assertion pseudocode:**
```
FOR ANY min_occ IN integers(min=1, max=10):
    patterns = detect_patterns(conn, min_occurrences=min_occ)
    FOR EACH p IN patterns:
        ASSERT p.occurrences >= min_occ
```

---

### TS-13-P5: Context budget compliance

**Property:** Property 7 from design.md
**Validates:** 13-REQ-7.2
**Type:** property
**Description:** Context selection never exceeds the max_facts budget.

**For any:** max_facts in [1, 100], keyword_facts list of any size
**Invariant:** `len(result) <= max_facts`.

**Assertion pseudocode:**
```
FOR ANY max_facts IN integers(min=1, max=100),
        n_keywords IN integers(min=0, max=200):
    keyword_facts = generate_keyword_facts(n_keywords)
    result = select_context_with_causal(
        conn, "test", [],
        keyword_facts=keyword_facts,
        max_facts=max_facts
    )
    ASSERT len(result) <= max_facts
```

---

### TS-13-P6: Referential integrity on insert

**Property:** Property 1 from design.md
**Validates:** 13-REQ-3.1, 13-REQ-2.E2
**Type:** property
**Description:** Causal links are only inserted when both fact IDs exist.

**For any:** pair of UUIDs (cause_id, effect_id) where at least one does not
exist in memory_facts
**Invariant:** `add_causal_link()` returns False and no row is inserted.

**Assertion pseudocode:**
```
FOR ANY nonexistent_id IN random_uuids():
    result = add_causal_link(conn, nonexistent_id, "aaa...")
    ASSERT result == False
    result = add_causal_link(conn, "aaa...", nonexistent_id)
    ASSERT result == False
```

## Edge Case Tests

### TS-13-E1: Duplicate causal link is idempotent

**Requirement:** 13-REQ-3.E1
**Type:** unit
**Description:** Inserting a duplicate causal link does not raise an error.

**Preconditions:**
- In-memory DuckDB with existing causal link `aaa -> bbb`.

**Input:**
- `add_causal_link(conn, "aaa...", "bbb...")` (duplicate)

**Expected:**
- Returns False (no new row).
- No exception raised.
- Still exactly one row for `(aaa..., bbb...)`.

**Assertion pseudocode:**
```
result = add_causal_link(conn, "aaa...", "bbb...")
ASSERT result == False
count = conn.execute(
    "SELECT COUNT(*) FROM fact_causes WHERE cause_id='aaa...' AND effect_id='bbb...'"
).fetchone()[0]
ASSERT count == 1
```

---

### TS-13-E2: Extraction returns no causal links

**Requirement:** 13-REQ-2.E1
**Type:** unit
**Description:** When extraction finds no causal relationships, facts are
stored without links and no error is raised.

**Preconditions:** None.

**Input:**
- `parse_causal_links("[]")`

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
links = parse_causal_links("[]")
ASSERT len(links) == 0
```

---

### TS-13-E3: Extraction returns completely invalid JSON

**Requirement:** 13-REQ-2.E1
**Type:** unit
**Description:** When the extraction model returns unparseable content,
the parser returns an empty list without raising.

**Preconditions:** None.

**Input:**
- `parse_causal_links("This is not JSON at all")`

**Expected:**
- Returns an empty list.
- No exception raised.

**Assertion pseudocode:**
```
links = parse_causal_links("This is not JSON at all")
ASSERT len(links) == 0
```

---

### TS-13-E4: Timeline with no causal links

**Requirement:** 13-REQ-4.1
**Type:** unit
**Description:** Building a timeline from a fact with no causal links returns
a timeline with just that fact.

**Preconditions:**
- In-memory DuckDB with fact `ddd` (no causal links).

**Input:**
- `build_timeline(conn, seed_fact_ids=["ddd..."])`

**Expected:**
- Timeline has exactly one node.
- Node has depth 0 and relationship "root".

**Assertion pseudocode:**
```
timeline = build_timeline(conn, ["ddd..."])
ASSERT len(timeline.nodes) == 1
ASSERT timeline.nodes[0].fact_id == "ddd..."
ASSERT timeline.nodes[0].relationship == "root"
```

---

### TS-13-E5: Patterns command with no knowledge store

**Requirement:** 13-REQ-5.E1
**Type:** unit
**Description:** The patterns command handles an empty or unavailable
knowledge store gracefully.

**Preconditions:**
- In-memory DuckDB with empty tables.

**Input:**
- `detect_patterns(conn)`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
conn_empty = create_db_with_empty_tables()
patterns = detect_patterns(conn_empty)
ASSERT len(patterns) == 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 13-REQ-1.1 | TS-13-19 | unit |
| 13-REQ-1.2 | TS-13-19 | unit |
| 13-REQ-2.1 | TS-13-14 | unit |
| 13-REQ-2.2 | TS-13-15 | unit |
| 13-REQ-2.E1 | TS-13-16, TS-13-E2, TS-13-E3 | unit |
| 13-REQ-2.E2 | TS-13-2, TS-13-P6 | unit, property |
| 13-REQ-3.1 | TS-13-1, TS-13-2, TS-13-P6 | unit, property |
| 13-REQ-3.2 | TS-13-3 | unit |
| 13-REQ-3.3 | TS-13-4 | unit |
| 13-REQ-3.4 | TS-13-5, TS-13-6, TS-13-7, TS-13-8, TS-13-P2 | unit, property |
| 13-REQ-3.E1 | TS-13-E1, TS-13-P1 | unit, property |
| 13-REQ-4.1 | TS-13-9, TS-13-E4 | unit |
| 13-REQ-4.2 | TS-13-9 | unit |
| 13-REQ-5.1 | TS-13-11, TS-13-P4 | unit, property |
| 13-REQ-5.2 | TS-13-11, TS-13-P4 | unit, property |
| 13-REQ-5.3 | TS-13-13 | unit |
| 13-REQ-5.E1 | TS-13-12, TS-13-E5 | unit |
| 13-REQ-6.1 | TS-13-9, TS-13-10, TS-13-P3 | unit, property |
| 13-REQ-6.2 | TS-13-9, TS-13-P3 | unit, property |
| 13-REQ-6.3 | TS-13-10 | unit |
| 13-REQ-7.1 | TS-13-17 | unit |
| 13-REQ-7.2 | TS-13-17, TS-13-18, TS-13-P5 | unit, property |
| Property 1 | TS-13-P6 | property |
| Property 2 | TS-13-P1 | property |
| Property 3 | TS-13-P2 | property |
| Property 5 | TS-13-P3 | property |
| Property 6 | TS-13-P4 | property |
| Property 7 | TS-13-P5 | property |
| Property 8 | TS-13-E2, TS-13-E3 | unit |
