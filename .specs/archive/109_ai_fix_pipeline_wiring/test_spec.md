# Test Specification: AI Fix Pipeline Wiring

## Overview

Tests validate the dispatch logic that wires existing AI generator and fixer
functions into the `lint-spec --ai --fix` pipeline. All AI calls are mocked --
no live API calls in tests. Tests cover dispatch correctness, ordering,
batching, error handling, and flag gating.

## Test Cases

### TS-109-1: AI fix results included in LintResult

**Requirement:** 109-REQ-1.1
**Type:** unit
**Description:** Verify that `_apply_ai_fixes()` returns FixResult objects
and they appear in `LintResult.fix_results`.

**Preconditions:**
- Mocked `rewrite_criteria()` returns one rewrite.
- Mocked `fix_ai_criteria()` returns one FixResult.
- Findings contain one `vague-criterion` finding.

**Input:**
- findings with one vague-criterion Finding for spec "test_spec"
- discovered specs list containing "test_spec" with a requirements.md fixture

**Expected:**
- `_apply_ai_fixes()` returns a list containing the FixResult.
- When called from `run_lint_specs(ai=True, fix=True)`, the FixResult appears
  in `LintResult.fix_results`.

**Assertion pseudocode:**
```
results = _apply_ai_fixes(findings, discovered, specs_dir)
ASSERT len(results) >= 1
ASSERT results[0].rule == "vague-criterion"
```

---

### TS-109-2: No AI fixes without --ai flag

**Requirement:** 109-REQ-1.2
**Type:** unit
**Description:** Verify that `run_lint_specs(fix=True, ai=False)` does not
invoke `_apply_ai_fixes()`.

**Preconditions:**
- Spec with a vague criterion that would be flagged by AI.
- Mocked AI functions.

**Input:**
- `run_lint_specs(specs_dir, fix=True, ai=False)`

**Expected:**
- `rewrite_criteria` is not called.
- `generate_test_spec_entries` is not called.

**Assertion pseudocode:**
```
result = run_lint_specs(specs_dir, fix=True, ai=False)
ASSERT mock_rewrite.call_count == 0
ASSERT mock_generate.call_count == 0
```

---

### TS-109-3: No AI fixes without --fix flag

**Requirement:** 109-REQ-1.3
**Type:** unit
**Description:** Verify that `run_lint_specs(ai=True, fix=False)` does not
invoke `_apply_ai_fixes()`.

**Preconditions:**
- Spec with a vague criterion.
- Mocked AI functions.

**Input:**
- `run_lint_specs(specs_dir, ai=True, fix=False)`

**Expected:**
- `rewrite_criteria` is not called.
- `fix_ai_criteria` is not called.

**Assertion pseudocode:**
```
result = run_lint_specs(specs_dir, ai=True, fix=False)
ASSERT mock_rewrite.call_count == 0
ASSERT mock_fix_ai.call_count == 0
```

---

### TS-109-4: Criteria rewrite dispatch for vague-criterion

**Requirement:** 109-REQ-2.1
**Type:** unit
**Description:** Verify that vague-criterion findings are dispatched to
`rewrite_criteria()` then `fix_ai_criteria()`.

**Preconditions:**
- One Finding with rule="vague-criterion", spec_name="s1",
  message="[01-REQ-1.1] Vague language detected"
- Mocked `rewrite_criteria()` returns `{"01-REQ-1.1": "improved text"}`
- Fixture requirements.md exists at spec path

**Input:**
- findings list with the vague-criterion Finding
- discovered specs containing "s1"

**Expected:**
- `rewrite_criteria()` called once with spec_name="s1", requirements text,
  findings list, and model ID.
