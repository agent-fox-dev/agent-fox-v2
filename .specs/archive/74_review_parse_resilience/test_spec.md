# Test Specification: Review Parse Resilience

## Overview

Tests validate three areas: (1) fuzzy/tolerant JSON extraction and field
normalization, (2) format retry logic, and (3) partial convergence handling.
Each test maps to a requirement from requirements.md and/or a correctness
property from design.md.

## Test Cases

### TS-74-1: Skeptic Prompt Contains Strict Format Instructions

**Requirement:** 74-REQ-1.1
**Type:** unit
**Description:** Verify the skeptic template contains the strict format
enforcement text.

**Preconditions:**
- Skeptic prompt template file exists at expected path.

**Input:**
- Read `agent_fox/_templates/prompts/skeptic.md` content.

**Expected:**
- Content contains instruction to output bare JSON without markdown fences.
- Content contains instruction to use exact field names from schema.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/skeptic.md")
ASSERT "no markdown fences" in content (case-insensitive)
ASSERT "exact field names" in content OR "exactly the field names" in content
```

### TS-74-2: Verifier Prompt Contains Strict Format Instructions

**Requirement:** 74-REQ-1.2
**Type:** unit
**Description:** Verify the verifier template contains the strict format
enforcement text.

**Preconditions:**
- Verifier prompt template file exists.

**Input:**
- Read `agent_fox/_templates/prompts/verifier.md` content.

**Expected:**
- Same format enforcement presence as TS-74-1.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/verifier.md")
ASSERT "no markdown fences" in content (case-insensitive)
```

### TS-74-3: Auditor Prompt Contains Strict Format Instructions

**Requirement:** 74-REQ-1.3
**Type:** unit
**Description:** Verify the auditor template contains the strict format text.

**Preconditions:**
- Auditor prompt template file exists.

**Input:**
- Read `agent_fox/_templates/prompts/auditor.md` content.

**Expected:**
- Same format enforcement presence as TS-74-1.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/auditor.md")
ASSERT "no markdown fences" in content (case-insensitive)
```

### TS-74-4: Oracle Prompt Contains Strict Format Instructions

**Requirement:** 74-REQ-1.4
**Type:** unit
**Description:** Verify the oracle template contains the strict format text.

**Preconditions:**
- Oracle prompt template file exists.

**Input:**
- Read `agent_fox/_templates/prompts/oracle.md` content.

**Expected:**
- Same format enforcement presence as TS-74-1.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/oracle.md")
ASSERT "no markdown fences" in content (case-insensitive)
```

### TS-74-5: Prompts Include Critical Reminders Section

**Requirement:** 74-REQ-1.5
**Type:** unit
**Description:** Verify each review archetype template ends with a
CRITICAL REMINDERS section repeating format constraints.

**Preconditions:**
- All four prompt template files exist.

**Input:**
- Read all four template files.

**Expected:**
- Each contains a section titled "CRITICAL" or "CRITICAL REMINDERS"
  after the output format section.

**Assertion pseudocode:**
```
FOR template IN [skeptic, verifier, auditor, oracle]:
    content = read_file(template)
    ASSERT "CRITICAL" in content
    # The CRITICAL section appears after OUTPUT FORMAT
    output_idx = content.index("OUTPUT FORMAT")
    critical_idx = content.index("CRITICAL")
    ASSERT critical_idx > output_idx
```

### TS-74-6: Prompts Include Negative Example

**Requirement:** 74-REQ-1.6
**Type:** unit
**Description:** Verify each review archetype template includes a negative
example of incorrect formatting.

**Preconditions:**
- All four prompt template files exist.

**Input:**
- Read all four template files.

**Expected:**
- Each contains text indicating an incorrect/wrong example (e.g., "WRONG",
  "INCORRECT", "DO NOT").

**Assertion pseudocode:**
```
FOR template IN [skeptic, verifier, auditor, oracle]:
    content = read_file(template)
    ASSERT any(marker in content for marker in ["WRONG", "INCORRECT", "DO NOT do this"])
```

### TS-74-7: Case-Insensitive Wrapper Key Resolution

**Requirement:** 74-REQ-2.1
**Type:** unit
**Description:** Verify `_resolve_wrapper_key` matches keys regardless of case.

**Preconditions:**
- `_resolve_wrapper_key` function exists in `review_parser.py`.

