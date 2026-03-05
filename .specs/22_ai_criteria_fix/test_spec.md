# Test Specification: AI-Powered Criteria Auto-Fix

## Overview

Tests validate the AI rewrite pipeline from prompt construction through file
modification. All AI calls are mocked — no live API calls in tests. Tests
cover the rewrite function, the criteria fixer, CLI integration, and edge
cases for malformed responses and missing criteria.

## Test Cases

### TS-22-1: Rewrite call produces replacement text

**Requirement:** 22-REQ-1.1
**Type:** unit
**Description:** Verify that `rewrite_criteria()` returns a mapping of criterion IDs to replacement text when given valid findings.

**Preconditions:**
- Mocked Anthropic client returns valid JSON with one rewrite entry.

**Input:**
- `spec_name`: `"test_spec"`
- `requirements_text`: fixture requirements.md content with one vague criterion
- `findings`: one Finding with rule `vague-criterion`, message containing `[99-REQ-1.1]`

**Expected:**
- Return dict contains key `"99-REQ-1.1"` with non-empty string value.

**Assertion pseudocode:**
```
result = await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT "99-REQ-1.1" IN result
ASSERT len(result["99-REQ-1.1"]) > 0
```

---

### TS-22-2: Rewrite applied to requirements.md

**Requirement:** 22-REQ-1.2
**Type:** unit
**Description:** Verify that `fix_ai_criteria()` writes replacement text back to the file.

**Preconditions:**
- Fixture `requirements.md` with criterion `[99-REQ-1.1] THE system SHALL be fast.`

**Input:**
- `rewrites`: `{"99-REQ-1.1": "THE system SHALL respond within 200ms at p95."}`

**Expected:**
- File content contains the replacement text.
- File content does not contain the original "be fast" text.

**Assertion pseudocode:**
```
results = fix_ai_criteria("test_spec", req_path, rewrites)
content = req_path.read_text()
ASSERT "respond within 200ms" IN content
ASSERT "be fast" NOT IN content
ASSERT len(results) == 1
```

---

### TS-22-3: Requirement ID preserved in rewrite

**Requirement:** 22-REQ-1.3
**Type:** unit
**Description:** Verify that the requirement ID prefix is preserved after rewriting.

**Preconditions:**
- Fixture with bracket-format ID: `[99-REQ-1.1]`

**Input:**
- `rewrites`: `{"99-REQ-1.1": "THE system SHALL respond within 200ms."}`

**Expected:**
- File still contains the ID prefix `[99-REQ-1.1]`.

**Assertion pseudocode:**
```
fix_ai_criteria("test_spec", req_path, rewrites)
content = req_path.read_text()
ASSERT "[99-REQ-1.1]" IN content
```

---

### TS-22-4: Bold-format ID preserved in rewrite

**Requirement:** 22-REQ-1.3
**Type:** unit
**Description:** Verify that bold-format requirement IDs are also preserved.

**Preconditions:**
- Fixture with bold-format ID: `**99-REQ-1.1:**`

**Input:**
- `rewrites`: `{"99-REQ-1.1": "THE system SHALL respond within 200ms."}`

**Expected:**
- File still contains `**99-REQ-1.1:**`.

**Assertion pseudocode:**
```
fix_ai_criteria("test_spec", req_path, rewrites)
content = req_path.read_text()
ASSERT "**99-REQ-1.1:**" IN content
```

---

### TS-22-5: No AI rewrite without --ai flag

**Requirement:** 22-REQ-1.4
**Type:** integration
**Description:** Verify that `--fix` alone does not invoke AI rewrite.

**Preconditions:**
- Spec with vague criterion that would be flagged by AI.
- Mocked Anthropic client.

**Input:**
- CLI args: `lint-spec --fix` (no `--ai`)

**Expected:**
- Anthropic client is not called for rewrite.
- The vague criterion remains unchanged.

**Assertion pseudocode:**
```
result = runner.invoke(lint_spec, ["--fix"])
ASSERT mock_client.messages.create.call_count == 0
```

---

### TS-22-6: EARS keywords in rewrite prompt

**Requirement:** 22-REQ-2.1
**Type:** unit
**Description:** Verify that the rewrite prompt includes EARS syntax keywords.

**Preconditions:**
- Mocked Anthropic client captures the prompt.

**Input:**
- One finding with rule `vague-criterion`.

