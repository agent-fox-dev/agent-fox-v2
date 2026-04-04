# Test Specification: Cross-Iteration Hunt Scan Deduplication

## Overview

Tests validate fingerprint computation, embedding/extraction, and the
dedup gate. Unit tests cover pure functions. Property tests verify formal
invariants from design.md. Integration tests exercise the full pipeline
through a mock platform.

## Test Cases

### TS-79-1: Fingerprint from category and files

**Requirement:** 79-REQ-1.1
**Type:** unit
**Description:** Verify fingerprint is a 16-char hex digest of category + sorted files.

**Preconditions:** None.

**Input:**
- FindingGroup with category="linter_debt", affected_files=["b.py", "a.py"]

**Expected:**
- 16-character lowercase hex string
- Same as manually computing SHA-256 of `"linter_debt\0a.py\0b.py"` truncated to 16 chars

**Assertion pseudocode:**
```
group = FindingGroup(category="linter_debt", affected_files=["b.py", "a.py"], ...)
fp = compute_fingerprint(group)
ASSERT len(fp) == 16
ASSERT all(c in "0123456789abcdef" for c in fp)
expected = sha256("linter_debt\0a.py\0b.py".encode()).hexdigest()[:16]
ASSERT fp == expected
```

### TS-79-2: Identical groups produce identical fingerprints

**Requirement:** 79-REQ-1.2
**Type:** unit
**Description:** Two groups with same category and files (different order) produce same fingerprint.

**Preconditions:** None.

**Input:**
- Group A: category="dead_code", affected_files=["x.py", "y.py"], title="Title A"
- Group B: category="dead_code", affected_files=["y.py", "x.py"], title="Title B"

**Expected:** compute_fingerprint(A) == compute_fingerprint(B)

**Assertion pseudocode:**
```
fp_a = compute_fingerprint(group_a)
fp_b = compute_fingerprint(group_b)
ASSERT fp_a == fp_b
```

### TS-79-3: Different category produces different fingerprint

**Requirement:** 79-REQ-1.3, 79-REQ-1.E2
**Type:** unit
**Description:** Groups with same files but different category produce different fingerprints.

**Preconditions:** None.

**Input:**
- Group A: category="linter_debt", affected_files=["a.py"]
- Group B: category="dead_code", affected_files=["a.py"]

**Expected:** compute_fingerprint(A) != compute_fingerprint(B)

**Assertion pseudocode:**
```
ASSERT compute_fingerprint(group_a) != compute_fingerprint(group_b)
```

### TS-79-4: Empty affected_files fingerprint

**Requirement:** 79-REQ-1.E1
**Type:** unit
**Description:** Group with empty affected_files produces valid fingerprint from category only.

**Preconditions:** None.

**Input:**
- FindingGroup with category="todo_fixme", affected_files=[]

**Expected:**
- 16-char hex string
- Equal to SHA-256 of `"todo_fixme"` truncated to 16 chars

**Assertion pseudocode:**
```
group = FindingGroup(category="todo_fixme", affected_files=[], ...)
fp = compute_fingerprint(group)
ASSERT len(fp) == 16
expected = sha256("todo_fixme".encode()).hexdigest()[:16]
ASSERT fp == expected
```

### TS-79-5: Embed fingerprint appends marker

**Requirement:** 79-REQ-2.1
**Type:** unit
**Description:** embed_fingerprint appends an HTML comment to the body.

**Preconditions:** None.

**Input:**
- body = "## Issue\n\nSome description"
- fingerprint = "a1b2c3d4e5f67890"

**Expected:**
- Result ends with "\n<!-- af:fingerprint:a1b2c3d4e5f67890 -->"

**Assertion pseudocode:**
```
result = embed_fingerprint(body, "a1b2c3d4e5f67890")
ASSERT result.endswith("\n<!-- af:fingerprint:a1b2c3d4e5f67890 -->")
ASSERT result.startswith("## Issue\n\nSome description")
```

### TS-79-6: Extract fingerprint from body

**Requirement:** 79-REQ-2.2
**Type:** unit
**Description:** extract_fingerprint returns the hex string from a body with a marker.

**Preconditions:** None.

**Input:**
- body = "Some text\n<!-- af:fingerprint:a1b2c3d4e5f67890 -->"

