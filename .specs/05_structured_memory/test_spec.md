# Test Specification: Structured Memory

## Overview

Tests for the structured memory system: data types, fact extraction, JSONL
storage, context selection, knowledge base compaction, and human-readable
summary generation. Tests map to requirements in `requirements.md` and
correctness properties in `design.md`.

## Test Cases

### TS-05-1: Fact creation with all fields

**Requirement:** 05-REQ-3.2
**Type:** unit
**Description:** Verify a Fact can be created with all required fields and
serialized to a dictionary.

**Preconditions:** None.

**Input:**
- Create a Fact with known values for all fields including supersedes.

**Expected:**
- All fields are accessible and match the input values.
- `_fact_to_dict()` produces a dictionary with all keys present.

**Assertion pseudocode:**
```
fact = Fact(id="uuid-1", content="test", category="gotcha",
            spec_name="spec_01", keywords=["k1"], confidence="high",
            created_at="2026-03-01T00:00:00+00:00", supersedes=None)
ASSERT fact.id == "uuid-1"
ASSERT fact.category == "gotcha"
d = _fact_to_dict(fact)
ASSERT "id" IN d AND "content" IN d AND "category" IN d
```

---

### TS-05-2: Category enum has six values

**Requirement:** 05-REQ-2.1
**Type:** unit
**Description:** Verify the Category enum defines exactly six categories.

**Preconditions:** None.

**Input:**
- List all values in the Category enum.

**Expected:**
- Exactly six values: gotcha, pattern, decision, convention, anti_pattern,
  fragile_area.

**Assertion pseudocode:**
```
values = [c.value for c in Category]
ASSERT len(values) == 6
ASSERT set(values) == {"gotcha", "pattern", "decision", "convention",
                        "anti_pattern", "fragile_area"}
```

---

### TS-05-3: Extraction returns facts from valid LLM response

**Requirement:** 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3
**Type:** unit
**Description:** Verify extraction parses a valid JSON LLM response into Fact
objects with UUIDs and timestamps.

**Preconditions:**
- Mock LLM client returns a JSON array with two fact objects.

**Input:**
- Call `extract_facts(transcript="...", spec_name="02_planning_engine")` with
  mocked LLM.

**Expected:**
- Returns 2 Fact objects.
- Each has a valid UUID, the correct spec_name, a valid category, and a
  non-empty created_at.

**Assertion pseudocode:**
```
mock_llm_response = '[{"content":"fact 1","category":"pattern",...}, ...]'
facts = await extract_facts("transcript", "02_planning_engine")
ASSERT len(facts) == 2
ASSERT all(f.spec_name == "02_planning_engine" for f in facts)
ASSERT all(f.id is not None for f in facts)
ASSERT all(f.created_at is not None for f in facts)
```

---

### TS-05-4: Store append and load round-trip

**Requirement:** 05-REQ-3.1, 05-REQ-3.3
**Type:** unit
**Description:** Verify facts can be appended and then loaded back
identically.

**Preconditions:**
- A temporary directory with no existing memory file.

**Input:**
- Append 3 facts to the JSONL file.
- Load all facts from the same file.

**Expected:**
- 3 facts loaded.
- Content, category, and all fields match the originals.

**Assertion pseudocode:**
```
append_facts([fact_a, fact_b, fact_c], path=tmp_path / "memory.jsonl")
loaded = load_all_facts(path=tmp_path / "memory.jsonl")
ASSERT len(loaded) == 3
ASSERT loaded[0].id == fact_a.id
ASSERT loaded[0].content == fact_a.content
```

---

### TS-05-5: Store append creates file if missing

**Requirement:** 05-REQ-3.E1
**Type:** unit
**Description:** Verify appending to a nonexistent file creates it.

**Preconditions:**
- Path points to a nonexistent file in a temporary directory.

**Input:**
- Append 1 fact to the nonexistent path.

**Expected:**
- The file is created.
- The fact can be loaded back.

**Assertion pseudocode:**
```
path = tmp_path / "new_memory.jsonl"
ASSERT NOT path.exists()
append_facts([fact_a], path=path)
ASSERT path.exists()
loaded = load_all_facts(path=path)
ASSERT len(loaded) == 1
```