**Expected:**
- The prompt text sent to the API contains "SHALL", "WHEN", "WHILE", "IF/THEN", "WHERE".

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model)
prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
ASSERT "SHALL" IN prompt
ASSERT "WHEN" IN prompt
ASSERT "EARS" IN prompt
```

---

### TS-22-7: Rewrite prompt includes full requirements text

**Requirement:** 22-REQ-2.4
**Type:** unit
**Description:** Verify the prompt includes the full requirements.md content.

**Preconditions:**
- Fixture requirements text with distinctive marker string.

**Input:**
- `requirements_text` containing `"UNIQUE_MARKER_STRING"`

**Expected:**
- The prompt contains `"UNIQUE_MARKER_STRING"`.

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model)
prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
ASSERT "UNIQUE_MARKER_STRING" IN prompt
```

---

### TS-22-13: Rewrite preserves original intent

**Requirement:** 22-REQ-2.2
**Type:** unit
**Description:** Verify the rewrite prompt instructs the AI to preserve original intent.

**Preconditions:**
- Mocked Anthropic client captures the prompt.

**Input:**
- One finding with rule `vague-criterion`.

**Expected:**
- The prompt text contains instructions about preserving intent (e.g., "preserve the original intent", "behavioral scope").

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model)
prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
ASSERT "intent" IN prompt.lower()
```

---

### TS-22-14: Rewrite prompt prevents fix loops

**Requirement:** 22-REQ-2.3
**Type:** unit
**Description:** Verify the prompt instructs the AI to produce text that would pass its own analysis.

**Preconditions:**
- Mocked Anthropic client captures the prompt.

**Input:**
- One finding with rule `implementation-leak`.

**Expected:**
- The prompt contains instructions about producing text that would not be flagged.

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model)
prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
ASSERT "pass" IN prompt.lower() OR "not be flagged" IN prompt.lower()
```

---

### TS-22-15: Re-validation runs after AI rewrite

**Requirement:** 22-REQ-4.2
**Type:** integration
**Description:** Verify that after AI rewrites are applied, the system re-validates the specs.

**Preconditions:**
- Mocked AI analysis and rewrite.
- Spec with a vague criterion.

**Input:**
- CLI args: `lint-spec --ai --fix`

**Expected:**
- After rewrite, validation runs again and the output reflects the re-validated state.

**Assertion pseudocode:**
```
result = runner.invoke(lint_spec, ["--ai", "--fix"])
# The re-validation output should not contain the rewritten criterion's finding
# (assuming the rewrite fixed it)
```

---

### TS-22-16: FixResult uses matching rule name

**Requirement:** 22-REQ-4.3
**Type:** unit
**Description:** Verify that FixResult objects carry the same rule name as the original AI finding.

**Preconditions:**
- Fixture with two criteria: one vague, one implementation-leak.

**Input:**
- Rewrites for both criteria with associated finding rules.

**Expected:**
- FixResults have rules `"vague-criterion"` and `"implementation-leak"` respectively.

**Assertion pseudocode:**
```
results = fix_ai_criteria("spec", req_path, rewrites, finding_rules)
ASSERT results[0].rule == "vague-criterion"
ASSERT results[1].rule == "implementation-leak"
```

---

### TS-22-8: Response JSON structure parsed correctly

**Requirement:** 22-REQ-2.5
**Type:** unit
**Description:** Verify that the response JSON mapping is parsed into a dict.

**Preconditions:**
- Mocked response: `{"rewrites": [{"criterion_id": "99-REQ-1.1", "original": "...", "replacement": "new text"}]}`

**Input:**
- One finding for `99-REQ-1.1`.

**Expected:**
- Return dict: `{"99-REQ-1.1": "new text"}`.

**Assertion pseudocode:**
```
result = await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT result == {"99-REQ-1.1": "new text"}
```

---

### TS-22-9: Batching — one call per spec

**Requirement:** 22-REQ-3.1
**Type:** unit
**Description:** Verify that multiple findings for the same spec result in one API call.

**Preconditions:**
- Three findings for the same spec, different criteria.

**Input:**
- `findings` list with 3 entries, all same `spec_name`.

