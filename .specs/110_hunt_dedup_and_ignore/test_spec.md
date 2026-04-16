# Test Specification: Hunt Scan Duplicate Detection and `af:ignore` Label

## Overview

Tests are organized into four sections: acceptance-criterion tests (one per
requirement criterion), property tests (one per correctness property from
design.md), edge-case tests, and integration smoke tests. All tests use the
existing pytest + Hypothesis framework.

Mock strategies:
- **Platform API** is always mocked (returns controlled `IssueResult` lists).
- **EmbeddingGenerator** is mocked in unit tests (returns controlled vectors)
  but uses real instances in property tests where vector math is under test.
- **DuckDB** is mocked in unit tests; smoke tests use an in-memory connection.

## Test Cases

### TS-110-1: Label constant defined

**Requirement:** 110-REQ-1.1
**Type:** unit
**Description:** Verify `LABEL_IGNORE` is defined with value `"af:ignore"`.

**Preconditions:**
- `platform.labels` module is importable.

**Input:**
- Import `LABEL_IGNORE` from `agent_fox.platform.labels`.

**Expected:**
- `LABEL_IGNORE == "af:ignore"`.

**Assertion pseudocode:**
```
from agent_fox.platform.labels import LABEL_IGNORE
ASSERT LABEL_IGNORE == "af:ignore"
```

### TS-110-2: Label color constant defined

**Requirement:** 110-REQ-1.2
**Type:** unit
**Description:** Verify `LABEL_IGNORE_COLOR` is a gray hex value.

**Preconditions:**
- `platform.labels` module is importable.

**Input:**
- Import `LABEL_IGNORE_COLOR` from `agent_fox.platform.labels`.

**Expected:**
- `LABEL_IGNORE_COLOR` is a 6-character hex string.

**Assertion pseudocode:**
```
from agent_fox.platform.labels import LABEL_IGNORE_COLOR
ASSERT len(LABEL_IGNORE_COLOR) == 6
ASSERT all(c in "0123456789abcdef" for c in LABEL_IGNORE_COLOR)
```

### TS-110-3: Label in REQUIRED_LABELS

**Requirement:** 110-REQ-1.3
**Type:** unit
**Description:** Verify `af:ignore` is in `REQUIRED_LABELS` with correct metadata.

**Preconditions:**
- `platform.labels` module is importable.

**Input:**
- Import `REQUIRED_LABELS` from `agent_fox.platform.labels`.

**Expected:**
- A `LabelSpec` with name `"af:ignore"` exists in `REQUIRED_LABELS`.
- Its description contains `"not-an-issue"` or similar wording.

**Assertion pseudocode:**
```
from agent_fox.platform.labels import REQUIRED_LABELS
specs = [s for s in REQUIRED_LABELS if s.name == "af:ignore"]
ASSERT len(specs) == 1
ASSERT "not-an-issue" in specs[0].description
```

### TS-110-4: Cosine similarity computation

**Requirement:** 110-REQ-2.4
**Type:** unit
**Description:** Verify `cosine_similarity()` returns correct value for known vectors.

**Preconditions:**
- `dedup` module is importable.

**Input:**
- `a = [1.0, 0.0, 0.0]`, `b = [1.0, 0.0, 0.0]` (identical)
- `a = [1.0, 0.0, 0.0]`, `b = [0.0, 1.0, 0.0]` (orthogonal)
- `a = [1.0, 0.0, 0.0]`, `b = [-1.0, 0.0, 0.0]` (opposite)

**Expected:**
- Identical: 1.0
- Orthogonal: 0.0
- Opposite: -1.0

**Assertion pseudocode:**
```
ASSERT cosine_similarity([1,0,0], [1,0,0]) == approx(1.0)
ASSERT cosine_similarity([1,0,0], [0,1,0]) == approx(0.0)
ASSERT cosine_similarity([1,0,0], [-1,0,0]) == approx(-1.0)
```

### TS-110-5: FindingGroup text representation

**Requirement:** 110-REQ-2.2
**Type:** unit
**Description:** Verify `build_finding_group_text()` produces the expected format.

**Preconditions:**
- A `FindingGroup` with category `"dead_code"`, title `"Unused function"`,
  affected_files `["src/a.py", "src/b.py"]`.