- `fix_ai_criteria()` called once with rewrites={"01-REQ-1.1": "improved text"}
  and findings_map={"01-REQ-1.1": "vague-criterion"}.

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT mock_rewrite.call_count == 1
ASSERT mock_fix_ai.call_count == 1
ASSERT mock_fix_ai.call_args.kwargs["findings_map"] == {"01-REQ-1.1": "vague-criterion"}
```

---

### TS-109-5: findings_map built from finding messages

**Requirement:** 109-REQ-2.2
**Type:** unit
**Description:** Verify that `_apply_ai_fixes_async()` extracts criterion IDs
from finding messages and maps them to their rule names.

**Preconditions:**
- Two findings: vague-criterion for "01-REQ-1.1", implementation-leak for
  "01-REQ-2.3"
- Mocked `rewrite_criteria()` returns rewrites for both.

**Input:**
- findings with both findings for spec "s1"

**Expected:**
- `fix_ai_criteria()` receives findings_map:
  `{"01-REQ-1.1": "vague-criterion", "01-REQ-2.3": "implementation-leak"}`

**Assertion pseudocode:**
```
await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
fmap = mock_fix_ai.call_args.kwargs["findings_map"]
ASSERT fmap["01-REQ-1.1"] == "vague-criterion"
ASSERT fmap["01-REQ-2.3"] == "implementation-leak"
```

---

### TS-109-6: Batch splitting for criteria rewrites

**Requirement:** 109-REQ-2.3
**Type:** unit
**Description:** Verify that findings exceeding `_MAX_REWRITE_BATCH` are
split into multiple `rewrite_criteria()` calls.

**Preconditions:**
- 25 vague-criterion findings for spec "s1".
- `_MAX_REWRITE_BATCH` is 20.
- Mocked `rewrite_criteria()` returns one rewrite per batch.

**Input:**
- 25 findings for spec "s1"

**Expected:**
- `rewrite_criteria()` called exactly 2 times (batch of 20 + batch of 5).

**Assertion pseudocode:**
```
await _apply_ai_fixes_async(findings_25, discovered, specs_dir, model)
ASSERT mock_rewrite.call_count == 2
ASSERT len(mock_rewrite.call_args_list[0].kwargs["findings"]) == 20
ASSERT len(mock_rewrite.call_args_list[1].kwargs["findings"]) == 5
```

---

### TS-109-7: Test spec generation dispatch for untraced-requirement

**Requirement:** 109-REQ-3.1
**Type:** unit
**Description:** Verify that untraced-requirement findings are dispatched
to `generate_test_spec_entries()` then `fix_ai_test_spec_entries()`.

**Preconditions:**
- One Finding with rule="untraced-requirement", spec_name="s1",
  message="Requirement 01-REQ-1.1 is not referenced in test_spec.md"
- Mocked `generate_test_spec_entries()` returns
  `{"01-REQ-1.1": "### TS-01-99: ..."}`
- Fixture requirements.md and test_spec.md exist at spec path

**Input:**
- findings list with the untraced-requirement Finding

**Expected:**
- `generate_test_spec_entries()` called once with spec_name="s1",
  requirements text, test spec text, ["01-REQ-1.1"], and model ID.
- `fix_ai_test_spec_entries()` called once with entries dict.

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT mock_generate.call_count == 1
ASSERT mock_fix_ts.call_count == 1
ASSERT "01-REQ-1.1" IN mock_generate.call_args.kwargs["untraced_req_ids"]
```

---

### TS-109-8: Batch splitting for test spec generation

**Requirement:** 109-REQ-3.2
**Type:** unit
**Description:** Verify that untraced IDs exceeding `_MAX_UNTRACED_BATCH`
are split into multiple `generate_test_spec_entries()` calls.

**Preconditions:**
- 25 untraced-requirement findings for spec "s1".
- `_MAX_UNTRACED_BATCH` is 20.
- Mocked `generate_test_spec_entries()` returns one entry per batch.

**Input:**
- 25 findings for spec "s1"

**Expected:**
- `generate_test_spec_entries()` called exactly 2 times (20 + 5 IDs).

**Assertion pseudocode:**
```
await _apply_ai_fixes_async(findings_25, discovered, specs_dir, model)
ASSERT mock_generate.call_count == 2
```

---

### TS-109-9: STANDARD model tier used for AI calls

**Requirement:** 109-REQ-3.3
**Type:** unit
**Description:** Verify that the STANDARD-tier model ID is passed to both
AI generator functions.

**Preconditions:**
- Mocked `resolve_model("STANDARD")` returns a model with ID "standard-id".
- Findings for both rewrite and generation.

**Input:**
- Mixed findings (vague-criterion + untraced-requirement)

**Expected:**
- `rewrite_criteria()` called with model="standard-id".
- `generate_test_spec_entries()` called with model="standard-id".