**Expected:** "a1b2c3d4e5f67890"

**Assertion pseudocode:**
```
fp = extract_fingerprint(body)
ASSERT fp == "a1b2c3d4e5f67890"
```

### TS-79-7: Extract returns None when no marker

**Requirement:** 79-REQ-2.E2
**Type:** unit
**Description:** extract_fingerprint returns None for a body without a marker.

**Preconditions:** None.

**Input:**
- body = "Just a regular issue body"

**Expected:** None

**Assertion pseudocode:**
```
fp = extract_fingerprint(body)
ASSERT fp is None
```

### TS-79-8: Extract returns first marker when multiple present

**Requirement:** 79-REQ-2.E1
**Type:** unit
**Description:** If multiple markers exist, first is returned.

**Preconditions:** None.

**Input:**
- body = "text\n<!-- af:fingerprint:aaaa000000000000 -->\n<!-- af:fingerprint:bbbb000000000000 -->"

**Expected:** "aaaa000000000000"

**Assertion pseudocode:**
```
fp = extract_fingerprint(body)
ASSERT fp == "aaaa000000000000"
```

### TS-79-9: Dedup gate filters matching groups

**Requirement:** 79-REQ-4.2, 79-REQ-4.4
**Type:** integration
**Description:** Groups whose fingerprints match existing issues are filtered out.

**Preconditions:**
- Mock platform returns one open issue with af:hunt label whose body contains
  `<!-- af:fingerprint:{fp_of_group_A} -->`

**Input:**
- group_A: same fingerprint as existing issue
- group_B: different fingerprint (no match)

**Expected:**
- filter_known_duplicates returns [group_B] only

**Assertion pseudocode:**
```
platform = MockPlatform(issues=[issue_with_fp_A])
result = await filter_known_duplicates([group_A, group_B], platform)
ASSERT result == [group_B]
```

### TS-79-10: Dedup gate logs skipped duplicates

**Requirement:** 79-REQ-4.3
**Type:** integration
**Description:** Skipped groups are logged at INFO with title and issue number.

**Preconditions:**
- Mock platform returns issue #42 with matching fingerprint

**Input:**
- group with title="Unused imports" and matching fingerprint

**Expected:**
- INFO log message containing "Unused imports" and "42"

**Assertion pseudocode:**
```
with capture_logs("INFO") as logs:
    result = await filter_known_duplicates([group], platform)
ASSERT any("Unused imports" in msg and "42" in msg for msg in logs)
ASSERT result == []
```

### TS-79-11: Issue created with af:hunt label

**Requirement:** 79-REQ-3.1
**Type:** integration
**Description:** create_issues_from_groups passes af:hunt label when creating.

**Preconditions:**
- Mock platform that records create_issue arguments

**Input:**
- One FindingGroup

**Expected:**
- platform.create_issue called with labels=["af:hunt"]

**Assertion pseudocode:**
```
platform = MockPlatform()
await create_issues_from_groups([group], platform)
ASSERT platform.create_issue_calls[0].labels == ["af:hunt"]
```

### TS-79-12: Issue body contains fingerprint marker

**Requirement:** 79-REQ-2.1
**Type:** integration
**Description:** Created issue body has the fingerprint marker appended.

**Preconditions:**
- Mock platform that records create_issue arguments

**Input:**
- One FindingGroup with known fingerprint

**Expected:**
- Body passed to platform.create_issue contains `<!-- af:fingerprint:{expected_fp} -->`

**Assertion pseudocode:**
```
platform = MockPlatform()
await create_issues_from_groups([group], platform)
body = platform.create_issue_calls[0].body
fp = extract_fingerprint(body)
ASSERT fp == compute_fingerprint(group)
```

### TS-79-13: Auto mode assigns both labels

**Requirement:** 79-REQ-3.2
**Type:** integration
**Description:** With --auto, issues get both af:hunt and af:fix labels.

**Preconditions:**
- Mock platform, auto_fix=True in engine config

**Input:**
- One FindingGroup, engine running with --auto

**Expected:**
- Issue created with af:hunt label
- af:fix label assigned afterward (existing behavior)