**Input:**
- The FindingGroup described above.

**Expected:**
- `"dead_code: Unused function\nFiles: src/a.py, src/b.py"`.

**Assertion pseudocode:**
```
group = FindingGroup(category="dead_code", title="Unused function",
                     affected_files=["src/a.py", "src/b.py"], ...)
result = build_finding_group_text(group)
ASSERT result == "dead_code: Unused function\nFiles: src/a.py, src/b.py"
```

### TS-110-6: Issue text representation

**Requirement:** 110-REQ-2.3
**Type:** unit
**Description:** Verify `build_issue_text()` produces the expected format.

**Preconditions:**
- An `IssueResult` with title `"Dead code: unused function"`,
  body `"Long body text..."` (600 chars).

**Input:**
- The IssueResult described above.

**Expected:**
- `"{title}\n{body[:500]}"` — body truncated to 500 chars.

**Assertion pseudocode:**
```
issue = IssueResult(number=1, title="Dead code", html_url="...",
                    body="x" * 600)
result = build_issue_text(issue)
ASSERT result == "Dead code\n" + "x" * 500
```

### TS-110-7: Enhanced filter_known_duplicates fetches all states

**Requirement:** 110-REQ-3.1
**Type:** integration
**Description:** Verify `filter_known_duplicates()` fetches issues with
`state="all"`.

**Preconditions:**
- Mock platform with `list_issues_by_label` that records call arguments.

**Input:**
- One FindingGroup with a fingerprint that matches a closed issue.

**Expected:**
- `list_issues_by_label` called with `state="all"`.
- The matching group is filtered out.

**Assertion pseudocode:**
```
platform = MockPlatform(issues=[closed_issue_with_matching_fp])
groups = [group_matching_closed_issue]
result = await filter_known_duplicates(groups, platform)
ASSERT platform.list_issues_by_label_called_with(state="all")
ASSERT len(result) == 0
```

### TS-110-8: Embedding similarity filters duplicates

**Requirement:** 110-REQ-3.3
**Type:** integration
**Description:** Verify groups with high embedding similarity to existing
issues are filtered out.

**Preconditions:**
- Mock platform with one open `af:hunt` issue.
- Mock embedder returning near-identical embeddings for the group and issue.

**Input:**
- One FindingGroup whose embedding is 0.95 similar to the existing issue.
- Similarity threshold = 0.85.

**Expected:**
- The group is filtered out.

**Assertion pseudocode:**
```
embedder = MockEmbedder(returns=[similar_vec_a, similar_vec_b])
platform = MockPlatform(issues=[existing_issue])
groups = [similar_group]
result = await filter_known_duplicates(groups, platform,
                                       similarity_threshold=0.85,
                                       embedder=embedder)
ASSERT len(result) == 0
```

### TS-110-9: Fingerprint checked before embedding

**Requirement:** 110-REQ-3.5
**Type:** integration
**Description:** Verify fingerprint match short-circuits embedding comparison.

**Preconditions:**
- Mock platform with one issue whose fingerprint matches the group.
- Mock embedder that records call count.

**Input:**
- One FindingGroup with matching fingerprint.

**Expected:**
- The group is filtered out.
- Embedder is NOT called for this group (short-circuit).

**Assertion pseudocode:**
```
embedder = MockEmbedder()
platform = MockPlatform(issues=[issue_with_matching_fp])
groups = [matching_fp_group]
result = await filter_known_duplicates(groups, platform, embedder=embedder)
ASSERT len(result) == 0
ASSERT embedder.embed_batch_call_count == 1  # only for issues, not for matched group
```

### TS-110-10: filter_ignored suppresses similar findings

**Requirement:** 110-REQ-4.3
**Type:** integration
**Description:** Verify `filter_ignored()` removes groups similar to
`af:ignore` issues.

**Preconditions:**
- Mock platform returning one `af:ignore` issue.
- Mock embedder returning vectors with 0.90 similarity.

**Input:**
- One FindingGroup similar to the ignored issue.
- Similarity threshold = 0.85.

**Expected:**
- The group is filtered out.