**Assertion pseudocode:**
```
_apply_ai_fixes(findings, discovered, specs_dir)
ASSERT mock_rewrite.call_args.kwargs["model"] == "standard-id"
ASSERT mock_generate.call_args.kwargs["model"] == "standard-id"
```

---

### TS-109-10: Criteria rewrites execute before test spec generation

**Requirement:** 109-REQ-4.1
**Type:** unit
**Description:** Verify that for a spec with both types of findings,
`rewrite_criteria()` + `fix_ai_criteria()` complete before
`generate_test_spec_entries()` is called.

**Preconditions:**
- One vague-criterion finding and one untraced-requirement finding, both
  for spec "s1".
- Call order tracking on mocked functions.

**Input:**
- Both findings for spec "s1"

**Expected:**
- `fix_ai_criteria()` is called before `generate_test_spec_entries()`.

**Assertion pseudocode:**
```
call_order = []
mock_fix_ai.side_effect = lambda *a, **kw: call_order.append("fix_ai")
mock_generate.side_effect = lambda *a, **kw: call_order.append("generate")
await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT call_order.index("fix_ai") < call_order.index("generate")
```

---

### TS-109-11: AI fixes execute before mechanical fixes

**Requirement:** 109-REQ-4.2
**Type:** unit
**Description:** Verify that `_apply_ai_fixes()` is called before
`apply_fixes()` in `run_lint_specs()`.

**Preconditions:**
- Mocked `_apply_ai_fixes` and `apply_fixes` with call order tracking.
- Findings that trigger both AI and mechanical fixes.

**Input:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected:**
- `_apply_ai_fixes` called before `apply_fixes`.

**Assertion pseudocode:**
```
call_order = []
# patch both functions to record call order
run_lint_specs(specs_dir, ai=True, fix=True)
ASSERT call_order == ["_apply_ai_fixes", "apply_fixes"]
```

---

### TS-109-12: Re-validation after AI fixes

**Requirement:** 109-REQ-5.1
**Type:** unit
**Description:** Verify that when AI fixes produce results, the system
re-validates (static + AI).

**Preconditions:**
- `_apply_ai_fixes()` returns one FixResult.
- `validate_specs` and `_merge_ai_findings` are mocked to track calls.

**Input:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected:**
- `validate_specs()` called at least twice (initial + re-validation).
- `_merge_ai_findings()` called at least twice (initial + re-validation).

**Assertion pseudocode:**
```
run_lint_specs(specs_dir, ai=True, fix=True)
ASSERT mock_validate.call_count >= 2
ASSERT mock_merge_ai.call_count >= 2
```

---

### TS-109-13: No re-invocation of AI fixes during re-validation

**Requirement:** 109-REQ-5.2
**Type:** unit
**Description:** Verify that the re-validation pass does not trigger
another round of AI fixes.

**Preconditions:**
- `_apply_ai_fixes()` returns results on first call.
- Track call count.

**Input:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected:**
- `_apply_ai_fixes()` called exactly once.

**Assertion pseudocode:**
```
run_lint_specs(specs_dir, ai=True, fix=True)
ASSERT mock_apply_ai.call_count == 1
```

---

## Edge Case Tests

### TS-109-E1: No AI-fixable findings skips pipeline

**Requirement:** 109-REQ-1.E1
**Type:** unit
**Description:** When all findings have rules outside AI_FIXABLE_RULES,
the AI fix pipeline is skipped entirely.

**Preconditions:**
- Findings with only mechanical rules (e.g., "missing-verification").

**Input:**
- findings with no AI_FIXABLE_RULES matches

**Expected:**
- `_apply_ai_fixes()` returns empty list.
- No AI generator or fixer functions called.

**Assertion pseudocode:**
```
results = _apply_ai_fixes(findings, discovered, specs_dir)
ASSERT results == []
ASSERT mock_rewrite.call_count == 0
ASSERT mock_generate.call_count == 0
```

---

### TS-109-E2: Rewrite failure for one spec continues others

**Requirement:** 109-REQ-2.E1
**Type:** unit
**Description:** If `rewrite_criteria()` raises for spec "s1", spec "s2"
is still processed.

**Preconditions:**
- Two specs ("s1", "s2") each with a vague-criterion finding.
- `rewrite_criteria()` raises Exception for "s1", returns valid dict for "s2".

**Input:**
- findings for both specs