**Input:**
- `data = {"Findings": [{"severity": "major", "description": "test"}]}`
- `canonical_key = "findings"`

**Expected:**
- Returns `"Findings"` (the actual key from the dict).

**Assertion pseudocode:**
```
result = _resolve_wrapper_key({"Findings": [...]}, "findings")
ASSERT result == "Findings"
```

### TS-74-8: Singular Variant Wrapper Key Resolution

**Requirement:** 74-REQ-2.2
**Type:** unit
**Description:** Verify `_resolve_wrapper_key` accepts singular variants.

**Preconditions:**
- `_resolve_wrapper_key` function exists.
- `WRAPPER_KEY_VARIANTS` map is populated.

**Input:**
- `data = {"finding": [{"severity": "minor", "description": "x"}]}`
- `canonical_key = "findings"`

**Expected:**
- Returns `"finding"`.

**Assertion pseudocode:**
```
result = _resolve_wrapper_key({"finding": [...]}, "findings")
ASSERT result == "finding"
```

### TS-74-9: Unwrap Items Uses Fuzzy Key Matching

**Requirement:** 74-REQ-2.3
**Type:** unit
**Description:** Verify `_unwrap_items` extracts findings from variant keys.

**Preconditions:**
- `_unwrap_items` uses `_resolve_wrapper_key` internally.

**Input:**
- Response text containing `{"Finding": [{"severity": "major", "description": "test"}]}`

**Expected:**
- Returns list with one item dict.

**Assertion pseudocode:**
```
response = '{"Finding": [{"severity": "major", "description": "test"}]}'
items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
ASSERT len(items) == 1
ASSERT items[0]["severity"] == "major"
```

### TS-74-10: Field-Level Case Normalization

**Requirement:** 74-REQ-2.4
**Type:** unit
**Description:** Verify typed parsers normalize field keys to lowercase.

**Preconditions:**
- `parse_review_findings` accepts items with non-standard key casing.

**Input:**
- `[{"Severity": "critical", "Description": "test issue"}]`

**Expected:**
- Returns one `ReviewFinding` with `severity="critical"` and
  `description="test issue"`.

**Assertion pseudocode:**
```
items = [{"Severity": "critical", "Description": "test issue"}]
findings = parse_review_findings(items, "spec", "1", "sess1")
ASSERT len(findings) == 1
ASSERT findings[0].severity == "critical"
ASSERT findings[0].description == "test issue"
```

### TS-74-11: Markdown Fence Extraction Preserved

**Requirement:** 74-REQ-2.5
**Type:** unit
**Description:** Verify JSON inside markdown fences with surrounding prose
is still extracted correctly.

**Preconditions:**
- `extract_json_array` handles fenced JSON.

**Input:**
- Text with prose, then ` ```json\n[{"severity": "major"}]\n``` `, then
  more prose.

**Expected:**
- Returns `[{"severity": "major"}]`.