**Assertion pseudocode:**
```
embedder = MockEmbedder(returns=[group_vec, ignored_issue_vec])
platform = MockPlatform(ignore_issues=[ignored_issue])
groups = [similar_to_ignored]
result = await filter_ignored(groups, platform,
                              similarity_threshold=0.85,
                              embedder=embedder)
ASSERT len(result) == 0
```

### TS-110-11: filter_ignored passes dissimilar findings

**Requirement:** 110-REQ-4.3, 110-REQ-4.4
**Type:** unit
**Description:** Verify `filter_ignored()` passes groups dissimilar to
`af:ignore` issues.

**Preconditions:**
- Mock platform returning one `af:ignore` issue.
- Mock embedder returning vectors with 0.3 similarity.

**Input:**
- One FindingGroup dissimilar to the ignored issue.
- Similarity threshold = 0.85.

**Expected:**
- The group passes through.

**Assertion pseudocode:**
```
embedder = MockEmbedder(returns=[group_vec, dissimilar_issue_vec])
platform = MockPlatform(ignore_issues=[ignored_issue])
groups = [dissimilar_group]
result = await filter_ignored(groups, platform,
                              similarity_threshold=0.85,
                              embedder=embedder)
ASSERT len(result) == 1
```

### TS-110-12: Knowledge ingestion creates anti_pattern fact

**Requirement:** 110-REQ-5.2
**Type:** integration
**Description:** Verify `ingest_ignore_signals()` creates an `anti_pattern`
fact for a new `af:ignore` issue.

**Preconditions:**
- Mock platform returning one `af:ignore` issue without ingestion marker.
- In-memory DuckDB connection with knowledge tables.
- Real `EmbeddingGenerator` or mock embedder.

**Input:**
- One `af:ignore` issue with title `"Dead code: unused_fn"` and body
  containing `**Category:** dead_code`.

**Expected:**
- One fact created with `category="anti_pattern"`,
  `spec_name="nightshift:ignore"`, and `confidence=0.9`.

**Assertion pseudocode:**
```
count = await ingest_ignore_signals(platform, conn, embedder)
ASSERT count == 1
facts = query_facts(conn, category="anti_pattern",
                    spec_name="nightshift:ignore")
ASSERT len(facts) == 1
ASSERT "unused_fn" in facts[0].content
```

### TS-110-13: Knowledge ingestion appends marker

**Requirement:** 110-REQ-5.3
**Type:** integration
**Description:** Verify `ingest_ignore_signals()` appends the
`<!-- af:knowledge-ingested -->` marker to the issue body.

**Preconditions:**
- Mock platform that records `update_issue` calls.
- One `af:ignore` issue without marker.

**Input:**
- The issue described above.

**Expected:**
- `platform.update_issue` called with the issue number and a body ending
  with `<!-- af:knowledge-ingested -->`.

**Assertion pseudocode:**
```
await ingest_ignore_signals(platform, conn, embedder)
ASSERT platform.update_issue_called_with(
    issue_number=issue.number,
    body=issue.body + "\n<!-- af:knowledge-ingested -->"
)
```

### TS-110-14: Critic receives false positives in prompt

**Requirement:** 110-REQ-6.2
**Type:** unit
**Description:** Verify that when `false_positives` is non-empty, the critic
system prompt contains a `Known False Positives` section.

**Preconditions:**
- Mock AI backend.

**Input:**
- 3+ findings (to trigger AI critic path).
- `false_positives = ["Dead code in tests/ is acceptable"]`.

**Expected:**
- The system prompt sent to the AI contains `"Known False Positives"` and
  the false-positive text.

**Assertion pseudocode:**
```
# Capture the system prompt sent to the AI
result = await consolidate_findings(findings,
                                     false_positives=["Dead code in tests/"])
ASSERT "Known False Positives" in captured_system_prompt
ASSERT "Dead code in tests/" in captured_system_prompt
```

### TS-110-15: Critic prompt unchanged when no false positives

**Requirement:** 110-REQ-6.E2
**Type:** unit
**Description:** Verify critic prompt is not modified when `false_positives`
is empty or None.

**Preconditions:**
- Mock AI backend.

**Input:**
- 3+ findings.
- `false_positives = None`.

**Expected:**
- System prompt does NOT contain `"Known False Positives"`.