---

### TS-05-6: Filter selects by spec name

**Requirement:** 05-REQ-4.1
**Type:** unit
**Description:** Verify context selection returns facts matching the spec name.

**Preconditions:**
- A list of facts with mixed spec names.

**Input:**
- `select_relevant_facts(all_facts, spec_name="spec_02", task_keywords=["test"])`

**Expected:**
- Only facts with spec_name="spec_02" or keyword matches are returned.
- Facts from "spec_02" are ranked higher.

**Assertion pseudocode:**
```
facts = [fact_spec01, fact_spec02a, fact_spec02b, fact_spec03]
result = select_relevant_facts(facts, "spec_02", ["test"])
ASSERT all(f.spec_name == "spec_02" or
           any(k in f.keywords for k in ["test"]) for f in result)
```

---

### TS-05-7: Filter selects by keyword overlap

**Requirement:** 05-REQ-4.1, 05-REQ-4.2
**Type:** unit
**Description:** Verify facts with more keyword matches score higher.

**Preconditions:**
- Facts with varying keyword overlap: 0, 1, 3 matches.

**Input:**
- `select_relevant_facts(all_facts, spec_name="spec_01", task_keywords=["pytest", "config", "toml"])`

**Expected:**
- Fact with 3 keyword matches ranks highest.
- Fact with 0 matches is not returned (unless same spec).

**Assertion pseudocode:**
```
fact_3_matches = Fact(..., keywords=["pytest", "config", "toml"], spec_name="other")
fact_1_match = Fact(..., keywords=["pytest"], spec_name="other")
fact_0_matches = Fact(..., keywords=["unrelated"], spec_name="other")
result = select_relevant_facts([fact_0_matches, fact_1_match, fact_3_matches],
                                "spec_01", ["pytest", "config", "toml"])
ASSERT result[0].id == fact_3_matches.id  # highest score
```

---

### TS-05-8: Filter enforces budget of 50

**Requirement:** 05-REQ-4.3
**Type:** unit
**Description:** Verify at most 50 facts are returned even when more match.

**Preconditions:**
- A list of 100 facts all matching the spec name.

**Input:**
- `select_relevant_facts(100_facts, spec_name="spec_01", task_keywords=["test"])`

**Expected:**
- Exactly 50 facts returned.

**Assertion pseudocode:**
```
many_facts = [make_fact(spec_name="spec_01") for _ in range(100)]
result = select_relevant_facts(many_facts, "spec_01", ["test"])
ASSERT len(result) == 50
```

---

### TS-05-9: Compaction removes duplicates by content hash

**Requirement:** 05-REQ-5.1
**Type:** unit
**Description:** Verify compaction removes facts with identical content,
keeping the earliest.

**Preconditions:**
- A JSONL file with two facts having the same content but different UUIDs
  and timestamps.

**Input:**
- Run `compact(path)`.

**Expected:**
- Only one fact survives.
- The surviving fact is the one with the earlier created_at.

**Assertion pseudocode:**
```
early = Fact(..., content="same", created_at="2026-01-01T00:00:00+00:00")
late = Fact(..., content="same", created_at="2026-03-01T00:00:00+00:00")
write_facts([late, early], path)
original, surviving = compact(path)
ASSERT original == 2
ASSERT surviving == 1
facts = load_all_facts(path)
ASSERT facts[0].created_at == "2026-01-01T00:00:00+00:00"
```

---

### TS-05-10: Compaction resolves supersession chains

**Requirement:** 05-REQ-5.2
**Type:** unit
**Description:** Verify compaction removes all facts in a supersession chain
except the terminal fact.

**Preconditions:**
- Three facts: A, B (supersedes A), C (supersedes B).

**Input:**
- Run `compact(path)`.

**Expected:**
- Only fact C survives.

**Assertion pseudocode:**
```
a = Fact(id="a-id", ..., supersedes=None)
b = Fact(id="b-id", ..., supersedes="a-id")
c = Fact(id="c-id", ..., supersedes="b-id")
write_facts([a, b, c], path)
original, surviving = compact(path)
ASSERT surviving == 1
facts = load_all_facts(path)
ASSERT facts[0].id == "c-id"
```