**Expected:**
- FixResult returned for "s2".
- Warning logged for "s1".

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT any(r.spec_name == "s2" for r in results)
ASSERT mock_logger_warning.called
```

---

### TS-109-E3: Empty rewrite dict skips fix_ai_criteria

**Requirement:** 109-REQ-2.E2
**Type:** unit
**Description:** When `rewrite_criteria()` returns `{}`, `fix_ai_criteria()`
is not called for that batch.

**Preconditions:**
- One vague-criterion finding.
- `rewrite_criteria()` returns `{}`.

**Input:**
- findings with one vague-criterion

**Expected:**
- `fix_ai_criteria()` not called.
- Empty results list.

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT mock_fix_ai.call_count == 0
ASSERT results == []
```

---

### TS-109-E4: Generation failure for one spec continues others

**Requirement:** 109-REQ-3.E1
**Type:** unit
**Description:** If `generate_test_spec_entries()` raises for spec "s1",
spec "s2" is still processed.

**Preconditions:**
- Two specs each with an untraced-requirement finding.
- `generate_test_spec_entries()` raises for "s1", returns valid dict for "s2".

**Input:**
- findings for both specs

**Expected:**
- FixResult returned for "s2".
- Warning logged for "s1".

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT any(r.spec_name == "s2" for r in results)
```

---

### TS-109-E5: Empty entries dict skips fix_ai_test_spec_entries

**Requirement:** 109-REQ-3.E2
**Type:** unit
**Description:** When `generate_test_spec_entries()` returns `{}`,
`fix_ai_test_spec_entries()` is not called.

**Preconditions:**
- One untraced-requirement finding.
- `generate_test_spec_entries()` returns `{}`.

**Input:**
- findings with one untraced-requirement

**Expected:**
- `fix_ai_test_spec_entries()` not called.

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT mock_fix_ts.call_count == 0
```

---

### TS-109-E6: Missing test_spec.md skips generation

**Requirement:** 109-REQ-3.E3
**Type:** unit
**Description:** When a spec has requirements.md but no test_spec.md,
test spec generation is skipped for that spec.

**Preconditions:**
- Spec "s1" with requirements.md but no test_spec.md.
- One untraced-requirement finding for "s1".

**Input:**
- findings for "s1"

**Expected:**
- `generate_test_spec_entries()` not called.
- No error raised.

**Assertion pseudocode:**
```
results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
ASSERT mock_generate.call_count == 0
ASSERT results == []
```

---

### TS-109-E7: Re-validation reports still-flagged criterion

**Requirement:** 109-REQ-5.E1
**Type:** integration
**Description:** If re-validation still flags a rewritten criterion, it
appears as a remaining finding without another rewrite.

**Preconditions:**
- `rewrite_criteria()` returns a rewrite for "01-REQ-1.1".
- `fix_ai_criteria()` applies it.
- Re-validation AI analysis still flags "01-REQ-1.1".

**Input:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected:**
- Final findings contain the vague-criterion finding for "01-REQ-1.1".
- `_apply_ai_fixes()` called exactly once (no re-fix).

**Assertion pseudocode:**
```
result = run_lint_specs(specs_dir, ai=True, fix=True)
ASSERT any(f.rule == "vague-criterion" for f in result.findings)
ASSERT mock_apply_ai.call_count == 1
```

---

## Property Test Cases

### TS-109-P1: AI fix isolation without --ai

**Property:** Property 1 from design.md
**Validates:** 109-REQ-1.2
**Type:** property
**Description:** For any set of findings, when ai=False, zero AI generator
calls are made regardless of finding rules.

**For any:** list of 0-20 findings with rules drawn from
AI_FIXABLE_RULES | FIXABLE_RULES
**Invariant:** `rewrite_criteria` and `generate_test_spec_entries` call
counts are zero.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(finding_strategy(), max_size=20):
    run_lint_specs(specs_dir, ai=False, fix=True)
    ASSERT mock_rewrite.call_count == 0
    ASSERT mock_generate.call_count == 0