**Assertion pseudocode:**
```
platform = MockPlatform()
engine = NightShiftEngine(config, platform, auto_fix=True)
# ... trigger hunt scan ...
ASSERT "af:hunt" in platform.create_issue_calls[0].labels
ASSERT platform.assign_label_calls[0] == (issue_number, "af:fix")
```

### TS-79-14: Separator prevents ambiguity

**Requirement:** 79-REQ-5.1
**Type:** unit
**Description:** Null-byte separator prevents category/file boundary ambiguity.

**Preconditions:** None.

**Input:**
- Group A: category="ab", affected_files=["c"]
- Group B: category="a", affected_files=["bc"]

**Expected:** compute_fingerprint(A) != compute_fingerprint(B)

**Assertion pseudocode:**
```
ASSERT compute_fingerprint(group_a) != compute_fingerprint(group_b)
```

### TS-79-15: Duplicate files are deduplicated before hashing

**Requirement:** 79-REQ-5.E1
**Type:** unit
**Description:** Duplicate entries in affected_files do not affect the fingerprint.

**Preconditions:** None.

**Input:**
- Group A: affected_files=["a.py", "b.py", "a.py"]
- Group B: affected_files=["a.py", "b.py"]

**Expected:** compute_fingerprint(A) == compute_fingerprint(B)

**Assertion pseudocode:**
```
ASSERT compute_fingerprint(group_a) == compute_fingerprint(group_b)
```

## Edge Case Tests

### TS-79-E1: Dedup gate fails open on platform error

**Requirement:** 79-REQ-4.E1
**Type:** integration
**Description:** If fetching existing issues fails, all groups pass through.

**Preconditions:**
- Mock platform that raises IntegrationError on list_issues_by_label

**Input:**
- Two FindingGroups

**Expected:**
- Both groups returned (no filtering)
- Warning logged

**Assertion pseudocode:**
```
platform = FailingMockPlatform()
with capture_logs("WARNING") as logs:
    result = await filter_known_duplicates([group_a, group_b], platform)
ASSERT len(result) == 2
ASSERT any("warning" in msg.lower() for msg in logs)
```

### TS-79-E2: No existing af:hunt issues

**Requirement:** 79-REQ-4.E2
**Type:** integration
**Description:** Empty platform returns all groups.

**Preconditions:**
- Mock platform returns empty list for list_issues_by_label

**Input:**
- Two FindingGroups

**Expected:**
- Both groups returned

**Assertion pseudocode:**
```
platform = MockPlatform(issues=[])
result = await filter_known_duplicates([group_a, group_b], platform)
ASSERT len(result) == 2
```

### TS-79-E3: All groups are duplicates

**Requirement:** 79-REQ-4.E3
**Type:** integration
**Description:** When all groups match existing issues, returns empty list.

**Preconditions:**
- Mock platform returns issues matching all input group fingerprints

**Input:**
- Two FindingGroups, both matching existing issues

**Expected:**
- Empty list returned

**Assertion pseudocode:**
```
result = await filter_known_duplicates([group_a, group_b], platform)
ASSERT result == []
```

### TS-79-E4: Label assignment failure does not block

**Requirement:** 79-REQ-3.E1
**Type:** integration
**Description:** If af:hunt label assignment fails, issue creation continues.

**Preconditions:**
- Mock platform where create_issue succeeds but labels param causes a warning
  (or the label is included in the create_issue call directly)

**Input:**
- One FindingGroup

**Expected:**
- Issue is created (with or without label)
- No exception propagated

**Assertion pseudocode:**
```
# Since af:hunt is passed via create_issue labels param, test the
# scenario where the platform ignores/fails on the label.
platform = MockPlatform(label_assignment_fails=True)
result = await create_issues_from_groups([group], platform)
ASSERT len(result) == 1
```

## Property Test Cases

### TS-79-P1: Fingerprint Determinism

**Property:** Property 1 from design.md
**Validates:** 79-REQ-1.1, 79-REQ-1.2, 79-REQ-5.1, 79-REQ-5.2
**Type:** property
**Description:** Same category and same files always produce the same fingerprint.

**For any:** category: text(min_size=1), files: lists(text(min_size=1))
**Invariant:** compute_fingerprint(group(category, files)) == compute_fingerprint(group(category, shuffled(files)))

