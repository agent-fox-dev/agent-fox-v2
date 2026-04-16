# Test Specification: Rich Memory Rendering (Spec 111)

## Overview

Tests verify that `render_summary()` produces enriched markdown with causal
chains, entity links, supersession history, relative age, sorted ordering,
and graceful degradation. All tests mock or use in-memory DuckDB -- no live
database required.

## Unit Tests

File: `tests/unit/knowledge/test_rich_rendering.py`

### TS-111-1: Summary header with fact count and date

**Requirement:** 111-REQ-1.1, 111-REQ-1.2

**Setup:** Create 3 facts with known `created_at` timestamps. Most recent is
`2026-04-10T12:00:00`.

**Action:** Call `render_summary()` with mocked connection.

**Assert:**
- Output contains `# Agent-Fox Memory` as first line.
- Second non-empty line contains `_3 facts | last updated: 2026-04-10_`.

---

### TS-111-2: Summary header with unparseable dates

**Requirement:** 111-REQ-1.E1

**Setup:** Create 2 facts with `created_at = ""` (empty string).

**Action:** Call `render_summary()`.

**Assert:** Summary line is `_2 facts_` (no "last updated" portion).

---

### TS-111-3: Relative age -- days format

**Requirement:** 111-REQ-2.1, 111-REQ-2.2, 111-REQ-2.3

**Setup:** Fact with `created_at` = 14 days before `now`.

**Action:** Call `_format_relative_age(created_at, now)`.

**Assert:** Returns `"14d ago"`.

---

### TS-111-4: Relative age -- months format

**Requirement:** 111-REQ-2.2

**Setup:** Fact with `created_at` = 90 days before `now`.

**Action:** Call `_format_relative_age(created_at, now)`.

**Assert:** Returns `"3mo ago"`.

---

### TS-111-5: Relative age -- years format

**Requirement:** 111-REQ-2.2

**Setup:** Fact with `created_at` = 400 days before `now`.

**Action:** Call `_format_relative_age(created_at, now)`.

**Assert:** Returns `"1y ago"`.

---

### TS-111-6: Relative age -- boundary at 60 days

**Requirement:** 111-REQ-2.2

**Setup:** Two facts: one at 59 days ago, one at 60 days ago.

**Action:** Call `_format_relative_age()` for each.

**Assert:** 59 days returns `"59d ago"`, 60 days returns `"2mo ago"`.

---

### TS-111-7: Relative age -- missing created_at

**Requirement:** 111-REQ-2.E1

**Setup:** Fact with `created_at = ""`.

**Action:** Call `_format_relative_age("", now)`.

**Assert:** Returns `None`.

---

### TS-111-8: Metadata parenthetical includes age

**Requirement:** 111-REQ-2.3

**Setup:** Fact with known spec_name, confidence, created_at (14 days ago).

**Action:** Call `_render_fact()` with empty enrichments.

**Assert:** Output contains `_(spec: my_spec, confidence: 0.90, 14d ago)_`.

---

### TS-111-9: Metadata parenthetical without age

**Requirement:** 111-REQ-2.E1

**Setup:** Fact with `created_at = ""`.

**Action:** Call `_render_fact()` with empty enrichments.

**Assert:** Output contains `_(spec: my_spec, confidence: 0.90)_` (no age).

---

### TS-111-10: Fact ordering by confidence then date

**Requirement:** 111-REQ-3.1

**Setup:** 3 facts in same category:
- Fact A: confidence=0.90, created_at=2026-04-01
- Fact B: confidence=0.90, created_at=2026-04-10
- Fact C: confidence=0.60, created_at=2026-04-15

**Action:** Call `render_summary()`.

**Assert:** Facts appear in order B, A, C (confidence desc, then date desc).

---

### TS-111-11: Fact ordering stability

**Requirement:** 111-REQ-3.E1

**Setup:** 3 facts with identical confidence and identical `created_at`.

**Action:** Call `render_summary()` twice.

**Assert:** Both outputs produce the same fact order.

---

### TS-111-12: Entity path sub-bullets

**Requirement:** 111-REQ-4.1

**Setup:** Fact with 2 associated FILE entities in enrichments.

**Action:** Call `_render_fact()` with enrichments containing entity paths.

**Assert:**
- Output contains `  - files: path/to/file1.py, path/to/file2.py` as a
  sub-bullet.

---

### TS-111-13: Entity path overflow

**Requirement:** 111-REQ-4.2

**Setup:** Fact with 5 associated FILE entities in enrichments.

**Action:** Call `_render_fact()` with enrichments.

**Assert:**
- Sub-bullet shows 3 paths followed by `+2 more`.

---

### TS-111-14: No entity paths

**Requirement:** 111-REQ-4.E1

**Setup:** Fact with no entity associations.

