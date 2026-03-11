# Test Specification: Confidence Normalization

## Overview

This test specification defines test contracts for normalizing confidence
values to `float [0.0, 1.0]` across the memory, knowledge, and analyzer
subsystems. Tests are organized by requirement area: confidence parsing,
DuckDB migration, JSONL compatibility, knowledge queries, analyzer, and
rendering.

## Test Cases

### TS-37-1: Parse String Confidence to Float

**Requirement:** 37-REQ-1.2
**Type:** unit
**Description:** Verify canonical string-to-float mapping.

**Preconditions:**
- `parse_confidence()` function is available from `memory/types.py`.

**Input:**
- `"high"`, `"medium"`, `"low"`

**Expected:**
- `0.9`, `0.6`, `0.3` respectively

**Assertion pseudocode:**
```
ASSERT parse_confidence("high") == 0.9
ASSERT parse_confidence("medium") == 0.6
ASSERT parse_confidence("low") == 0.3
```

### TS-37-2: Parse Numeric Confidence

**Requirement:** 37-REQ-1.3
**Type:** unit
**Description:** Verify numeric confidence values are accepted and clamped.

**Preconditions:**
- `parse_confidence()` function is available.

**Input:**
- `0.75`, `0.0`, `1.0`, `0.5`

**Expected:**
- Same values returned unchanged.

**Assertion pseudocode:**
```
ASSERT parse_confidence(0.75) == 0.75
ASSERT parse_confidence(0.0) == 0.0
ASSERT parse_confidence(1.0) == 1.0
```

### TS-37-3: Fact Dataclass Uses Float

**Requirement:** 37-REQ-1.4
**Type:** unit
**Description:** Verify the Fact dataclass accepts float confidence and defaults to 0.6.

**Preconditions:**
- `Fact` dataclass is imported from `memory/types.py`.

**Input:**
- Create a Fact with `confidence=0.85`.
- Create a Fact using default confidence.

**Expected:**
- First fact: `confidence == 0.85`
- Default fact: `confidence == 0.6`

**Assertion pseudocode:**
```
fact = Fact(..., confidence=0.85)
ASSERT fact.confidence == 0.85
ASSERT isinstance(fact.confidence, float)
```

### TS-37-4: Extraction Stores Float Confidence

**Requirement:** 37-REQ-1.1
**Type:** unit
**Description:** Verify fact extraction produces float confidence from LLM output.

**Preconditions:**
- Mock LLM returns JSON with `"confidence": "high"`.

**Input:**
- Session transcript text.

**Expected:**
- Extracted fact has `confidence == 0.9` (float).

**Assertion pseudocode:**
```
facts = extract_facts(transcript, model="mock")
ASSERT isinstance(facts[0].confidence, float)
ASSERT facts[0].confidence == 0.9
```

### TS-37-5: DuckDB Migration Converts TEXT to FLOAT

**Requirement:** 37-REQ-2.1
**Type:** integration
**Description:** Verify the migration converts the confidence column type.

**Preconditions:**
- DuckDB test database with `memory_facts` table using TEXT confidence.
- Rows with values `"high"`, `"medium"`, `"low"`.

**Input:**
- Apply migration v6.

**Expected:**
- Column type is FLOAT after migration.
- Values converted: `0.9`, `0.6`, `0.3`.

**Assertion pseudocode:**
```
apply_pending_migrations(conn)
rows = conn.execute("SELECT confidence FROM memory_facts").fetchall()
FOR row IN rows:
    ASSERT isinstance(row[0], float)
ASSERT set(row[0] for row in rows) == {0.9, 0.6, 0.3}
```

### TS-37-6: Migration Preserves Row Count

**Requirement:** 37-REQ-2.3
**Type:** integration
**Description:** Verify no rows are lost during migration.

**Preconditions:**
- DuckDB test database with N rows in `memory_facts`.

**Input:**
- Apply migration v6.

**Expected:**
- Row count is unchanged after migration.

**Assertion pseudocode:**
```
count_before = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
apply_pending_migrations(conn)
count_after = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
ASSERT count_before == count_after
```