**Assertion pseudocode:**
```
text = "Here is my analysis:\n```json\n[{\"severity\": \"major\"}]\n```\nDone."
result = extract_json_array(text)
ASSERT result == [{"severity": "major"}]
```

### TS-74-12: Single Object Treated as Finding

**Requirement:** 74-REQ-2.E1
**Type:** unit
**Description:** Verify a bare JSON object with required fields is treated
as a single finding.

**Preconditions:**
- `_unwrap_items` handles single-object fallback.

**Input:**
- Response text: `{"severity": "minor", "description": "nit"}`

**Expected:**
- Returns list with one item.

**Assertion pseudocode:**
```
response = '{"severity": "minor", "description": "nit"}'
items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
ASSERT len(items) == 1
```

### TS-74-13: Multiple JSON Blocks Merged

**Requirement:** 74-REQ-2.E2
**Type:** unit
**Description:** Verify findings from multiple JSON blocks in the same
output are merged.

**Preconditions:**
- `_unwrap_items` iterates all extracted JSON blocks.

**Input:**
- Response with two separate JSON objects, each containing a `findings`
  array with one item.

**Expected:**
- Returns list with two items (merged from both blocks).

**Assertion pseudocode:**
```
response = '{"findings": [{"severity": "major", "description": "a"}]}\nMore text.\n{"findings": [{"severity": "minor", "description": "b"}]}'
items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
ASSERT len(items) == 2
```

### TS-74-14: Format Retry Triggered on Parse Failure

**Requirement:** 74-REQ-3.1
**Type:** integration
**Description:** Verify that when extraction fails, a format retry is
attempted.

**Preconditions:**
- Mock backend that returns unparseable text on first call, valid JSON on
  second call.

**Input:**
- Transcript with no valid JSON.
- Session handle that supports appending messages.

**Expected:**
- Retry is attempted (backend receives retry message).
- Findings from retry response are persisted.

**Assertion pseudocode:**
```
backend = MockBackend(responses=["no json here", '{"findings": [...]}'])
persist_review_findings(transcript="no json here", ..., backend=backend)
ASSERT backend.call_count == 2  # initial parse + retry
ASSERT findings_persisted == True
```

### TS-74-15: Retry Message Contains Schema

**Requirement:** 74-REQ-3.2
**Type:** unit
**Description:** Verify the retry prompt includes the expected JSON schema
reference and parse failure explanation.

**Preconditions:**
- `FORMAT_RETRY_PROMPT` constant or retry message builder exists.

**Input:**
- None (inspect the constant/builder).

**Expected:**
- Message contains "could not be parsed" or equivalent.
- Message contains "JSON" and format instructions.

**Assertion pseudocode:**
```
ASSERT "could not be parsed" in FORMAT_RETRY_PROMPT
ASSERT "JSON" in FORMAT_RETRY_PROMPT
```

### TS-74-16: Maximum One Retry

**Requirement:** 74-REQ-3.3
**Type:** unit
**Description:** Verify that at most 1 format retry is attempted.

**Preconditions:**
- Mock backend that always returns unparseable output.

**Input:**
- Transcript with no valid JSON.

**Expected:**
- Backend is called at most once for retry (total 2 parse attempts).

**Assertion pseudocode:**
```
backend = MockBackend(responses=["bad", "still bad"])
persist_review_findings(..., backend=backend)
ASSERT backend.retry_count <= 1
```

### TS-74-17: Successful Retry Suppresses Parse Failure Event

**Requirement:** 74-REQ-3.4
**Type:** integration
**Description:** Verify no REVIEW_PARSE_FAILURE event is emitted when
retry succeeds.

**Preconditions:**
- Mock backend: first response unparseable, second response valid JSON.
- Mock sink to capture audit events.

**Input:**
- Unparseable transcript, valid retry response.

**Expected:**
- No REVIEW_PARSE_FAILURE event emitted.
- REVIEW_PARSE_RETRY_SUCCESS event emitted.

**Assertion pseudocode:**
```
events = run_persistence_with_retry(bad_then_good)
ASSERT not any(e.type == REVIEW_PARSE_FAILURE for e in events)
ASSERT any(e.type == REVIEW_PARSE_RETRY_SUCCESS for e in events)
```

### TS-74-18: Failed Retry Emits Parse Failure

**Requirement:** 74-REQ-3.E1
**Type:** integration
**Description:** Verify REVIEW_PARSE_FAILURE is emitted when retry also fails.

**Preconditions:**
- Mock backend: both responses unparseable.
- Mock sink.

**Input:**
- Two unparseable responses.

**Expected:**
- REVIEW_PARSE_FAILURE event emitted with `retry_attempted: true`.

**Assertion pseudocode:**
```
events = run_persistence_with_retry(bad_then_bad)
ASSERT any(e.type == REVIEW_PARSE_FAILURE for e in events)
failure_event = find(events, REVIEW_PARSE_FAILURE)
ASSERT failure_event.payload["retry_attempted"] == True
```

### TS-74-19: No Retry on Terminated Session

**Requirement:** 74-REQ-3.E2
**Type:** unit
**Description:** Verify retry is skipped when session is terminated.

**Preconditions:**
- Session handle indicates terminated state (timeout/error).

**Input:**
- Unparseable transcript, terminated session.

**Expected:**
- No retry attempted. REVIEW_PARSE_FAILURE emitted directly.

**Assertion pseudocode:**
```
result = persist_review_findings(..., session_alive=False)
ASSERT retry_attempted == False
ASSERT parse_failure_emitted == True
```

### TS-74-20: Partial Convergence - Skeptic

**Requirement:** 74-REQ-4.1
**Type:** unit
**Description:** Verify skeptic convergence proceeds with parseable instances
only.

**Preconditions:**
- 3 skeptic instances: 2 produce findings, 1 returns None (parse failure).

**Input:**
- `instance_findings = [[finding_a, finding_b], [finding_c], None]`

**Expected:**
- Convergence receives only the 2 non-None lists.
- Result contains merged findings from 2 instances.

**Assertion pseudocode:**
```
raw_results = [[f_a, f_b], [f_c], None]
filtered = [r for r in raw_results if r is not None]
merged, blocked = converge_skeptic_records(filtered, block_threshold=5)
ASSERT len(filtered) == 2
ASSERT len(merged) >= 1
```

### TS-74-21: Partial Convergence - Verifier

**Requirement:** 74-REQ-4.2
**Type:** unit
**Description:** Verify verifier convergence proceeds with parseable
instances only.

**Preconditions:**
- 2 verifier instances: 1 produces verdicts, 1 returns None.

**Input:**
- `instance_verdicts = [[verdict_pass], None]`

**Expected:**
- Convergence receives only the 1 non-None list.

**Assertion pseudocode:**
```
raw_results = [[v_pass], None]
filtered = [r for r in raw_results if r is not None]
merged = converge_verifier_records(filtered)
ASSERT len(merged) == 1
```

### TS-74-22: Partial Convergence - Auditor

**Requirement:** 74-REQ-4.3
**Type:** unit
**Description:** Verify auditor convergence proceeds with parseable
instances only.

**Preconditions:**
- 2 auditor instances: 1 produces AuditResult, 1 returns None.

**Input:**
- `instance_results = [audit_result, None]`

**Expected:**
- Convergence receives only the 1 non-None result.

**Assertion pseudocode:**
```
raw_results = [audit_result, None]
filtered = [r for r in raw_results if r is not None]
merged = converge_auditor(filtered)
ASSERT merged.overall_verdict == audit_result.overall_verdict
```

### TS-74-23: No Parse Failure When Some Instances Succeed

**Requirement:** 74-REQ-4.4
**Type:** unit
**Description:** Verify REVIEW_PARSE_FAILURE is NOT emitted when at least
one instance produces parseable output.

**Preconditions:**
- 2 instances: 1 parseable, 1 not.
- Mock sink.

**Input:**
- Mixed parse results.

**Expected:**
- No REVIEW_PARSE_FAILURE event.
- Warning logged for failed instance.

**Assertion pseudocode:**
```
events = run_multi_instance([good_output, bad_output])
ASSERT not any(e.type == REVIEW_PARSE_FAILURE for e in events)
```

### TS-74-24: Warning Logged for Failed Instances

**Requirement:** 74-REQ-4.5
**Type:** unit
**Description:** Verify a warning is logged when some instances fail parsing.

**Preconditions:**
- 2 instances: 1 parseable, 1 not.
- caplog fixture.

**Input:**
- Mixed parse results.

**Expected:**
- Warning log message identifies the failed instance.

**Assertion pseudocode:**
```
with caplog:
    run_multi_instance([good, bad])
ASSERT any("instance" in r.message and "failed" in r.message for r in caplog.records)
```

### TS-74-25: All Instances Fail Emits Parse Failure

**Requirement:** 74-REQ-4.E1
**Type:** unit
**Description:** Verify REVIEW_PARSE_FAILURE is emitted when ALL instances
fail parsing.

**Preconditions:**
- 2 instances, both unparseable.
- Mock sink.

**Input:**
- All-bad parse results.

**Expected:**
- REVIEW_PARSE_FAILURE event emitted.
- Empty results returned.

**Assertion pseudocode:**
```
events, results = run_multi_instance([bad, bad])
ASSERT any(e.type == REVIEW_PARSE_FAILURE for e in events)
ASSERT results == []
```

### TS-74-26: Retry Success Audit Event

**Requirement:** 74-REQ-5.1
**Type:** unit
**Description:** Verify REVIEW_PARSE_RETRY_SUCCESS event is emitted on
successful retry.

**Preconditions:**
- Mock sink.

**Input:**
- Failed initial parse, successful retry.

**Expected:**
- Event with type REVIEW_PARSE_RETRY_SUCCESS, containing archetype and
  node_id in payload.

**Assertion pseudocode:**
```
events = run_with_retry(bad_then_good)
event = find(events, REVIEW_PARSE_RETRY_SUCCESS)
ASSERT event is not None
ASSERT "archetype" in event.payload
ASSERT "node_id" in event.payload or event.node_id is not None
```

### TS-74-27: Parse Failure Payload Contains Strategy Field

**Requirement:** 74-REQ-5.3
**Type:** unit
**Description:** Verify REVIEW_PARSE_FAILURE payload includes strategy field.

**Preconditions:**
- Mock sink, all-fail scenario.

**Input:**
- Unparseable output, retry also fails.

**Expected:**
- REVIEW_PARSE_FAILURE payload contains `strategy` field with comma-
  separated strategy names.

**Assertion pseudocode:**
```
events = run_with_retry(bad_then_bad)
event = find(events, REVIEW_PARSE_FAILURE)
ASSERT "strategy" in event.payload
ASSERT "bracket_scan" in event.payload["strategy"]
```

## Property Test Cases

### TS-74-P1: Fuzzy Matching Subsumes Exact Matching

**Property:** Property 1 from design.md
**Validates:** 74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3
**Type:** property
**Description:** For any canonical wrapper key, the exact key always resolves.

**For any:** canonical_key sampled from WRAPPER_KEY_VARIANTS keys
**Invariant:** `_resolve_wrapper_key({canonical_key: []}, canonical_key)`
returns the canonical key.

**Assertion pseudocode:**
```
FOR ANY canonical_key IN WRAPPER_KEY_VARIANTS.keys():
    data = {canonical_key: []}
    result = _resolve_wrapper_key(data, canonical_key)
    ASSERT result == canonical_key
```

### TS-74-P2: Case Normalization Preserves Values

**Property:** Property 2 from design.md
**Validates:** 74-REQ-2.4
**Type:** property
**Description:** Normalizing keys to lowercase preserves all values.

**For any:** dict with random string keys (no case collisions) and
integer values
**Invariant:** `_normalize_keys(d)` has the same length and same set of
values as `d`.

**Assertion pseudocode:**
```
FOR ANY d IN dicts_without_case_collisions:
    result = _normalize_keys(d)
    ASSERT len(result) == len(d)
    ASSERT set(result.values()) == set(d.values())
```

### TS-74-P3: Retry Bound

**Property:** Property 3 from design.md
**Validates:** 74-REQ-3.3, 74-REQ-3.E1
**Type:** property
**Description:** Total parse attempts never exceed 2.

**For any:** sequence of N unparseable responses (N ≥ 1)
**Invariant:** The number of parse attempts is at most 2.

**Assertion pseudocode:**
```
FOR ANY n_bad_responses IN integers(min=1, max=10):
    attempt_count = run_parse_with_retry(bad_responses * n_bad_responses)
    ASSERT attempt_count <= 2
```

### TS-74-P4: Partial Convergence Monotonicity

**Property:** Property 4 from design.md
**Validates:** 74-REQ-4.1, 74-REQ-4.2, 74-REQ-4.3
**Type:** property
**Description:** Filtering preserves all non-None results.

**For any:** list of N elements, each either a list of findings or None
**Invariant:** filtered list contains exactly the non-None elements, in order.

**Assertion pseudocode:**
```
FOR ANY results IN lists(elements=one_of(finding_lists, none())):
    filtered = [r for r in results if r is not None]
    ASSERT len(filtered) == sum(1 for r in results if r is not None)
    ASSERT all(f is not None for f in filtered)
```

### TS-74-P5: Variant Coverage

**Property:** Property 6 from design.md
**Validates:** 74-REQ-2.2, 74-REQ-2.3
**Type:** property
**Description:** Every registered variant resolves correctly.

**For any:** (canonical_key, variant) pair from WRAPPER_KEY_VARIANTS
**Invariant:** `_resolve_wrapper_key({variant: []}, canonical_key)` returns
the variant string.

**Assertion pseudocode:**
```
FOR ANY (canonical, variant) IN flatten(WRAPPER_KEY_VARIANTS.items()):
    data = {variant: []}
    result = _resolve_wrapper_key(data, canonical)
    ASSERT result == variant
```

### TS-74-P6: Backward Compatibility

**Property:** Property 7 from design.md
**Validates:** 74-REQ-2.5
**Type:** property
**Description:** Exact-match inputs still parse correctly.

**For any:** well-formed JSON with exact canonical keys and standard casing
**Invariant:** `_unwrap_items()` returns the same items as before changes.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(finding_dicts, min_size=1):
    response = json.dumps({"findings": findings})
    items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
    ASSERT items == findings
```

## Edge Case Tests

### TS-74-E1: Empty Output Text

**Requirement:** 74-REQ-2.E1
**Type:** unit
**Description:** Verify empty output returns no findings.

**Preconditions:**
- None.

**Input:**
- `output_text = ""`

**Expected:**
- `extract_json_array("")` returns `None`.

**Assertion pseudocode:**
```
result = extract_json_array("")
ASSERT result is None
```

### TS-74-E2: JSON With Unknown Wrapper Key

**Requirement:** 74-REQ-2.E1
**Type:** unit
**Description:** Verify JSON with unrecognized wrapper key falls through
to single-item detection.

**Preconditions:**
- None.

**Input:**
- `{"results_data": [{"severity": "major"}]}`

**Expected:**
- If the object contains required single-item keys, treated as single item.
  Otherwise returns empty list.

**Assertion pseudocode:**
```
response = '{"results_data": [{"severity": "major"}]}'
items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
# "results_data" is not a variant, but object has "severity" -> single item? No, severity is nested.
ASSERT items == []  # Not a recognized wrapper or single-item shape
```

### TS-74-E3: Single Instance Bypass

**Requirement:** 74-REQ-4.E2
**Type:** unit
**Description:** Verify single-instance mode uses result directly without
partial-result filtering.

**Preconditions:**
- instances = 1.

**Input:**
- Single instance result (parseable or not).

**Expected:**
- Result used directly, no filtering applied.

**Assertion pseudocode:**
```
result = run_single_instance(good_output)
ASSERT result == parsed_findings  # Direct passthrough
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 74-REQ-1.1 | TS-74-1 | unit |
| 74-REQ-1.2 | TS-74-2 | unit |
| 74-REQ-1.3 | TS-74-3 | unit |
| 74-REQ-1.4 | TS-74-4 | unit |
| 74-REQ-1.5 | TS-74-5 | unit |
| 74-REQ-1.6 | TS-74-6 | unit |
| 74-REQ-2.1 | TS-74-7, TS-74-P1 | unit, property |
| 74-REQ-2.2 | TS-74-8, TS-74-P5 | unit, property |
| 74-REQ-2.3 | TS-74-9, TS-74-P5 | unit, property |
| 74-REQ-2.4 | TS-74-10, TS-74-P2 | unit, property |
| 74-REQ-2.5 | TS-74-11, TS-74-P6 | unit, property |
| 74-REQ-2.E1 | TS-74-12, TS-74-E1, TS-74-E2 | unit |
| 74-REQ-2.E2 | TS-74-13 | unit |
| 74-REQ-3.1 | TS-74-14 | integration |
| 74-REQ-3.2 | TS-74-15 | unit |
| 74-REQ-3.3 | TS-74-16, TS-74-P3 | unit, property |
| 74-REQ-3.4 | TS-74-17 | integration |
| 74-REQ-3.5 | TS-74-14 | integration |
| 74-REQ-3.E1 | TS-74-18, TS-74-P3 | integration, property |
| 74-REQ-3.E2 | TS-74-19 | unit |
| 74-REQ-4.1 | TS-74-20, TS-74-P4 | unit, property |
| 74-REQ-4.2 | TS-74-21, TS-74-P4 | unit, property |
| 74-REQ-4.3 | TS-74-22, TS-74-P4 | unit, property |
| 74-REQ-4.4 | TS-74-23 | unit |
| 74-REQ-4.5 | TS-74-24 | unit |
| 74-REQ-4.E1 | TS-74-25 | unit |
| 74-REQ-4.E2 | TS-74-E3 | unit |
| 74-REQ-5.1 | TS-74-26 | unit |
| 74-REQ-5.2 | TS-74-18 | integration |
| 74-REQ-5.3 | TS-74-27 | unit |
| Property 1 | TS-74-P1 | property |
| Property 2 | TS-74-P2 | property |
| Property 3 | TS-74-P3 | property |
| Property 4 | TS-74-P4 | property |
| Property 6 | TS-74-P5 | property |
| Property 7 | TS-74-P6 | property |