```

---

### TS-109-P2: Dispatch correctness by rule

**Property:** Property 2 from design.md
**Validates:** 109-REQ-2.1, 109-REQ-3.1
**Type:** property
**Description:** For any finding, dispatch routes it to the correct
generator based on its rule name.

**For any:** single Finding with rule drawn from AI_FIXABLE_RULES
**Invariant:** If rule is vague-criterion or implementation-leak,
`rewrite_criteria` is called; if rule is untraced-requirement,
`generate_test_spec_entries` is called.

**Assertion pseudocode:**
```
FOR ANY rule IN sampled_from(AI_FIXABLE_RULES):
    finding = Finding(rule=rule, ...)
    await _apply_ai_fixes_async([finding], discovered, specs_dir, model)
    IF rule IN {"vague-criterion", "implementation-leak"}:
        ASSERT mock_rewrite.call_count == 1
        ASSERT mock_generate.call_count == 0
    ELSE:
        ASSERT mock_rewrite.call_count == 0
        ASSERT mock_generate.call_count == 1
```

---

### TS-109-P3: Ordering invariant

**Property:** Property 3 from design.md
**Validates:** 109-REQ-4.1
**Type:** property
**Description:** For any spec with both rewrite and generation findings,
rewrite completes before generation starts.

**For any:** spec with 1-5 vague-criterion findings and 1-5
untraced-requirement findings
**Invariant:** In the call order log, all `fix_ai_criteria` calls precede
all `generate_test_spec_entries` calls for the same spec.

**Assertion pseudocode:**
```
FOR ANY n_rewrite IN integers(1, 5):
    FOR ANY n_untraced IN integers(1, 5):
        call_log = []
        # ... set up mock tracking
        await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
        rewrite_idx = max(i for i, c in enumerate(call_log) if c == "fix_ai")
        gen_idx = min(i for i, c in enumerate(call_log) if c == "generate")
        ASSERT rewrite_idx < gen_idx
```

---

### TS-109-P4: Batch size bound

**Property:** Property 4 from design.md
**Validates:** 109-REQ-2.3, 109-REQ-3.2
**Type:** property
**Description:** For any number of findings N, the number of AI calls is
at most ceil(N / batch_limit).

**For any:** N findings (1-50) for a single spec, all with the same rule
**Invariant:** call_count <= ceil(N / batch_limit)

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 50):
    findings = [make_finding(rule="vague-criterion")] * n
    await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
    ASSERT mock_rewrite.call_count == ceil(n / _MAX_REWRITE_BATCH)
```

---

### TS-109-P5: Per-spec error isolation

**Property:** Property 5 from design.md
**Validates:** 109-REQ-2.E1, 109-REQ-3.E1
**Type:** property
**Description:** For any set of specs where one spec's AI call fails, all
other specs' fixes are still attempted.

**For any:** 2-5 specs, one of which is designated to fail
**Invariant:** FixResults from non-failing specs are still returned.

**Assertion pseudocode:**
```
FOR ANY n_specs IN integers(2, 5):
    FOR ANY fail_idx IN integers(0, n_specs - 1):
        # rewrite_criteria raises for spec at fail_idx, succeeds for others
        results = await _apply_ai_fixes_async(findings, discovered, specs_dir, model)
        successful_specs = {r.spec_name for r in results}
        ASSERT len(successful_specs) == n_specs - 1
```

---

### TS-109-P6: Single-pass fix guarantee

**Property:** Property 6 from design.md
**Validates:** 109-REQ-5.1, 109-REQ-5.2
**Type:** property
**Description:** For any run with AI fixes, the AI fix pipeline is invoked
at most once.

**For any:** findings list producing 0-10 AI FixResults
**Invariant:** `_apply_ai_fixes` call count is exactly 1 within
`run_lint_specs(ai=True, fix=True)`.

**Assertion pseudocode:**
```
FOR ANY n_results IN integers(0, 10):
    mock_apply_ai.return_value = [FixResult(...)] * n_results
    run_lint_specs(specs_dir, ai=True, fix=True)
    ASSERT mock_apply_ai.call_count == 1
```

---

## Integration Smoke Tests

### TS-109-SMOKE-1: Full criteria rewrite path

**Execution Path:** Path 1 from design.md
**Description:** End-to-end verification that `lint-spec --ai --fix`
dispatches vague-criterion findings through `rewrite_criteria()` to
`fix_ai_criteria()` and the rewrite appears in the spec file.

**Setup:**
- Fixture spec directory with a `requirements.md` containing a vague
  criterion: `[99-REQ-1.1] THE system SHALL be fast.`