### TS-37-7: JSONL Loads String Confidence

**Requirement:** 37-REQ-3.1, 37-REQ-3.2
**Type:** unit
**Description:** Verify JSONL loader converts old string confidence to float.

**Preconditions:**
- JSONL file with `"confidence": "high"`.

**Input:**
- Load facts from JSONL.

**Expected:**
- Loaded fact has `confidence == 0.9` (float).

**Assertion pseudocode:**
```
facts = load_all_facts(jsonl_path)
ASSERT facts[0].confidence == 0.9
ASSERT isinstance(facts[0].confidence, float)
```

### TS-37-8: JSONL Writes Float Confidence

**Requirement:** 37-REQ-3.3
**Type:** unit
**Description:** Verify JSONL writer outputs float confidence.

**Preconditions:**
- Fact with `confidence=0.85`.

**Input:**
- Write fact to JSONL, read raw JSON.

**Expected:**
- JSON field `"confidence"` is `0.85` (number, not string).

**Assertion pseudocode:**
```
append_facts([fact], jsonl_path)
raw = read_jsonl_line(jsonl_path)
ASSERT raw["confidence"] == 0.85
ASSERT isinstance(raw["confidence"], float)
```

### TS-37-9: OracleAnswer Uses Float Confidence

**Requirement:** 37-REQ-4.1, 37-REQ-4.2
**Type:** unit
**Description:** Verify OracleAnswer confidence is a float computed from results.

**Preconditions:**
- `_determine_confidence()` function available.

**Input:**
- 3 search results with similarity > 0.7.

**Expected:**
- Returns a float (high confidence, e.g., >= 0.8).

**Assertion pseudocode:**
```
conf = _determine_confidence(results_3_high_sim)
ASSERT isinstance(conf, float)
ASSERT conf >= 0.8
```

### TS-37-10: Pattern Uses Float Confidence

**Requirement:** 37-REQ-4.3, 37-REQ-4.4
**Type:** unit
**Description:** Verify Pattern confidence is a float based on occurrence count.

**Preconditions:**
- `_assign_confidence()` function available.

**Input:**
- Occurrence counts: 2, 3, 5, 10.

**Expected:**
- `0.4`, `0.7`, `0.9`, `0.9` respectively.

**Assertion pseudocode:**
```
ASSERT _assign_confidence(2) == 0.4
ASSERT _assign_confidence(3) == 0.7
ASSERT _assign_confidence(5) == 0.9
ASSERT _assign_confidence(10) == 0.9
```

### TS-37-11: Improvement Uses Float Confidence

**Requirement:** 37-REQ-5.1, 37-REQ-5.2
**Type:** unit
**Description:** Verify Improvement dataclass uses float confidence.

**Preconditions:**
- `Improvement` dataclass from `fix/analyzer.py`.

**Input:**
- Create Improvement with `confidence=0.85`.

**Expected:**
- `confidence` field is float.

**Assertion pseudocode:**
```
imp = Improvement(..., confidence=0.85)
ASSERT isinstance(imp.confidence, float)
```

### TS-37-12: Low-Confidence Filter Uses Threshold

**Requirement:** 37-REQ-5.3
**Type:** unit
**Description:** Verify improvement filtering uses `< 0.5` threshold.

**Preconditions:**
- List of Improvements with confidences `[0.3, 0.5, 0.7, 0.9]`.

**Input:**
- Apply confidence filter.

**Expected:**
- Only items with confidence >= 0.5 remain (3 items).

**Assertion pseudocode:**
```
filtered = filter_improvements(improvements)
ASSERT len(filtered) == 3
ASSERT all(i.confidence >= 0.5 for i in filtered)
```

### TS-37-13: Fact Rendering Shows Float

**Requirement:** 37-REQ-6.1
**Type:** unit
**Description:** Verify rendered fact output shows two-decimal confidence.

**Preconditions:**
- Fact with `confidence=0.9`.

**Input:**
- Render the fact.

**Expected:**
- Output contains `confidence: 0.90`.