**Assertion pseudocode:**
```
FOR ANY category IN text(), files IN lists(text()):
    shuffled = random_permutation(files)
    group_a = make_group(category=category, affected_files=files)
    group_b = make_group(category=category, affected_files=shuffled)
    ASSERT compute_fingerprint(group_a) == compute_fingerprint(group_b)
```

### TS-79-P2: Fingerprint Uniqueness

**Property:** Property 2 from design.md
**Validates:** 79-REQ-1.3, 79-REQ-1.E2
**Type:** property
**Description:** Different category or different files produce different fingerprints.

**For any:** two FindingGroups where category differs OR deduplicated-sorted affected_files differ
**Invariant:** compute_fingerprint(A) != compute_fingerprint(B) (probabilistic)

**Assertion pseudocode:**
```
FOR ANY cat_a, cat_b IN text(), files_a, files_b IN lists(text()):
    ASSUME sorted(set(files_a)) != sorted(set(files_b)) OR cat_a != cat_b
    group_a = make_group(category=cat_a, affected_files=files_a)
    group_b = make_group(category=cat_b, affected_files=files_b)
    ASSERT compute_fingerprint(group_a) != compute_fingerprint(group_b)
```

### TS-79-P3: Embed-Extract Round-Trip

**Property:** Property 3 from design.md
**Validates:** 79-REQ-2.1, 79-REQ-2.2
**Type:** property
**Description:** Embedding then extracting a fingerprint recovers the original.

**For any:** body: text(), fp: 16-char hex string
**Invariant:** extract_fingerprint(embed_fingerprint(body, fp)) == fp

**Assertion pseudocode:**
```
FOR ANY body IN text(), fp IN hex_strings(length=16):
    ASSERT extract_fingerprint(embed_fingerprint(body, fp)) == fp
```

### TS-79-P4: Dedup Gate Conservation

**Property:** Property 4 from design.md
**Validates:** 79-REQ-4.2, 79-REQ-4.4, 79-REQ-4.E3
**Type:** property
**Description:** The gate returns a subset; no novel group is dropped, no duplicate passes.

**For any:** list of FindingGroups, set of known fingerprints
**Invariant:** result is subset of input AND every result fp NOT in known AND every omitted fp IN known

**Assertion pseudocode:**
```
FOR ANY groups IN lists(finding_groups()), known IN sets(hex_strings()):
    platform = MockPlatform(fingerprints=known)
    result = await filter_known_duplicates(groups, platform)
    ASSERT set(result).issubset(set(groups))
    for g in result:
        ASSERT compute_fingerprint(g) not in known
    for g in groups:
        if g not in result:
            ASSERT compute_fingerprint(g) in known
```

### TS-79-P5: Fail-Open Guarantee

**Property:** Property 5 from design.md
**Validates:** 79-REQ-4.E1
**Type:** property
**Description:** Platform failure returns all groups unchanged.

**For any:** list of FindingGroups
**Invariant:** filter_known_duplicates(groups, failing_platform) == groups

**Assertion pseudocode:**
```
FOR ANY groups IN lists(finding_groups()):
    platform = FailingMockPlatform()
    result = await filter_known_duplicates(groups, platform)
    ASSERT result == groups
```

### TS-79-P6: Empty Files Stability

**Property:** Property 6 from design.md
**Validates:** 79-REQ-1.E1
**Type:** property
**Description:** Empty affected_files produces valid fingerprint from category alone.

**For any:** category: text(min_size=1)
**Invariant:** len(compute_fingerprint(group(category, []))) == 16

**Assertion pseudocode:**
```
FOR ANY category IN text(min_size=1):
    group = make_group(category=category, affected_files=[])
    fp = compute_fingerprint(group)
    ASSERT len(fp) == 16
    ASSERT all(c in "0123456789abcdef" for c in fp)
```

## Integration Smoke Tests

### TS-79-SMOKE-1: Full hunt scan pipeline with dedup

**Execution Path:** Path 1 from design.md
**Description:** Verifies end-to-end that a duplicate finding across two scan
iterations does not create a second issue.

**Setup:**
- Mock platform with `create_issue` and `list_issues_by_label` implemented
- Real `filter_known_duplicates`, real `create_issues_from_groups`, real
  `compute_fingerprint`, real `embed_fingerprint`, real `extract_fingerprint`