**Assertion pseudocode:**
```
result = await consolidate_findings(findings, false_positives=None)
ASSERT "Known False Positives" not in captured_system_prompt
```

### TS-110-16: Configuration field exists

**Requirement:** 110-REQ-7.1
**Type:** unit
**Description:** Verify `NightShiftConfig` has a `similarity_threshold` field
with default 0.85.

**Preconditions:**
- `core.config` module is importable.

**Input:**
- Instantiate `NightShiftConfig()` with defaults.

**Expected:**
- `config.similarity_threshold == 0.85`.

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.similarity_threshold == 0.85
```

### TS-110-17: Category extraction from issue body

**Requirement:** 110-REQ-5.4
**Type:** unit
**Description:** Verify category is extracted from the `**Category:**` field
in the issue body.

**Preconditions:**
- An issue body containing `**Category:** dead_code`.

**Input:**
- The issue body string.

**Expected:**
- Extracted category is `"dead_code"`.

**Assertion pseudocode:**
```
body = "## Title\n\n**Category:** dead_code\n\n**Severity:** minor"
category = extract_category_from_body(body)
ASSERT category == "dead_code"
```

## Property Test Cases

### TS-110-P1: Fingerprint Superset

**Property:** Property 1 from design.md
**Validates:** 110-REQ-3.2, 110-REQ-3.3
**Type:** property
**Description:** Enhanced filter returns a subset of fingerprint-only filter.

**For any:** list of FindingGroups and list of existing IssueResults with
fingerprints.
**Invariant:** Every group returned by the enhanced filter is also returned
by fingerprint-only filter.

**Assertion pseudocode:**
```
FOR ANY groups IN st.lists(finding_groups()), issues IN st.lists(issue_results()):
    fp_only = await filter_known_duplicates(groups, platform(issues), similarity_threshold=1.0)
    enhanced = await filter_known_duplicates(groups, platform(issues), similarity_threshold=0.85, embedder=embedder)
    ASSERT set(enhanced_titles) <= set(fp_only_titles)
```

### TS-110-P2: Cosine Similarity Symmetry

**Property:** Property 2 from design.md
**Validates:** 110-REQ-2.4
**Type:** property
**Description:** Cosine similarity is symmetric.

**For any:** two non-None float vectors `a` and `b` of equal length.
**Invariant:** `cosine_similarity(a, b) == cosine_similarity(b, a)`.

**Assertion pseudocode:**
```
FOR ANY a, b IN st.lists(st.floats(), min_size=1, max_size=384):
    ASSERT cosine_similarity(a, b) == approx(cosine_similarity(b, a))
```

### TS-110-P3: Cosine Similarity Bounds

**Property:** Property 3 from design.md
**Validates:** 110-REQ-2.4
**Type:** property
**Description:** Cosine similarity is bounded in [-1.0, 1.0].

**For any:** two non-None, non-zero float vectors `a` and `b`.
**Invariant:** `-1.0 <= cosine_similarity(a, b) <= 1.0`.

**Assertion pseudocode:**
```
FOR ANY a, b IN st.lists(st.floats(allow_nan=False, allow_infinity=False),
                         min_size=1, max_size=384):
    assume(any(x != 0 for x in a) and any(x != 0 for x in b))
    sim = cosine_similarity(a, b)
    ASSERT -1.0 <= sim <= 1.0
```

### TS-110-P4: Cosine Similarity Null Safety

**Property:** Property 4 from design.md
**Validates:** 110-REQ-2.4, 110-REQ-2.E1
**Type:** property
**Description:** Cosine similarity returns 0.0 for None or empty vectors.

**For any:** one valid vector and one None or empty vector.
**Invariant:** `cosine_similarity(valid, invalid) == 0.0`.

**Assertion pseudocode:**
```
FOR ANY a IN st.lists(st.floats(), min_size=1, max_size=384):
    ASSERT cosine_similarity(a, None) == 0.0
    ASSERT cosine_similarity(None, a) == 0.0
    ASSERT cosine_similarity(a, []) == 0.0
    ASSERT cosine_similarity([], a) == 0.0