**Expected:**
- `mock_client.messages.create` called exactly once.
- The prompt includes all 3 criterion IDs.

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT mock_client.messages.create.call_count == 1
```

---

### TS-22-10: No call for specs without AI findings

**Requirement:** 22-REQ-3.2
**Type:** unit
**Description:** Verify no rewrite call is made when there are no AI criteria findings.

**Preconditions:**
- Empty findings list.

**Input:**
- `findings`: `[]`

**Expected:**
- Return empty dict, no API call.

**Assertion pseudocode:**
```
result = await rewrite_criteria(spec_name, req_text, [], model)
ASSERT result == {}
ASSERT mock_client.messages.create.call_count == 0
```

---

### TS-22-11: Fix summary includes AI rewrite counts

**Requirement:** 22-REQ-4.1
**Type:** unit
**Description:** Verify FixResult objects use the correct rule names.

**Preconditions:**
- `fix_ai_criteria` applied one vague and one implementation-leak rewrite.

**Input:**
- Two rewrites applied successfully.

**Expected:**
- One FixResult with rule `"vague-criterion"`, one with `"implementation-leak"`.

**Assertion pseudocode:**
```
results = fix_ai_criteria(spec_name, req_path, rewrites)
rules = {r.rule for r in results}
ASSERT "vague-criterion" IN rules OR "implementation-leak" IN rules
```

---

### TS-22-12: STANDARD model used for rewrite

**Requirement:** 22-REQ-3.3
**Type:** unit
**Description:** Verify the rewrite call uses the STANDARD-tier model.

**Preconditions:**
- Mocked model registry and Anthropic client.

**Input:**
- Standard invocation of rewrite_criteria.

**Expected:**
- The model argument passed to `messages.create` matches the STANDARD model ID.

**Assertion pseudocode:**
```
await rewrite_criteria(spec_name, req_text, findings, model="standard-model-id")
call_kwargs = mock_client.messages.create.call_args[1]
ASSERT call_kwargs["model"] == "standard-model-id"
```

### TS-22-17: FIXABLE_RULES extended in AI mode

**Requirement:** 22-REQ-4.4
**Type:** unit
**Description:** Verify that vague-criterion and implementation-leak are treated as fixable when AI mode is active.

**Preconditions:**
- AI criteria findings exist for a spec.

**Input:**
- Findings with rules `vague-criterion` and `implementation-leak`.

**Expected:**
- The fix pipeline processes these findings (does not skip them as unfixable).

**Assertion pseudocode:**
```
# When ai=True, the apply flow should recognize these rules
ASSERT "vague-criterion" is processed by the AI fix path
ASSERT "implementation-leak" is processed by the AI fix path
```

---

## Property Test Cases

### TS-22-P1: Requirement ID round-trip

**Property:** Property 1 from design.md
**Validates:** 22-REQ-1.3
**Type:** property
**Description:** For any criterion ID and replacement text, the fixer preserves the ID in the output.

**For any:** criterion ID matching `\d{2}-REQ-\d+\.\d+`, and arbitrary replacement text (non-empty ASCII strings)
**Invariant:** After applying the rewrite, the file content contains the original criterion ID.

**Assertion pseudocode:**
```
FOR ANY criterion_id IN regex_strategy(r"\d{2}-REQ-\d+\.\d+"):
    FOR ANY replacement IN text(min_size=1):
        write fixture with criterion_id
        fix_ai_criteria("spec", path, {criterion_id: replacement})
        content = path.read_text()
        ASSERT criterion_id IN content
```

---

### TS-22-P2: File integrity after rewrite

**Property:** Property 2 from design.md
**Validates:** 22-REQ-1.2, 22-REQ-1.3
**Type:** property
**Description:** For any requirements file with N requirement headings, the rewritten file has N requirement headings.

**For any:** requirements.md fixture with 1-5 requirement headings and criteria
**Invariant:** Count of `### Requirement` headings is unchanged after rewrite.

**Assertion pseudocode:**
```
FOR ANY n_reqs IN integers(1, 5):
    write fixture with n_reqs requirement sections
    fix_ai_criteria("spec", path, {first_criterion: "replacement"})
    content = path.read_text()
    ASSERT content.count("### Requirement") == n_reqs
```

---

### TS-22-P3: Prompt contains EARS keywords

**Property:** Property 5 from design.md
**Validates:** 22-REQ-2.1
**Type:** property
**Description:** For any set of findings, the rewrite prompt always contains EARS keywords.

**For any:** list of 1-10 findings with vague-criterion or implementation-leak rules
**Invariant:** The prompt text contains "SHALL" and "EARS".

**Assertion pseudocode:**
```
FOR ANY findings IN lists(finding_strategy(), min_size=1, max_size=10):
    await rewrite_criteria("spec", req_text, findings, model)
    prompt = captured_prompt
    ASSERT "SHALL" IN prompt
    ASSERT "EARS" IN prompt
```

## Edge Case Tests

### TS-22-E1: Rewrite call failure leaves file unchanged

**Requirement:** 22-REQ-1.E1
**Type:** unit
**Description:** If the AI API call raises an exception, the requirements file is not modified.