**Action:** Call `_render_fact()` with empty entity enrichments.

**Assert:** No `files:` sub-bullet in output.

---

### TS-111-15: Cause sub-bullets

**Requirement:** 111-REQ-5.1

**Setup:** Fact with 2 causes in enrichments, each with content of 80 chars.

**Action:** Call `_render_fact()`.

**Assert:**
- Output contains 2 lines matching `  - cause: {truncated to 60 chars}...`.

---

### TS-111-16: Effect sub-bullets

**Requirement:** 111-REQ-5.2

**Setup:** Fact with 2 effects in enrichments.

**Action:** Call `_render_fact()`.

**Assert:**
- Output contains 2 lines matching `  - effect: {content}`.

---

### TS-111-17: Cause/effect limit enforcement

**Requirement:** 111-REQ-5.1, 111-REQ-5.2

**Setup:** Fact with 5 causes and 5 effects in enrichments.

**Action:** Call `_render_fact()`.

**Assert:**
- Exactly 2 `cause:` sub-bullets and 2 `effect:` sub-bullets.

---

### TS-111-18: No causal links

**Requirement:** 111-REQ-5.E1

**Setup:** Fact with no causal links.

**Action:** Call `_render_fact()` with empty causal enrichments.

**Assert:** No `cause:` or `effect:` sub-bullets.

---

### TS-111-19: Supersession sub-bullet

**Requirement:** 111-REQ-6.1

**Setup:** Fact that superseded an older fact. Enrichments contain old content
of 100 characters.

**Action:** Call `_render_fact()`.

**Assert:**
- Output contains `  - replaces: {truncated to 80 chars}...`.

---

### TS-111-20: No supersession

**Requirement:** 111-REQ-6.E1

**Setup:** Fact that did not supersede anything.

**Action:** Call `_render_fact()` with empty supersession enrichments.

**Assert:** No `replaces:` sub-bullet.

---

### TS-111-21: Enrichment loading -- batch queries

**Requirement:** 111-REQ-7.1, 111-REQ-7.2

**Setup:** In-memory DuckDB with schema, 3 facts, seed fact_causes,
fact_entities, entity_graph, and one superseded fact.

**Action:** Call `load_enrichments(conn, fact_ids)`.

**Assert:**
- Returned `Enrichments` has correct causes, effects, entity_paths, and
  superseded content for each fact.

---

### TS-111-22: Enrichment query failure isolation

**Requirement:** 111-REQ-7.E1

**Setup:** Mock DuckDB connection where the causes query raises an exception
but other queries succeed.

**Action:** Call `load_enrichments(conn, fact_ids)`.

**Assert:**
- `enrichments.causes` is empty dict.
- `enrichments.effects`, `enrichments.entity_paths`, `enrichments.superseded`
  contain valid data.

---

### TS-111-23: Enrichment with None connection

**Requirement:** 111-REQ-7.E2

**Action:** Call `load_enrichments(conn=None, fact_ids)`.

**Assert:** Returns `Enrichments` with all fields as empty dicts.

---

### TS-111-24: Content truncation correctness

**Requirement:** 111-REQ-5.1, 111-REQ-6.1

**Setup:** Cause content of exactly 60 chars, effect content of 61 chars,
superseded content of exactly 80 chars, superseded content of 81 chars.

**Action:** Call `_render_fact()`.

**Assert:**
- 60-char cause rendered without ellipsis.
- 61-char effect truncated to 60 chars + ellipsis.
- 80-char superseded rendered without ellipsis.
- 81-char superseded truncated to 80 chars + ellipsis.

---

### TS-111-25: Full render with all enrichments

**Requirement:** All

**Setup:** 2 facts across 2 categories. Fact 1 has causes, effects, entities,
and superseded content. Fact 2 has no enrichments.

**Action:** Call `render_summary()`.

**Assert:**
- Output is valid markdown.
- Fact 1 has sub-bullets for cause, effect, files, replaces.
- Fact 2 has no sub-bullets.
- Summary header is present.

## Property Tests

File: `tests/property/knowledge/test_rich_rendering_props.py`

### TS-111-P1: Age format correctness

**Requirement:** 111-REQ-2.2

**Strategy:** Generate random `created_at` timestamps between 0 and 3650 days
ago. Verify `_format_relative_age()` output matches `\d+(d|mo|y) ago` and
uses the correct unit for the day range.

---

### TS-111-P2: Sort stability

**Requirement:** 111-REQ-3.1, 111-REQ-3.E1

**Strategy:** Generate lists of facts with random confidence and created_at
values. Sort with the production sort key. Verify:
- Higher confidence always precedes lower confidence.
- Among equal confidence, newer created_at precedes older.
- Sorting the same list twice yields identical results.

---

### TS-111-P3: Sub-bullet bounds