```

### TS-110-P5: Ignore Filter Independence

**Property:** Property 5 from design.md
**Validates:** 110-REQ-4.1, 110-REQ-4.3
**Type:** property
**Description:** Groups dissimilar to all ignored issues pass through.

**For any:** FindingGroup and list of IssueResults where all pairwise
similarities are below threshold.
**Invariant:** All input groups are present in the output.

**Assertion pseudocode:**
```
FOR ANY groups IN st.lists(finding_groups()):
    embedder = MockEmbedder(always_returns_orthogonal_vectors)
    result = await filter_ignored(groups, empty_platform,
                                   similarity_threshold=0.85,
                                   embedder=embedder)
    ASSERT len(result) == len(groups)
```

### TS-110-P6: Ingestion Idempotency

**Property:** Property 6 from design.md
**Validates:** 110-REQ-5.1, 110-REQ-5.3, 110-REQ-5.E1
**Type:** property
**Description:** Double ingestion produces exactly one fact.

**For any:** single `af:ignore` issue.
**Invariant:** Two calls to `ingest_ignore_signals()` produce exactly one
fact, and the second call returns 0.

**Assertion pseudocode:**
```
FOR ANY issue IN ignore_issues():
    conn = in_memory_duckdb()
    count1 = await ingest_ignore_signals(platform([issue]), conn, embedder)
    count2 = await ingest_ignore_signals(platform([issue_with_marker]), conn, embedder)
    ASSERT count1 == 1
    ASSERT count2 == 0
    ASSERT count_facts(conn, spec_name="nightshift:ignore") == 1
```

### TS-110-P7: Threshold Monotonicity

**Property:** Property 7 from design.md
**Validates:** 110-REQ-7.1, 110-REQ-7.E1, 110-REQ-7.E2
**Type:** property
**Description:** Higher threshold = fewer groups suppressed.

**For any:** list of FindingGroups, fixed issues, and two thresholds
`t1 < t2`.
**Invariant:** `|filter(groups, t2)| >= |filter(groups, t1)|`.

**Assertion pseudocode:**
```
FOR ANY groups, t1 IN st.floats(0.0, 1.0), t2 IN st.floats(0.0, 1.0):
    assume(t1 < t2)
    r1 = await filter_known_duplicates(groups, platform, similarity_threshold=t1, embedder=embedder)
    r2 = await filter_known_duplicates(groups, platform, similarity_threshold=t2, embedder=embedder)
    ASSERT len(r2) >= len(r1)
```

### TS-110-P8: Fail-Open Guarantee

**Property:** Property 8 from design.md
**Validates:** 110-REQ-3.E1, 110-REQ-3.E2, 110-REQ-4.E2, 110-REQ-4.E3
**Type:** property
**Description:** On failure, all groups are returned unmodified.

**For any:** list of FindingGroups.
**Invariant:** When platform raises, `filter_known_duplicates()` returns
all input groups.

**Assertion pseudocode:**
```
FOR ANY groups IN st.lists(finding_groups()):
    platform = FailingPlatform()
    result = await filter_known_duplicates(groups, platform)
    ASSERT result == groups
```

### TS-110-P9: Critic Prompt Stability

**Property:** Property 9 from design.md
**Validates:** 110-REQ-6.E2
**Type:** property
**Description:** Empty false_positives produces identical behaviour to no
false_positives.

**For any:** list of findings.
**Invariant:** `consolidate_findings(f, false_positives=[])` and
`consolidate_findings(f, false_positives=None)` produce the same system
prompt.

**Assertion pseudocode:**
```
FOR ANY findings IN st.lists(findings_strategy()):
    prompt_none = capture_prompt(consolidate_findings(findings, false_positives=None))
    prompt_empty = capture_prompt(consolidate_findings(findings, false_positives=[]))
    ASSERT prompt_none == prompt_empty