- Mocked `rewrite_criteria()` returns
  `{"99-REQ-1.1": "THE system SHALL respond within 200ms at p95."}`
- Mocked `analyze_acceptance_criteria()` returns a vague-criterion Finding
  for "99-REQ-1.1".
- `fix_ai_criteria()` is NOT mocked -- it runs for real.

**Trigger:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected side effects:**
- `requirements.md` on disk contains "respond within 200ms" and no longer
  contains "be fast".
- `LintResult.fix_results` contains a FixResult with rule="vague-criterion".

**Must NOT satisfy with:**
- Mocking `fix_ai_criteria()` -- the real fixer must run to verify the
  file is actually modified.

**Assertion pseudocode:**
```
result = run_lint_specs(specs_dir, ai=True, fix=True)
content = (specs_dir / "99_test" / "requirements.md").read_text()
ASSERT "respond within 200ms" IN content
ASSERT "be fast" NOT IN content
ASSERT any(r.rule == "vague-criterion" for r in result.fix_results)
```

---

### TS-109-SMOKE-2: Full test spec generation path

**Execution Path:** Path 2 from design.md
**Description:** End-to-end verification that `lint-spec --ai --fix`
dispatches untraced-requirement findings through
`generate_test_spec_entries()` to `fix_ai_test_spec_entries()` and the
entry appears in the spec file.

**Setup:**
- Fixture spec directory with `requirements.md` containing requirement
  "99-REQ-1.1" and `test_spec.md` that does NOT reference "99-REQ-1.1".
- Static validation produces an untraced-requirement Finding.
- Mocked `generate_test_spec_entries()` returns
  `{"99-REQ-1.1": "### TS-99-42: Auto-generated test\n..."}`.
- `fix_ai_test_spec_entries()` is NOT mocked -- it runs for real.

**Trigger:**
- `run_lint_specs(specs_dir, ai=True, fix=True)`

**Expected side effects:**
- `test_spec.md` on disk contains "TS-99-42" entry text.
- `LintResult.fix_results` contains a FixResult with
  rule="untraced-requirement".

**Must NOT satisfy with:**
- Mocking `fix_ai_test_spec_entries()` -- the real fixer must run to
  verify the file is actually modified.

**Assertion pseudocode:**
```
result = run_lint_specs(specs_dir, ai=True, fix=True)
content = (specs_dir / "99_test" / "test_spec.md").read_text()
ASSERT "TS-99-42" IN content
ASSERT any(r.rule == "untraced-requirement" for r in result.fix_results)
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 109-REQ-1.1 | TS-109-1 | unit |
| 109-REQ-1.2 | TS-109-2 | unit |
| 109-REQ-1.3 | TS-109-3 | unit |
| 109-REQ-1.E1 | TS-109-E1 | unit |
| 109-REQ-2.1 | TS-109-4 | unit |
| 109-REQ-2.2 | TS-109-5 | unit |
| 109-REQ-2.3 | TS-109-6 | unit |
| 109-REQ-2.E1 | TS-109-E2 | unit |
| 109-REQ-2.E2 | TS-109-E3 | unit |
| 109-REQ-3.1 | TS-109-7 | unit |
| 109-REQ-3.2 | TS-109-8 | unit |
| 109-REQ-3.3 | TS-109-9 | unit |
| 109-REQ-3.E1 | TS-109-E4 | unit |
| 109-REQ-3.E2 | TS-109-E5 | unit |
| 109-REQ-3.E3 | TS-109-E6 | unit |
| 109-REQ-4.1 | TS-109-10 | unit |
| 109-REQ-4.2 | TS-109-11 | unit |
| 109-REQ-5.1 | TS-109-12 | unit |
| 109-REQ-5.2 | TS-109-13 | unit |
| 109-REQ-5.E1 | TS-109-E7 | integration |
| Property 1 | TS-109-P1 | property |
| Property 2 | TS-109-P2 | property |
| Property 3 | TS-109-P3 | property |
| Property 4 | TS-109-P4 | property |
| Property 5 | TS-109-P5 | property |
| Property 6 | TS-109-P6 | property |
| Path 1 | TS-109-SMOKE-1 | integration |
| Path 2 | TS-109-SMOKE-2 | integration |