**Preconditions:**
- Mocked client raises `Exception("API timeout")`.
- Fixture `requirements.md` with known content.

**Input:**
- One finding for a vague criterion.

**Expected:**
- `rewrite_criteria()` returns empty dict.
- File content unchanged.

**Assertion pseudocode:**
```
original = req_path.read_text()
result = await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT result == {}
ASSERT req_path.read_text() == original
```

---

### TS-22-E2: Missing criterion ID skipped

**Requirement:** 22-REQ-1.E2
**Type:** unit
**Description:** If a criterion ID from the rewrite response doesn't exist in the file, skip it.

**Preconditions:**
- Fixture with criterion `99-REQ-1.1` only.

**Input:**
- `rewrites`: `{"99-REQ-1.1": "fixed text", "99-REQ-9.9": "phantom text"}`

**Expected:**
- One FixResult (for 1.1), not two.
- File does not contain "phantom text".

**Assertion pseudocode:**
```
results = fix_ai_criteria("spec", req_path, rewrites)
ASSERT len(results) == 1
content = req_path.read_text()
ASSERT "phantom text" NOT IN content
```

---

### TS-22-E3: Fenced JSON response parsed

**Requirement:** 22-REQ-2.E1
**Type:** unit
**Description:** JSON wrapped in markdown code fences is extracted and parsed.

**Preconditions:**
- Mocked response text: `` ```json\n{"rewrites": [...]}\n``` ``

**Input:**
- One finding.

**Expected:**
- `rewrite_criteria()` returns a non-empty dict.

**Assertion pseudocode:**
```
result = await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT len(result) > 0
```

---

### TS-22-E4: Omitted criterion in response

**Requirement:** 22-REQ-2.E2
**Type:** unit
**Description:** If the AI response rewrites some but not all requested criteria, only the returned ones are applied.

**Preconditions:**
- Two findings for criteria 1.1 and 1.2.
- Mocked response only contains rewrite for 1.1.

**Input:**
- Two findings.

**Expected:**
- Return dict has one entry (1.1), not two.

**Assertion pseudocode:**
```
result = await rewrite_criteria(spec_name, req_text, findings, model)
ASSERT "99-REQ-1.1" IN result
ASSERT "99-REQ-1.2" NOT IN result
```

---

### TS-22-E5: Re-validation does not re-rewrite

**Requirement:** 22-REQ-4.E1
**Type:** integration
**Description:** If a rewritten criterion is still flagged on re-validation, it appears as a remaining finding, not another rewrite attempt.

**Preconditions:**
- Mocked AI analysis always flags the criterion (even after rewrite).
- Mocked rewrite produces a replacement.

**Input:**
- CLI args: `lint-spec --ai --fix`

**Expected:**
- Rewrite is applied once.
- Re-validation reports the finding without invoking another rewrite.

**Assertion pseudocode:**
```
result = runner.invoke(lint_spec, ["--ai", "--fix"])
ASSERT rewrite_call_count == 1
ASSERT "vague-criterion" IN result.output  # still reported
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 22-REQ-1.1 | TS-22-1 | unit |
| 22-REQ-1.2 | TS-22-2 | unit |
| 22-REQ-1.3 | TS-22-3, TS-22-4 | unit |
| 22-REQ-1.4 | TS-22-5 | integration |
| 22-REQ-1.E1 | TS-22-E1 | unit |
| 22-REQ-1.E2 | TS-22-E2 | unit |
| 22-REQ-2.1 | TS-22-6 | unit |
| 22-REQ-2.2 | TS-22-13 | unit |
| 22-REQ-2.3 | TS-22-14 | unit |
| 22-REQ-2.4 | TS-22-7 | unit |
| 22-REQ-2.5 | TS-22-8 | unit |
| 22-REQ-2.E1 | TS-22-E3 | unit |
| 22-REQ-2.E2 | TS-22-E4 | unit |
| 22-REQ-3.1 | TS-22-9 | unit |
| 22-REQ-3.2 | TS-22-10 | unit |
| 22-REQ-3.3 | TS-22-12 | unit |
| 22-REQ-4.1 | TS-22-11 | unit |
| 22-REQ-4.2 | TS-22-15 | integration |
| 22-REQ-4.3 | TS-22-16 | unit |
| 22-REQ-4.4 | TS-22-17 | unit |
| 22-REQ-4.E1 | TS-22-E5 | integration |
| Property 1 | TS-22-P1 | property |
| Property 2 | TS-22-P2 | property |
| Property 5 | TS-22-P3 | property |