```

## Edge Case Tests

### TS-110-E1: Embedding returns None

**Requirement:** 110-REQ-2.E1
**Type:** unit
**Description:** When embedder returns None, similarity is 0.0.

**Preconditions:**
- Mock embedder that returns None for all texts.

**Input:**
- One FindingGroup and one existing issue.

**Expected:**
- `cosine_similarity(None, valid_vector)` returns 0.0.
- Group is NOT filtered out.

**Assertion pseudocode:**
```
ASSERT cosine_similarity(None, [1.0, 0.0]) == 0.0
```

### TS-110-E2: EmbeddingGenerator unavailable

**Requirement:** 110-REQ-2.E2
**Type:** integration
**Description:** When embedder is None, fall back to fingerprint-only.

**Preconditions:**
- `embedder=None` passed to `filter_known_duplicates()`.
- One existing issue with non-matching fingerprint but semantically similar.

**Input:**
- Group that would be caught by similarity but not by fingerprint.

**Expected:**
- Group passes through (fingerprint-only mode).

**Assertion pseudocode:**
```
result = await filter_known_duplicates([group], platform, embedder=None)
ASSERT len(result) == 1  # not filtered, no embedder
```

### TS-110-E3: Platform API failure in filter_known_duplicates

**Requirement:** 110-REQ-3.E2
**Type:** integration
**Description:** When platform raises, all groups pass through.

**Preconditions:**
- Mock platform that raises `IntegrationError` on `list_issues_by_label`.

**Input:**
- Two FindingGroups.

**Expected:**
- Both groups returned unfiltered.

**Assertion pseudocode:**
```
platform = FailingPlatform()
result = await filter_known_duplicates([g1, g2], platform)
ASSERT len(result) == 2
```

### TS-110-E4: No af:ignore issues exist

**Requirement:** 110-REQ-4.E1
**Type:** unit
**Description:** When no `af:ignore` issues exist, all groups pass through.

**Preconditions:**
- Mock platform returning empty list for `af:ignore`.

**Input:**
- Two FindingGroups.

**Expected:**
- Both groups returned.

**Assertion pseudocode:**
```
platform = MockPlatform(ignore_issues=[])
result = await filter_ignored([g1, g2], platform, embedder=embedder)
ASSERT len(result) == 2
```

### TS-110-E5: Ingestion marker already present

**Requirement:** 110-REQ-5.E1
**Type:** unit
**Description:** Issue with existing marker is skipped.

**Preconditions:**
- One `af:ignore` issue with `<!-- af:knowledge-ingested -->` in body.

**Input:**
- The issue described above.

**Expected:**
- `ingest_ignore_signals()` returns 0.
- No facts created.

**Assertion pseudocode:**
```
issue = IssueResult(body="...<!-- af:knowledge-ingested -->")
count = await ingest_ignore_signals(platform([issue]), conn, embedder)
ASSERT count == 0
```

### TS-110-E6: Issue body update failure

**Requirement:** 110-REQ-5.E2
**Type:** integration
**Description:** When `update_issue` fails, fact is still created.

**Preconditions:**
- Mock platform where `update_issue` raises `IntegrationError`.
- One `af:ignore` issue without marker.

**Input:**
- The issue described above.

**Expected:**
- Fact is created in knowledge store.
- `ingest_ignore_signals()` returns 1.
- Warning is logged.

**Assertion pseudocode:**
```
platform = MockPlatform(update_issue_raises=True)
count = await ingest_ignore_signals(platform, conn, embedder)
ASSERT count == 1
ASSERT count_facts(conn) == 1
```

### TS-110-E7: Knowledge store unavailable

**Requirement:** 110-REQ-5.E3
**Type:** unit
**Description:** When DuckDB connection is None, ingestion is skipped.

**Preconditions:**
- `conn=None` or closed connection.

**Input:**
- One `af:ignore` issue.

**Expected:**
- `ingest_ignore_signals()` returns 0.
- Warning is logged.

**Assertion pseudocode:**
```
count = await ingest_ignore_signals(platform, conn=None, embedder=embedder)
ASSERT count == 0
```

### TS-110-E8: similarity_threshold = 0.0

**Requirement:** 110-REQ-7.E1
**Type:** unit
**Description:** Threshold 0.0 suppresses all groups with any embedding match.

**Preconditions:**
- Mock embedder returning orthogonal but non-zero vectors (similarity ~0.01).
- One existing issue.

**Input:**
- One FindingGroup with near-zero similarity to existing issue.
- `similarity_threshold=0.0`.

**Expected:**
- Group is filtered out (any non-zero similarity exceeds 0.0).

**Assertion pseudocode:**
```
result = await filter_known_duplicates([group], platform,
                                       similarity_threshold=0.0,
                                       embedder=embedder)