**Requirement:** 111-REQ-4.2, 111-REQ-5.1, 111-REQ-5.2

**Strategy:** Generate enrichments with random counts of causes (0-10),
effects (0-10), and entity paths (0-20). Render each fact. Verify:
- At most `_MAX_CAUSES` cause lines.
- At most `_MAX_EFFECTS` effect lines.
- At most `_MAX_ENTITY_PATHS` paths shown (overflow indicator when exceeded).

---

### TS-111-P4: Enrichment independence

**Requirement:** 111-REQ-7.E1

**Strategy:** For each of the 4 enrichment query types, simulate a failure
(raise Exception) while others succeed. Verify that the successful queries
still return data and rendering completes without error.

---

### TS-111-P5: Graceful degradation

**Requirement:** 111-REQ-7.E2

**Strategy:** Generate random fact lists. Call `render_summary(conn=None)`.
Verify output contains all facts, correct category headers, correct sort
order, and no sub-bullets.

---

### TS-111-P6: Truncation boundary

**Requirement:** 111-REQ-5.1, 111-REQ-6.1

**Strategy:** Generate strings of lengths 1 to 200. Apply truncation at 60
and 80 character limits. Verify:
- Strings at or under the limit are unchanged.
- Strings over the limit are exactly `limit` chars + ellipsis.

## Integration Smoke Tests

File: `tests/integration/knowledge/test_rich_rendering_smoke.py`

### TS-111-SMOKE-1: End-to-end rich rendering

**Requirement:** All

**Setup:** In-memory DuckDB with full schema (via `run_migrations()`). Insert
5 facts across 3 categories, 2 causal links, 3 entity entries, and 1
superseded fact.

**Action:** Call `render_summary(conn, tmp_path / "memory.md")`.

**Assert:**
- Output file exists and is valid markdown.
- Summary header shows `_5 facts | last updated: ..._`.
- Facts appear in correct sort order within each category.
- At least one fact has `cause:` sub-bullet.
- At least one fact has `files:` sub-bullet.
- At least one fact has `replaces:` sub-bullet.
- All facts have age indicators in metadata.

---

### TS-111-SMOKE-2: Rendering with empty enrichment tables

**Requirement:** 111-REQ-7.E1

**Setup:** In-memory DuckDB with full schema. Insert 3 facts but no
fact_causes, fact_entities, or superseded facts.

**Action:** Call `render_summary(conn, tmp_path / "memory.md")`.

**Assert:**
- Output file exists with all 3 facts rendered.
- No sub-bullets present (no enrichment data).
- Summary header and sort order are correct.

## Coverage Matrix

| Test ID | Requirements Covered |
|---------|---------------------|
| TS-111-1 | 111-REQ-1.1, 111-REQ-1.2 |
| TS-111-2 | 111-REQ-1.E1 |
| TS-111-3 | 111-REQ-2.1, 111-REQ-2.2, 111-REQ-2.3 |
| TS-111-4 | 111-REQ-2.2 |
| TS-111-5 | 111-REQ-2.2 |
| TS-111-6 | 111-REQ-2.2 |
| TS-111-7 | 111-REQ-2.E1 |
| TS-111-8 | 111-REQ-2.3 |
| TS-111-9 | 111-REQ-2.E1 |
| TS-111-10 | 111-REQ-3.1 |
| TS-111-11 | 111-REQ-3.E1 |
| TS-111-12 | 111-REQ-4.1 |
| TS-111-13 | 111-REQ-4.2 |
| TS-111-14 | 111-REQ-4.E1 |
| TS-111-15 | 111-REQ-5.1 |
| TS-111-16 | 111-REQ-5.2 |
| TS-111-17 | 111-REQ-5.1, 111-REQ-5.2 |
| TS-111-18 | 111-REQ-5.E1 |
| TS-111-19 | 111-REQ-6.1 |
| TS-111-20 | 111-REQ-6.E1 |
| TS-111-21 | 111-REQ-7.1, 111-REQ-7.2 |
| TS-111-22 | 111-REQ-7.E1 |
| TS-111-23 | 111-REQ-7.E2 |
| TS-111-24 | 111-REQ-5.1, 111-REQ-6.1 |
| TS-111-25 | All |
| TS-111-P1 | 111-REQ-2.2 |
| TS-111-P2 | 111-REQ-3.1, 111-REQ-3.E1 |
| TS-111-P3 | 111-REQ-4.2, 111-REQ-5.1, 111-REQ-5.2 |
| TS-111-P4 | 111-REQ-7.E1 |
| TS-111-P5 | 111-REQ-7.E2 |
| TS-111-P6 | 111-REQ-5.1, 111-REQ-6.1 |
| TS-111-SMOKE-1 | All |
| TS-111-SMOKE-2 | 111-REQ-7.E1 |