**Assertion pseudocode:**
```
rendered = render_fact(fact)
ASSERT "confidence: 0.90" in rendered
```

## Edge Case Tests

### TS-37-E1: Unknown Confidence String

**Requirement:** 37-REQ-1.E1
**Type:** unit
**Description:** Verify unknown string defaults to 0.6 with warning.

**Preconditions:**
- `parse_confidence()` function available.

**Input:**
- `"very_high"`, `"uncertain"`, `""`

**Expected:**
- Returns `0.6` for all.
- Warning logged.

**Assertion pseudocode:**
```
ASSERT parse_confidence("very_high") == 0.6
ASSERT parse_confidence("uncertain") == 0.6
ASSERT parse_confidence("") == 0.6
```

### TS-37-E2: Out-of-Range Numeric Clamping

**Requirement:** 37-REQ-1.E2
**Type:** unit
**Description:** Verify values outside [0.0, 1.0] are clamped.

**Preconditions:**
- `parse_confidence()` function available.

**Input:**
- `-0.5`, `1.5`, `100`, `-1`

**Expected:**
- `0.0`, `1.0`, `1.0`, `0.0`

**Assertion pseudocode:**
```
ASSERT parse_confidence(-0.5) == 0.0
ASSERT parse_confidence(1.5) == 1.0
ASSERT parse_confidence(100) == 1.0
ASSERT parse_confidence(-1) == 0.0
```

### TS-37-E3: NULL Confidence in Migration

**Requirement:** 37-REQ-2.E1
**Type:** integration
**Description:** Verify NULL confidence rows get default 0.6 during migration.

**Preconditions:**
- DuckDB test database with a row where `confidence IS NULL`.

**Input:**
- Apply migration v6.

**Expected:**
- Row's confidence is `0.6` after migration.

**Assertion pseudocode:**
```
conn.execute("INSERT INTO memory_facts (..., confidence) VALUES (..., NULL)")
apply_pending_migrations(conn)
row = conn.execute("SELECT confidence FROM memory_facts WHERE id = ?", [id]).fetchone()
ASSERT row[0] == 0.6
```

### TS-37-E4: None Input to parse_confidence

**Requirement:** 37-REQ-1.E1
**Type:** unit
**Description:** Verify None input defaults to 0.6.

**Preconditions:**
- `parse_confidence()` function available.

**Input:**
- `None`

**Expected:**
- Returns `0.6`.

**Assertion pseudocode:**
```
ASSERT parse_confidence(None) == 0.6
```

## Property Test Cases

### TS-37-P1: Confidence Always in Range

**Property:** Property 1 from design.md
**Validates:** 37-REQ-1.1, 37-REQ-1.3, 37-REQ-1.E1, 37-REQ-1.E2
**Type:** property
**Description:** parse_confidence always returns a value in [0.0, 1.0].

**For any:** float, int, string, or None value
**Invariant:** `0.0 <= parse_confidence(value) <= 1.0`

**Assertion pseudocode:**
```
FOR ANY value IN (floats | ints | text(max_size=20) | none()):
    result = parse_confidence(value)
    ASSERT 0.0 <= result <= 1.0
    ASSERT isinstance(result, float)
```

### TS-37-P2: Canonical Mapping Is Deterministic

**Property:** Property 2 from design.md
**Validates:** 37-REQ-1.2, 37-REQ-2.2, 37-REQ-3.2
**Type:** property
**Description:** Canonical strings always map to the same float.

**For any:** string in {"high", "medium", "low"}
**Invariant:** `parse_confidence(s) == CONFIDENCE_MAP[s]`

**Assertion pseudocode:**
```
FOR ANY s IN sampled_from(["high", "medium", "low"]):
    ASSERT parse_confidence(s) == CONFIDENCE_MAP[s]
```

### TS-37-P3: JSONL Round-Trip Preserves Confidence

**Property:** Property 4 from design.md
**Validates:** 37-REQ-3.1, 37-REQ-3.3
**Type:** property
**Description:** Writing and reading a fact preserves its confidence.