ASSERT len(result) == 0
```

### TS-110-E9: similarity_threshold = 1.0

**Requirement:** 110-REQ-7.E2
**Type:** unit
**Description:** Threshold 1.0 effectively disables similarity matching.

**Preconditions:**
- Mock embedder returning near-identical vectors (similarity 0.99).
- One existing issue.

**Input:**
- One FindingGroup very similar to existing issue.
- `similarity_threshold=1.0`.

**Expected:**
- Group passes through (0.99 < 1.0, not filtered).

**Assertion pseudocode:**
```
result = await filter_known_duplicates([group], platform,
                                       similarity_threshold=1.0,
                                       embedder=embedder)
ASSERT len(result) == 1
```

### TS-110-E10: Category not found in issue body

**Requirement:** 110-REQ-5.4
**Type:** unit
**Description:** When `**Category:**` field is missing from issue body,
category defaults to `"unknown"`.

**Preconditions:**
- An issue body without a `**Category:**` field.

**Input:**
- Issue body: `"Some text without category field"`.

**Expected:**
- Extracted category is `"unknown"`.

**Assertion pseudocode:**
```
category = extract_category_from_body("No category here")
ASSERT category == "unknown"
```

## Integration Smoke Tests

### TS-110-SMOKE-1: Hunt scan with enhanced dedup (Path 1)

**Execution Path:** Path 1 from design.md
**Description:** Full hunt scan pipeline from findings to issue creation,
exercising fingerprint dedup, embedding similarity, and ignore filter.

**Setup:**
- Mock platform with:
  - One open `af:hunt` issue with fingerprint matching group A.
  - One closed `af:hunt` issue with embedding similar to group B.
  - One `af:ignore` issue with embedding similar to group C.
- Real `consolidate_findings` (mechanical path, <3 findings).
- Mock embedder returning controlled vectors.
- 4 FindingGroups: A (fingerprint dup), B (similarity dup), C (ignored),
  D (novel).

**Trigger:** Call `NightShiftEngine._run_hunt_scan()` or equivalent pipeline.

**Expected side effects:**
- Only group D results in `platform.create_issue()` being called.
- Groups A, B, C are filtered out at their respective gates.

**Must NOT satisfy with:** Mocking `filter_known_duplicates` or
`filter_ignored` — the real functions must run.

**Assertion pseudocode:**
```
platform = MockPlatform(
    hunt_issues=[open_fp_match, closed_similar],
    ignore_issues=[ignored_similar],
)
embedder = MockEmbedder(vectors=controlled_vectors)
# Run pipeline: consolidate → filter_known_duplicates → filter_ignored → create
groups = [group_A, group_B, group_C, group_D]
after_dedup = await filter_known_duplicates(groups, platform,
                                            similarity_threshold=0.85,
                                            embedder=embedder)
after_ignore = await filter_ignored(after_dedup, platform,
                                     similarity_threshold=0.85,
                                     embedder=embedder)
created = await create_issues_from_groups(after_ignore, platform)
ASSERT len(created) == 1
ASSERT platform.create_issue.call_count == 1
```

### TS-110-SMOKE-2: af:ignore knowledge ingestion (Path 2)

**Execution Path:** Path 2 from design.md
**Description:** Ingestion of `af:ignore` issues into the knowledge store.

**Setup:**
- Mock platform with two `af:ignore` issues: one without marker, one with.
- In-memory DuckDB with knowledge tables initialized.
- Real `EmbeddingGenerator` or mock embedder.

**Trigger:** Call `ingest_ignore_signals(platform, conn, embedder)`.

**Expected side effects:**
- One fact created in DuckDB (the un-ingested issue).
- `platform.update_issue` called once (for the un-ingested issue).
- Returns 1.

**Must NOT satisfy with:** Mocking `_write_fact` or `_is_ingested`.

**Assertion pseudocode:**
```
platform = MockPlatform(ignore_issues=[
    issue_without_marker,
    issue_with_marker,
])
conn = in_memory_duckdb_with_tables()
count = await ingest_ignore_signals(platform, conn, embedder)
ASSERT count == 1
ASSERT platform.update_issue.call_count == 1
facts = query_facts(conn, category="anti_pattern")
ASSERT len(facts) == 1
```

### TS-110-SMOKE-3: AI critic with false-positive awareness (Path 3)

**Execution Path:** Path 3 from design.md
**Description:** AI critic receives false positives in its system prompt.

**Setup:**
- 3+ findings (to trigger AI path).
- Mock AI backend that captures the system prompt.
- `false_positives = ["Dead code in tests/ is acceptable"]`.

**Trigger:** Call `consolidate_findings(findings, false_positives=fps)`.

**Expected side effects:**
- System prompt contains `"Known False Positives"` section.
- System prompt contains the false-positive text.
- Returns FindingGroups (from AI or mechanical fallback).

**Must NOT satisfy with:** Mocking `_run_critic` — the real prompt
construction must execute.

**Assertion pseudocode:**
```
captured_prompts = []
with mock_ai_backend(capture_system_prompt=captured_prompts):
    result = await consolidate_findings(
        findings_3_plus,
        false_positives=["Dead code in tests/ is acceptable"],
    )