---

### TS-05-11: Render generates markdown organized by category

**Requirement:** 05-REQ-6.1, 05-REQ-6.2
**Type:** unit
**Description:** Verify the rendered summary has sections for each category
with fact content and attribution.

**Preconditions:**
- A JSONL file with facts in multiple categories.

**Input:**
- Call `render_summary(memory_path, output_path)`.

**Expected:**
- Output file contains section headings for each populated category.
- Each fact entry includes content, spec name, and confidence.

**Assertion pseudocode:**
```
render_summary(memory_path=path, output_path=out_path)
content = out_path.read_text()
ASSERT "## Gotchas" IN content
ASSERT "## Patterns" IN content
ASSERT "spec: 01_core_foundation" IN content
ASSERT "confidence: high" IN content
```

---

### TS-05-12: Load facts by spec name

**Requirement:** 05-REQ-4.1
**Type:** unit
**Description:** Verify `load_facts_by_spec` filters correctly.

**Preconditions:**
- A JSONL file with facts from three different specs.

**Input:**
- `load_facts_by_spec("spec_02", path)`.

**Expected:**
- Only facts with spec_name="spec_02" are returned.

**Assertion pseudocode:**
```
append_facts([fact_spec01, fact_spec02, fact_spec03], path)
result = load_facts_by_spec("spec_02", path)
ASSERT len(result) == 1
ASSERT result[0].spec_name == "spec_02"
```

## Property Test Cases

### TS-05-P1: Context budget enforcement

**Property:** Property 1 from design.md
**Validates:** 05-REQ-4.3
**Type:** property
**Description:** The context selection function never returns more than the
budget.

**For any:** list of facts (0 to 200), any spec_name, any keyword list,
any budget (1 to 100)
**Invariant:** `len(select_relevant_facts(facts, spec, kw, budget)) <= budget`

**Assertion pseudocode:**
```
FOR ANY facts IN lists(facts, max_size=200),
        spec IN text(),
        keywords IN lists(text()),
        budget IN integers(1, 100):
    result = select_relevant_facts(facts, spec, keywords, budget)
    ASSERT len(result) <= budget
```

---

### TS-05-P2: Compaction idempotency

**Property:** Property 2 from design.md
**Validates:** 05-REQ-5.E2
**Type:** property
**Description:** Running compaction twice produces the same result as once.

**For any:** list of facts with possible duplicates and supersession chains
**Invariant:** `compact(); compact()` yields the same file content as
`compact()` alone.

**Assertion pseudocode:**
```
FOR ANY facts IN lists(facts, min_size=1, max_size=50):
    write_facts(facts, path)
    compact(path)
    content_after_first = path.read_text()
    compact(path)
    content_after_second = path.read_text()
    ASSERT content_after_first == content_after_second
```

---

### TS-05-P3: Fact serialization round-trip

**Property:** Property 4 from design.md
**Validates:** 05-REQ-3.2
**Type:** property
**Description:** Any valid Fact survives a serialize-deserialize round-trip.

**For any:** valid Fact object
**Invariant:** `_dict_to_fact(_fact_to_dict(fact))` equals the original fact
in all fields.

**Assertion pseudocode:**
```
FOR ANY fact IN valid_facts():
    d = _fact_to_dict(fact)
    restored = _dict_to_fact(d)
    ASSERT restored.id == fact.id
    ASSERT restored.content == fact.content
    ASSERT restored.category == fact.category
    ASSERT restored.keywords == fact.keywords
    ASSERT restored.supersedes == fact.supersedes
```

---

### TS-05-P4: Deduplication determinism

**Property:** Property 5 from design.md
**Validates:** 05-REQ-5.1
**Type:** property
**Description:** Deduplication always keeps the earliest instance regardless
of input order.

**For any:** list of facts where some share the same content
**Invariant:** The surviving fact for each content hash has the minimum
created_at among all facts with that hash.