**For any:** float confidence in [0.0, 1.0]
**Invariant:** After write → read round-trip, confidence is unchanged.

**Assertion pseudocode:**
```
FOR ANY conf IN floats(min_value=0.0, max_value=1.0):
    fact = make_fact(confidence=conf)
    append_facts([fact], path)
    loaded = load_all_facts(path)[-1]
    ASSERT abs(loaded.confidence - conf) < 1e-9
```

### TS-37-P4: Migration Preserves Row Count

**Property:** Property 3 from design.md
**Validates:** 37-REQ-2.1, 37-REQ-2.3
**Type:** property
**Description:** Migration never changes the number of rows.

**For any:** set of N rows with mixed confidence values
**Invariant:** Row count before == row count after migration.

**Assertion pseudocode:**
```
FOR ANY rows IN lists(confidence_values, min_size=0, max_size=50):
    insert_rows(conn, rows)
    count_before = count_rows(conn)
    apply_migration(conn)
    count_after = count_rows(conn)
    ASSERT count_before == count_after
```

### TS-37-P5: Backward-Compatible String Loading

**Property:** Property 5 from design.md
**Validates:** 37-REQ-3.1, 37-REQ-3.2
**Type:** property
**Description:** Old-format JSONL with string confidence loads correctly.

**For any:** string confidence from {"high", "medium", "low"}
**Invariant:** Loaded confidence equals canonical float mapping.

**Assertion pseudocode:**
```
FOR ANY s IN sampled_from(["high", "medium", "low"]):
    write_jsonl_with_string_confidence(path, s)
    fact = load_all_facts(path)[-1]
    ASSERT fact.confidence == CONFIDENCE_MAP[s]
```

### TS-37-P6: Threshold Filter Correctness

**Property:** Property 6 from design.md
**Validates:** 37-REQ-5.3
**Type:** property
**Description:** Filtering at threshold 0.5 partitions correctly.

**For any:** list of Improvements with random float confidences
**Invariant:** All retained items have confidence >= 0.5, all excluded have < 0.5.

**Assertion pseudocode:**
```
FOR ANY improvements IN lists(improvement_strategy):
    filtered = filter_improvements(improvements)
    ASSERT all(i.confidence >= 0.5 for i in filtered)
    excluded = set(improvements) - set(filtered)
    ASSERT all(i.confidence < 0.5 for i in excluded)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 37-REQ-1.1 | TS-37-4 | unit |
| 37-REQ-1.2 | TS-37-1 | unit |
| 37-REQ-1.3 | TS-37-2 | unit |
| 37-REQ-1.4 | TS-37-3 | unit |
| 37-REQ-1.E1 | TS-37-E1, TS-37-E4 | unit |
| 37-REQ-1.E2 | TS-37-E2 | unit |
| 37-REQ-2.1 | TS-37-5 | integration |
| 37-REQ-2.2 | TS-37-5 | integration |
| 37-REQ-2.3 | TS-37-6 | integration |
| 37-REQ-2.E1 | TS-37-E3 | integration |
| 37-REQ-3.1 | TS-37-7 | unit |
| 37-REQ-3.2 | TS-37-7 | unit |
| 37-REQ-3.3 | TS-37-8 | unit |
| 37-REQ-4.1 | TS-37-9 | unit |
| 37-REQ-4.2 | TS-37-9 | unit |
| 37-REQ-4.3 | TS-37-10 | unit |
| 37-REQ-4.4 | TS-37-10 | unit |
| 37-REQ-5.1 | TS-37-11 | unit |
| 37-REQ-5.2 | TS-37-11 | unit |
| 37-REQ-5.3 | TS-37-12 | unit |
| 37-REQ-6.1 | TS-37-13 | unit |
| Property 1 | TS-37-P1 | property |
| Property 2 | TS-37-P2 | property |
| Property 3 | TS-37-P4 | property |
| Property 4 | TS-37-P3 | property |
| Property 5 | TS-37-P5 | property |
| Property 6 | TS-37-P6 | property |