ASSERT "Known False Positives" in captured_prompts[0]
ASSERT "Dead code in tests/" in captured_prompts[0]
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 110-REQ-1.1 | TS-110-1 | unit |
| 110-REQ-1.2 | TS-110-2 | unit |
| 110-REQ-1.3 | TS-110-3 | unit |
| 110-REQ-1.4 | TS-110-3 | unit |
| 110-REQ-1.E1 | TS-110-3 | unit |
| 110-REQ-2.1 | TS-110-8 | integration |
| 110-REQ-2.2 | TS-110-5 | unit |
| 110-REQ-2.3 | TS-110-6 | unit |
| 110-REQ-2.4 | TS-110-4 | unit |
| 110-REQ-2.E1 | TS-110-E1 | unit |
| 110-REQ-2.E2 | TS-110-E2 | integration |
| 110-REQ-3.1 | TS-110-7 | integration |
| 110-REQ-3.2 | TS-110-7 | integration |
| 110-REQ-3.3 | TS-110-8 | integration |
| 110-REQ-3.4 | TS-110-8 | integration |
| 110-REQ-3.5 | TS-110-9 | integration |
| 110-REQ-3.E1 | TS-110-E2 | integration |
| 110-REQ-3.E2 | TS-110-E3 | integration |
| 110-REQ-4.1 | TS-110-10 | integration |
| 110-REQ-4.2 | TS-110-10 | integration |
| 110-REQ-4.3 | TS-110-10, TS-110-11 | integration |
| 110-REQ-4.4 | TS-110-11 | unit |
| 110-REQ-4.E1 | TS-110-E4 | unit |
| 110-REQ-4.E2 | TS-110-E3 | integration |
| 110-REQ-4.E3 | TS-110-E2 | integration |
| 110-REQ-5.1 | TS-110-12 | integration |
| 110-REQ-5.2 | TS-110-12 | integration |
| 110-REQ-5.3 | TS-110-13 | integration |
| 110-REQ-5.4 | TS-110-17 | unit |
| 110-REQ-5.E1 | TS-110-E5 | unit |
| 110-REQ-5.E2 | TS-110-E6 | integration |
| 110-REQ-5.E3 | TS-110-E7 | unit |
| 110-REQ-6.1 | TS-110-14 | unit |
| 110-REQ-6.2 | TS-110-14 | unit |
| 110-REQ-6.3 | TS-110-SMOKE-3 | integration |
| 110-REQ-6.E1 | TS-110-15 | unit |
| 110-REQ-6.E2 | TS-110-15 | unit |
| 110-REQ-7.1 | TS-110-16 | unit |
| 110-REQ-7.2 | TS-110-8 | integration |
| 110-REQ-7.E1 | TS-110-E8 | unit |
| 110-REQ-7.E2 | TS-110-E9 | unit |
| Property 1 | TS-110-P1 | property |
| Property 2 | TS-110-P2 | property |
| Property 3 | TS-110-P3 | property |
| Property 4 | TS-110-P4 | property |
| Property 5 | TS-110-P5 | property |
| Property 6 | TS-110-P6 | property |
| Property 7 | TS-110-P7 | property |
| Property 8 | TS-110-P8 | property |
| Property 9 | TS-110-P9 | property |