**Assertion pseudocode:**
```
FOR ANY facts IN lists_with_duplicates():
    result = _deduplicate_by_content(facts)
    for r in result:
        hash = _content_hash(r.content)
        all_with_hash = [f for f in facts if _content_hash(f.content) == hash]
        earliest = min(all_with_hash, key=lambda f: f.created_at)
        ASSERT r.created_at == earliest.created_at
```

---

### TS-05-P5: Category completeness

**Property:** Property 3 from design.md
**Validates:** 05-REQ-2.1
**Type:** property
**Description:** Every Category enum value has a corresponding CATEGORY_TITLES
entry.

**For any:** category in Category enum
**Invariant:** `category.value in CATEGORY_TITLES`

**Assertion pseudocode:**
```
FOR ANY cat IN Category:
    ASSERT cat.value IN CATEGORY_TITLES
```

---

### TS-05-P6: Supersession chain resolution

**Property:** Property 6 from design.md
**Validates:** 05-REQ-5.2
**Type:** property
**Description:** In any supersession chain, only the terminal fact survives.

**For any:** chain of N facts where fact[i+1] supersedes fact[i]
**Invariant:** After `_resolve_supersession()`, only the last fact in the
chain remains.

**Assertion pseudocode:**
```
FOR ANY chain_length IN integers(2, 10):
    chain = build_supersession_chain(chain_length)
    result = _resolve_supersession(chain)
    ASSERT len(result) == 1
    ASSERT result[0].id == chain[-1].id
```

## Edge Case Tests

### TS-05-E1: Extraction with invalid LLM JSON

**Requirement:** 05-REQ-1.E1
**Type:** unit
**Description:** Verify extraction handles malformed LLM response gracefully.

**Preconditions:**
- Mock LLM returns `"not valid json {{"`.

**Input:**
- `extract_facts(transcript="...", spec_name="spec_01")` with mocked LLM.

**Expected:**
- Returns an empty list.
- A warning is logged.

**Assertion pseudocode:**
```
mock_llm_response = "not valid json {{"
facts = await extract_facts("transcript", "spec_01")
ASSERT facts == []
ASSERT warning_logged("invalid JSON")
```

---

### TS-05-E2: Extraction with zero facts

**Requirement:** 05-REQ-1.E2
**Type:** unit
**Description:** Verify extraction handles an empty array response.

**Preconditions:**
- Mock LLM returns `"[]"`.

**Input:**
- `extract_facts(transcript="...", spec_name="spec_01")` with mocked LLM.

**Expected:**
- Returns an empty list.
- No error is raised.

**Assertion pseudocode:**
```
mock_llm_response = "[]"
facts = await extract_facts("transcript", "spec_01")
ASSERT facts == []
```

---

### TS-05-E3: Unknown category defaults to gotcha

**Requirement:** 05-REQ-2.2
**Type:** unit
**Description:** Verify an unknown category in LLM output is replaced with
gotcha.

**Preconditions:**
- Mock LLM returns a fact with `category: "unknown_cat"`.

**Input:**
- `_parse_extraction_response(response, spec_name="spec_01")`.

**Expected:**
- The fact's category is set to "gotcha".
- A warning is logged.

**Assertion pseudocode:**
```
response = '[{"content":"test","category":"unknown_cat","confidence":"high","keywords":["k"]}]'
facts = _parse_extraction_response(response, "spec_01")
ASSERT facts[0].category == "gotcha"
ASSERT warning_logged("unknown category")
```

---

### TS-05-E4: Load from nonexistent memory file

**Requirement:** 05-REQ-4.E2
**Type:** unit
**Description:** Verify loading from a nonexistent file returns empty list.

**Preconditions:**
- Path points to a nonexistent file.

**Input:**
- `load_all_facts(path=Path("/nonexistent/memory.jsonl"))`.

**Expected:**
- Returns an empty list.
- No error is raised.

**Assertion pseudocode:**
```
result = load_all_facts(path=Path("/tmp/nonexistent.jsonl"))
ASSERT result == []
```

---

### TS-05-E5: Filter with no matching facts