- Stub only: HuntScanner.run (returns fixed findings), AI critic (bypassed via
  mechanical grouping with < 3 findings)

**Trigger:**
1. Call `_run_hunt_scan()` — creates issues with fingerprints
2. Configure mock platform to return the issues created in step 1 from
   `list_issues_by_label`
3. Call `_run_hunt_scan()` again with the same findings

**Expected side effects:**
- Step 1: `platform.create_issue` called N times (one per group)
- Step 3: `platform.create_issue` called 0 times (all groups are duplicates)
- INFO log messages for each skipped duplicate

**Must NOT satisfy with:** Mocking `filter_known_duplicates`, mocking
`compute_fingerprint`, mocking `embed_fingerprint`, mocking
`extract_fingerprint`.

**Assertion pseudocode:**
```
platform = MockPlatform()
engine = NightShiftEngine(config, platform)
engine._run_hunt_scan_inner = lambda: fixed_findings  # 2 findings

# Iteration 1: creates issues
await engine._run_hunt_scan()
ASSERT platform.create_issue.call_count == 2

# Configure platform to return created issues
platform.set_open_hunt_issues(platform.created_issues)

# Iteration 2: same findings, should create nothing
await engine._run_hunt_scan()
ASSERT platform.create_issue.call_count == 2  # no new calls
```

### TS-79-SMOKE-2: Full pipeline fail-open on platform error

**Execution Path:** Path 2 from design.md
**Description:** Verifies that platform failure during dedup results in all
issues being created (fail-open).

**Setup:**
- Mock platform where `list_issues_by_label` raises IntegrationError but
  `create_issue` works normally
- Real dedup components (not mocked)

**Trigger:**
- Call `_run_hunt_scan()` with findings

**Expected side effects:**
- `platform.create_issue` called for every group (no filtering)
- WARNING log about platform failure

**Must NOT satisfy with:** Mocking `filter_known_duplicates`.

**Assertion pseudocode:**
```
platform = MockPlatform(list_issues_raises=IntegrationError("timeout"))
engine = NightShiftEngine(config, platform)
engine._run_hunt_scan_inner = lambda: fixed_findings

with capture_logs("WARNING") as logs:
    await engine._run_hunt_scan()
ASSERT platform.create_issue.call_count == len(expected_groups)
ASSERT any("warning" in msg.lower() for msg in logs)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 79-REQ-1.1 | TS-79-1 | unit |
| 79-REQ-1.2 | TS-79-2 | unit |
| 79-REQ-1.3 | TS-79-3 | unit |
| 79-REQ-1.E1 | TS-79-4 | unit |
| 79-REQ-1.E2 | TS-79-3 | unit |
| 79-REQ-2.1 | TS-79-5, TS-79-12 | unit, integration |
| 79-REQ-2.2 | TS-79-6 | unit |
| 79-REQ-2.E1 | TS-79-8 | unit |
| 79-REQ-2.E2 | TS-79-7 | unit |
| 79-REQ-3.1 | TS-79-11 | integration |
| 79-REQ-3.2 | TS-79-13 | integration |
| 79-REQ-3.E1 | TS-79-E4 | integration |
| 79-REQ-4.1 | TS-79-9 | integration |
| 79-REQ-4.2 | TS-79-9 | integration |
| 79-REQ-4.3 | TS-79-10 | integration |
| 79-REQ-4.4 | TS-79-9 | integration |
| 79-REQ-4.E1 | TS-79-E1 | integration |
| 79-REQ-4.E2 | TS-79-E2 | integration |
| 79-REQ-4.E3 | TS-79-E3 | integration |
| 79-REQ-5.1 | TS-79-14 | unit |
| 79-REQ-5.2 | TS-79-2 | unit |
| 79-REQ-5.E1 | TS-79-15 | unit |
| Property 1 | TS-79-P1 | property |
| Property 2 | TS-79-P2 | property |
| Property 3 | TS-79-P3 | property |
| Property 4 | TS-79-P4 | property |
| Property 5 | TS-79-P5 | property |
| Property 6 | TS-79-P6 | property |
| Path 1 | TS-79-SMOKE-1 | integration |
| Path 2 | TS-79-SMOKE-2 | integration |