**Requirement:** 05-REQ-4.E1
**Type:** unit
**Description:** Verify filter returns empty list when nothing matches.

**Preconditions:**
- A list of facts with no matching spec name or keywords.

**Input:**
- `select_relevant_facts(facts, "unrelated_spec", ["no_match"])`.

**Expected:**
- Returns an empty list.

**Assertion pseudocode:**
```
facts = [Fact(..., spec_name="spec_01", keywords=["pytest"])]
result = select_relevant_facts(facts, "unrelated_spec", ["no_match"])
ASSERT result == []
```

---

### TS-05-E6: Compaction on empty knowledge base

**Requirement:** 05-REQ-5.E1
**Type:** unit
**Description:** Verify compaction handles a missing or empty knowledge base.

**Preconditions:**
- Path points to a nonexistent file or an empty file.

**Input:**
- `compact(path)`.

**Expected:**
- Returns (0, 0).
- No error is raised.

**Assertion pseudocode:**
```
original, surviving = compact(path=Path("/tmp/nonexistent.jsonl"))
ASSERT original == 0
ASSERT surviving == 0
```

---

### TS-05-E7: Render creates docs directory

**Requirement:** 05-REQ-6.E1
**Type:** unit
**Description:** Verify render creates the output directory if missing.

**Preconditions:**
- Output path is in a nonexistent directory within tmp_path.

**Input:**
- `render_summary(memory_path, output_path=tmp_path / "docs" / "memory.md")`.

**Expected:**
- The `docs/` directory is created.
- The file is written.

**Assertion pseudocode:**
```
out = tmp_path / "docs" / "memory.md"
ASSERT NOT out.parent.exists()
render_summary(memory_path=path, output_path=out)
ASSERT out.exists()
```

---

### TS-05-E8: Render with empty knowledge base

**Requirement:** 05-REQ-6.E2
**Type:** unit
**Description:** Verify render produces a "no facts" summary when the
knowledge base is empty.

**Preconditions:**
- Memory JSONL file does not exist or is empty.

**Input:**
- `render_summary(memory_path, output_path)`.

**Expected:**
- Output file contains "No facts have been recorded yet."

**Assertion pseudocode:**
```
render_summary(memory_path=empty_path, output_path=out_path)
content = out_path.read_text()
ASSERT "No facts have been recorded yet" IN content
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3 | TS-05-3 | unit |
| 05-REQ-1.E1 | TS-05-E1 | unit |
| 05-REQ-1.E2 | TS-05-E2 | unit |
| 05-REQ-2.1 | TS-05-2 | unit |
| 05-REQ-2.2 | TS-05-E3 | unit |
| 05-REQ-3.1, 05-REQ-3.3 | TS-05-4 | unit |
| 05-REQ-3.2 | TS-05-1 | unit |
| 05-REQ-3.E1 | TS-05-5 | unit |
| 05-REQ-3.E2 | (verified by store error handling) | unit |
| 05-REQ-4.1 | TS-05-6, TS-05-12 | unit |
| 05-REQ-4.2 | TS-05-7 | unit |
| 05-REQ-4.3 | TS-05-8 | unit |
| 05-REQ-4.E1 | TS-05-E5 | unit |
| 05-REQ-4.E2 | TS-05-E4 | unit |
| 05-REQ-5.1 | TS-05-9 | unit |
| 05-REQ-5.2 | TS-05-10 | unit |
| 05-REQ-5.E1 | TS-05-E6 | unit |
| 05-REQ-5.E2 | TS-05-P2 | property |
| 05-REQ-6.1, 05-REQ-6.2 | TS-05-11 | unit |
| 05-REQ-6.3 | (verified by sync barrier integration) | integration |
| 05-REQ-6.E1 | TS-05-E7 | unit |
| 05-REQ-6.E2 | TS-05-E8 | unit |
| Property 1 | TS-05-P1 | property |
| Property 2 | TS-05-P2 | property |
| Property 3 | TS-05-P5 | property |
| Property 4 | TS-05-P3 | property |
| Property 5 | TS-05-P4 | property |
| Property 6 | TS-05-P6 | property |
