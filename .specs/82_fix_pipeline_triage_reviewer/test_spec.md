# Test Specification: Fix Pipeline Triage & Reviewer Archetypes

## Overview

Tests cover four areas: archetype registration, output parsing, issue comment
formatting, and the pipeline retry/escalation loop. Unit tests validate
individual functions; property tests validate parsing invariants; integration
smoke tests validate end-to-end pipeline flow with mock backends.

## Test Cases

### TS-82-1: Triage archetype registered in registry

**Requirement:** 82-REQ-1.1
**Type:** unit
**Description:** Verify that the archetype registry contains a `"triage"` entry
with the correct template, model tier, and read-only allowlist.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is importable from `agent_fox.archetypes`.

**Input:**
- Access `ARCHETYPE_REGISTRY["triage"]`.

**Expected:**
- Entry exists with `templates=["triage.md"]`,
  `default_model_tier="ADVANCED"`, and an allowlist containing only read-only
  commands (`ls`, `cat`, `git`, `wc`, `head`, `tail`).

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["triage"]
ASSERT entry.templates == ["triage.md"]
ASSERT entry.default_model_tier == "ADVANCED"
ASSERT "uv" NOT IN entry.default_allowlist
ASSERT "git" IN entry.default_allowlist
```

### TS-82-2: Triage system prompt loads template

**Requirement:** 82-REQ-1.2
**Type:** unit
**Description:** Verify that `build_system_prompt(archetype="triage")` loads
`triage.md` and interpolates `{spec_name}`.

**Preconditions:**
- `triage.md` template file exists in `_templates/prompts/`.

**Input:**
- `build_system_prompt(context="issue body", task_group=0, spec_name="fix-issue-42", archetype="triage")`

**Expected:**
- Returned string contains content from `triage.md` template.
- Returned string contains `"fix-issue-42"`.
- Returned string contains `"issue body"` in the context section.

**Assertion pseudocode:**
```
prompt = build_system_prompt(context="issue body", task_group=0, spec_name="fix-issue-42", archetype="triage")
ASSERT "fix-issue-42" IN prompt
ASSERT "issue body" IN prompt
ASSERT "TRIAGE" IN prompt.upper() OR "acceptance criteria" IN prompt.lower()
```

### TS-82-3: Parse valid triage JSON

**Requirement:** 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3
**Type:** unit
**Description:** Verify that `parse_triage_output()` correctly parses a
well-formed triage JSON into a `TriageResult`.

**Preconditions:**
- None.

**Input:**
```json
{
  "summary": "Bug in engine loop",
  "affected_files": ["agent_fox/engine.py"],
  "acceptance_criteria": [
    {
      "id": "AC-1",
      "description": "Engine handles empty queue",
      "preconditions": "Queue is empty",
      "expected": "Engine returns without error",
      "assertion": "Return value is None"
    }
  ]
}
```

**Expected:**
- `TriageResult` with `summary="Bug in engine loop"`,
  `affected_files=["agent_fox/engine.py"]`, one criterion with all five
  fields populated.

**Assertion pseudocode:**
```
result = parse_triage_output(json_string, "fix-issue-1", "session-1")
ASSERT result.summary == "Bug in engine loop"
ASSERT result.affected_files == ["agent_fox/engine.py"]
ASSERT len(result.criteria) == 1
ASSERT result.criteria[0].id == "AC-1"
ASSERT result.criteria[0].description == "Engine handles empty queue"
ASSERT result.criteria[0].preconditions == "Queue is empty"
ASSERT result.criteria[0].expected == "Engine returns without error"
ASSERT result.criteria[0].assertion == "Return value is None"
```

### TS-82-4: Parse triage JSON skips incomplete criteria

**Requirement:** 82-REQ-2.2
**Type:** unit
**Description:** Verify that criteria missing required fields are excluded.

**Preconditions:**
- None.

**Input:**
```json
{
  "summary": "Summary",
  "affected_files": [],
  "acceptance_criteria": [
    {"id": "AC-1", "description": "Good", "preconditions": "P", "expected": "E", "assertion": "A"},
    {"id": "AC-2", "description": "Missing fields"}
  ]
}
```

**Expected:**
- `TriageResult` with exactly one criterion (AC-1). AC-2 is excluded.

**Assertion pseudocode:**
```
result = parse_triage_output(json_string, "fix-issue-1", "s1")
ASSERT len(result.criteria) == 1
ASSERT result.criteria[0].id == "AC-1"
```

### TS-82-5: Parse triage output returns empty on invalid JSON

**Requirement:** 82-REQ-2.E1
**Type:** unit
**Description:** Verify graceful fallback on unparseable triage output.

**Preconditions:**
- None.

**Input:**
- `"This is not JSON at all, just some markdown text"`

**Expected:**
- Empty `TriageResult` (summary="", affected_files=[], criteria=[]).

**Assertion pseudocode:**
```
result = parse_triage_output("not json", "fix-issue-1", "s1")
ASSERT result.summary == ""
ASSERT result.criteria == []
```

### TS-82-6: Fix reviewer archetype registered in registry

**Requirement:** 82-REQ-4.1
**Type:** unit
**Description:** Verify that the archetype registry contains a
`"fix_reviewer"` entry with the correct template, model tier, and allowlist
that includes test-running commands.

**Preconditions:**
- `ARCHETYPE_REGISTRY` is importable.

**Input:**
- Access `ARCHETYPE_REGISTRY["fix_reviewer"]`.

**Expected:**
- Entry exists with `templates=["fix_reviewer.md"]`,
  `default_model_tier="ADVANCED"`, and an allowlist that includes `uv` and
  `make`.

**Assertion pseudocode:**
```
entry = ARCHETYPE_REGISTRY["fix_reviewer"]
ASSERT entry.templates == ["fix_reviewer.md"]
ASSERT entry.default_model_tier == "ADVANCED"
ASSERT "uv" IN entry.default_allowlist
ASSERT "make" IN entry.default_allowlist
```

### TS-82-7: Fix reviewer system prompt loads template

**Requirement:** 82-REQ-4.2
**Type:** unit
**Description:** Verify that `build_system_prompt(archetype="fix_reviewer")`
loads `fix_reviewer.md` and interpolates `{spec_name}`.

**Preconditions:**
- `fix_reviewer.md` template file exists in `_templates/prompts/`.

**Input:**
- `build_system_prompt(context="criteria context", task_group=0, spec_name="fix-issue-99", archetype="fix_reviewer")`

**Expected:**
- Returned string contains content from `fix_reviewer.md`.
- Returned string contains `"fix-issue-99"`.

**Assertion pseudocode:**
```
prompt = build_system_prompt(context="criteria context", task_group=0, spec_name="fix-issue-99", archetype="fix_reviewer")
ASSERT "fix-issue-99" IN prompt
ASSERT "criteria context" IN prompt
ASSERT "verdict" IN prompt.lower()
```

### TS-82-8: Parse valid fix reviewer JSON

**Requirement:** 82-REQ-5.1
**Type:** unit
**Description:** Verify that `parse_fix_review_output()` correctly parses a
well-formed reviewer JSON into a `FixReviewResult`.

**Preconditions:**
- None.

**Input:**
```json
{
  "verdicts": [
    {"criterion_id": "AC-1", "verdict": "PASS", "evidence": "Test passes"},
    {"criterion_id": "AC-2", "verdict": "FAIL", "evidence": "Function returns wrong value"}
  ],
  "overall_verdict": "FAIL",
  "summary": "1 of 2 criteria failed"
}
```

**Expected:**
- `FixReviewResult` with two verdicts, overall_verdict="FAIL",
  summary="1 of 2 criteria failed".

**Assertion pseudocode:**
```
result = parse_fix_review_output(json_string, "fix-issue-1", "s1")
ASSERT len(result.verdicts) == 2
ASSERT result.verdicts[0].criterion_id == "AC-1"
ASSERT result.verdicts[0].verdict == "PASS"
ASSERT result.verdicts[1].verdict == "FAIL"
ASSERT result.overall_verdict == "FAIL"
```

### TS-82-9: Parse reviewer output defaults to FAIL on invalid JSON

**Requirement:** 82-REQ-5.1
**Type:** unit
**Description:** Verify that unparseable reviewer output is treated as FAIL.

**Preconditions:**
- None.

**Input:**
- `"Some markdown prose, no JSON"`

**Expected:**
- `FixReviewResult` with overall_verdict="FAIL", empty verdicts.

**Assertion pseudocode:**
```
result = parse_fix_review_output("no json", "fix-issue-1", "s1")
ASSERT result.overall_verdict == "FAIL"
ASSERT result.verdicts == []
```

### TS-82-10: Pipeline runs triage-coder-reviewer sequence

**Requirement:** 82-REQ-7.1
**Type:** unit
**Description:** Verify that `process_issue()` invokes archetypes in the
correct order.

**Preconditions:**
- `FixPipeline` with mocked `_run_session` and `GitHubPlatform`.

**Input:**
- A mock issue with title and body.
- `_run_session` returns mock `SessionOutcome` for each archetype.
- Triage outcome contains valid JSON with one criterion.
- Reviewer outcome contains PASS verdict.

**Expected:**
- `_run_session` called with archetypes in order: triage first, then coder,
  then fix_reviewer. (Coder may be called via a dedicated method but must
  appear between triage and reviewer.)

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, mock_platform)
pipeline._run_session = mock_run_session
await pipeline.process_issue(issue, issue_body="fix the bug")
archetypes_called = [call.args[0] for call in mock_run_session.calls]
ASSERT archetypes_called[0] == "triage"
ASSERT "coder" in archetypes_called  # may be via _run_coder_session
ASSERT archetypes_called[-1] == "fix_reviewer"
```

### TS-82-11: Coder prompt includes triage criteria

**Requirement:** 82-REQ-7.2
**Type:** unit
**Description:** Verify that the coder's system prompt includes triage
acceptance criteria.

**Preconditions:**
- A `TriageResult` with two criteria.

**Input:**
- Call `_build_coder_prompt(spec, triage_result)`.

**Expected:**
- System prompt contains "AC-1" and "AC-2".
- System prompt contains the descriptions of both criteria.

**Assertion pseudocode:**
```
system_prompt, task_prompt = pipeline._build_coder_prompt(spec, triage_result)
ASSERT "AC-1" IN system_prompt
ASSERT "AC-2" IN system_prompt
ASSERT triage_result.criteria[0].description IN system_prompt
```

### TS-82-12: Reviewer prompt includes triage criteria

**Requirement:** 82-REQ-7.3, 82-REQ-5.3
**Type:** unit
**Description:** Verify that the reviewer's system prompt includes triage
acceptance criteria for verification.

**Preconditions:**
- A `TriageResult` with criteria.

**Input:**
- Call `_build_reviewer_prompt(spec, triage_result)`.

**Expected:**
- System prompt contains the criterion IDs and descriptions.

**Assertion pseudocode:**
```
system_prompt, task_prompt = pipeline._build_reviewer_prompt(spec, triage_result)
ASSERT "AC-1" IN system_prompt
ASSERT triage_result.criteria[0].description IN system_prompt
```

### TS-82-13: Triage comment posted to issue

**Requirement:** 82-REQ-3.1
**Type:** unit
**Description:** Verify that the triage report is posted as a comment.

**Preconditions:**
- Mock `GitHubPlatform` with spied `add_issue_comment`.

**Input:**
- Run pipeline with valid triage output.

**Expected:**
- `add_issue_comment` called with issue number and a string containing
  the summary and criterion descriptions in markdown.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue, issue_body="bug")
comment = mock_platform.add_issue_comment.calls[1].args[1]  # [0] is "Starting fix..."
ASSERT "AC-1" IN comment
ASSERT "## Triage" IN comment OR "## Acceptance Criteria" IN comment
```

### TS-82-14: Reviewer comment posted to issue

**Requirement:** 82-REQ-6.1
**Type:** unit
**Description:** Verify that the review report is posted as a comment.

**Preconditions:**
- Mock `GitHubPlatform`, reviewer returns PASS verdict.

**Input:**
- Run pipeline to completion (PASS).

**Expected:**
- `add_issue_comment` called with a comment containing the overall verdict
  and per-criterion results.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue, issue_body="bug")
comments = [c.args[1] for c in mock_platform.add_issue_comment.calls]
review_comment = [c for c in comments if "PASS" in c or "verdict" in c.lower()]
ASSERT len(review_comment) >= 1
ASSERT "AC-1" IN review_comment[0]
```

### TS-82-15: Coder retried on reviewer FAIL with feedback

**Requirement:** 82-REQ-8.1
**Type:** unit
**Description:** Verify that reviewer FAIL triggers coder retry with evidence.

**Preconditions:**
- Mock pipeline: reviewer returns FAIL on first call, PASS on second.
- `max_retries >= 1`.

**Input:**
- Run pipeline.

**Expected:**
- Coder called twice. Second coder call's task prompt contains the
  reviewer's evidence text.

**Assertion pseudocode:**
```
coder_prompts = [call for call in mock_calls if call.archetype == "coder"]
ASSERT len(coder_prompts) == 2
ASSERT "Function returns wrong value" IN coder_prompts[1].task_prompt
```

### TS-82-16: Model escalation on repeated FAIL

**Requirement:** 82-REQ-8.2, 82-REQ-8.3
**Type:** unit
**Description:** Verify that the pipeline escalates the model tier after
`retries_before_escalation` consecutive FAILs.

**Preconditions:**
- Config: `retries_before_escalation=1`, `max_retries=3`.
- Reviewer always returns FAIL.
- Mock `resolve_model` to track which tier is requested.

**Input:**
- Run pipeline.

**Expected:**
- First coder attempt uses starting tier (e.g. STANDARD).
- After 1 failure + 1 retry at STANDARD, escalates to ADVANCED.
- Model ID passed to coder changes after escalation.

**Assertion pseudocode:**
```
tiers_used = [call.model_tier for call in coder_calls]
ASSERT tiers_used[0] != tiers_used[-1]  # escalation occurred
```

### TS-82-17: Pipeline stops and posts failure on exhaustion

**Requirement:** 82-REQ-8.4
**Type:** unit
**Description:** Verify that pipeline posts failure comment when ladder is
exhausted.

**Preconditions:**
- Config: `max_retries=1`, `retries_before_escalation=1`.
- Reviewer always returns FAIL.
- Mock platform.

**Input:**
- Run pipeline.

**Expected:**
- Pipeline returns without raising.
- `add_issue_comment` called with a comment containing failure indication.
- Issue is NOT closed (no `close_issue` call).

**Assertion pseudocode:**
```
await pipeline.process_issue(issue, issue_body="bug")
comments = [c.args[1] for c in mock_platform.add_issue_comment.calls]
failure_comments = [c for c in comments if "failed" in c.lower() or "exhausted" in c.lower()]
ASSERT len(failure_comments) >= 1
ASSERT mock_platform.close_issue.call_count == 0
```

### TS-82-18: Triage failure does not block pipeline

**Requirement:** 82-REQ-7.E1
**Type:** unit
**Description:** Verify that a triage session failure allows the coder to
proceed with issue body only.

**Preconditions:**
- Mock `_run_session("triage")` to raise `Exception("timeout")`.

**Input:**
- Run pipeline.

**Expected:**
- Pipeline does not raise.
- Coder session is still called (with empty criteria).
- Warning is logged.

**Assertion pseudocode:**
```
pipeline._run_session = mock_that_raises_for_triage
await pipeline.process_issue(issue, issue_body="bug")
ASSERT coder_was_called
ASSERT "triage" NOT IN [c.archetype for c in successful_sessions]  # triage failed
```

### TS-82-19: Comment posting failure does not block pipeline

**Requirement:** 82-REQ-3.E1, 82-REQ-6.E1
**Type:** unit
**Description:** Verify that comment posting failures are logged but do not
stop the pipeline.

**Preconditions:**
- Mock `add_issue_comment` to raise `IntegrationError`.

**Input:**
- Run pipeline with valid triage and PASS reviewer result.

**Expected:**
- Pipeline completes successfully (returns metrics).
- No exception raised.

**Assertion pseudocode:**
```
mock_platform.add_issue_comment = raises(IntegrationError("API error"))
metrics = await pipeline.process_issue(issue, issue_body="bug")
ASSERT metrics.sessions_run >= 2  # at least coder + reviewer ran
```

### TS-82-20: Only coder is retried, not triage or reviewer

**Requirement:** 82-REQ-8.E1
**Type:** unit
**Description:** Verify that triage runs exactly once and the reviewer is not
independently retried.

**Preconditions:**
- Reviewer returns FAIL twice, then PASS on third coder attempt.

**Input:**
- Run pipeline.

**Expected:**
- Triage called exactly once.
- Reviewer called three times (once per coder attempt).
- Coder called three times.

**Assertion pseudocode:**
```
counts = Counter(call.archetype for call in all_session_calls)
ASSERT counts["triage"] == 1
ASSERT counts["coder"] == 3
ASSERT counts["fix_reviewer"] == 3
```

## Edge Case Tests

### TS-82-E1: Triage output with empty criteria array

**Requirement:** 82-REQ-2.E1
**Type:** unit
**Description:** Verify that an empty acceptance_criteria array produces an
empty TriageResult.

**Preconditions:**
- None.

**Input:**
```json
{"summary": "unclear", "affected_files": [], "acceptance_criteria": []}
```

**Expected:**
- `TriageResult` with empty criteria list, summary="unclear".

**Assertion pseudocode:**
```
result = parse_triage_output(json_string, "fix-issue-1", "s1")
ASSERT result.criteria == []
ASSERT result.summary == "unclear"
```

### TS-82-E2: Reviewer with no triage criteria falls back to issue text

**Requirement:** 82-REQ-5.E1
**Type:** unit
**Description:** Verify reviewer prompt adaptation when no criteria exist.

**Preconditions:**
- Empty `TriageResult`.

**Input:**
- Call `_build_reviewer_prompt(spec, empty_triage_result)`.

**Expected:**
- Prompt instructs the reviewer to verify based on the issue description.
- Prompt contains the issue body text.

**Assertion pseudocode:**
```
system_prompt, _ = pipeline._build_reviewer_prompt(spec, empty_triage)
ASSERT "issue description" IN system_prompt.lower() OR spec.system_context IN system_prompt
```

### TS-82-E3: Triage JSON wrapped in markdown fences

**Requirement:** 82-REQ-2.1
**Type:** unit
**Description:** Verify that triage JSON inside markdown code fences is still
parsed correctly (fallback path).

**Preconditions:**
- None.

**Input:**
````
Here is my analysis:
```json
{"summary": "found it", "affected_files": [], "acceptance_criteria": [{"id": "AC-1", "description": "d", "preconditions": "p", "expected": "e", "assertion": "a"}]}
```
````

**Expected:**
- `TriageResult` with one criterion parsed successfully.

**Assertion pseudocode:**
```
result = parse_triage_output(fenced_json, "fix-issue-1", "s1")
ASSERT len(result.criteria) == 1
ASSERT result.criteria[0].id == "AC-1"
```

### TS-82-E4: Reviewer JSON with unknown verdict value

**Requirement:** 82-REQ-5.1
**Type:** unit
**Description:** Verify that verdicts with invalid verdict values (not
PASS/FAIL) are excluded.

**Preconditions:**
- None.

**Input:**
```json
{
  "verdicts": [
    {"criterion_id": "AC-1", "verdict": "MAYBE", "evidence": "unsure"},
    {"criterion_id": "AC-2", "verdict": "PASS", "evidence": "ok"}
  ],
  "overall_verdict": "PASS",
  "summary": "mixed"
}
```

**Expected:**
- Only AC-2 is included in parsed result. AC-1 is excluded.

**Assertion pseudocode:**
```
result = parse_fix_review_output(json_string, "fix-issue-1", "s1")
ASSERT len(result.verdicts) == 1
ASSERT result.verdicts[0].criterion_id == "AC-2"
```

## Property Test Cases

### TS-82-P1: Triage criteria field completeness

**Property:** Property 1 from design.md
**Validates:** 82-REQ-2.1, 82-REQ-2.2
**Type:** property
**Description:** For any generated triage JSON, all parsed criteria contain
all five required fields.

**For any:** JSON object with `acceptance_criteria` array where each element
is a dict with a random subset of the five required keys (`id`,
`description`, `preconditions`, `expected`, `assertion`) plus random string
values.

**Invariant:** Every criterion in the parsed `TriageResult.criteria` has all
five fields as non-empty strings. Criteria missing any field are excluded.

**Assertion pseudocode:**
```
FOR ANY criteria_dicts IN lists(dicts_with_random_subset_of_keys):
    json_str = json.dumps({"summary": "s", "affected_files": [], "acceptance_criteria": criteria_dicts})
    result = parse_triage_output(json_str, "fix-issue-1", "s1")
    FOR EACH criterion IN result.criteria:
        ASSERT criterion.id != ""
        ASSERT criterion.description != ""
        ASSERT criterion.preconditions != ""
        ASSERT criterion.expected != ""
        ASSERT criterion.assertion != ""
    # Count: only criteria with all 5 fields are included
    complete = [c for c in criteria_dicts if all(k in c for k in REQUIRED_KEYS)]
    ASSERT len(result.criteria) == len(complete)
```

### TS-82-P2: Reviewer verdict validation

**Property:** Property 2 from design.md
**Validates:** 82-REQ-5.1, 82-REQ-5.3
**Type:** property
**Description:** For any generated reviewer JSON, all parsed verdicts have
valid verdict values and overall_verdict is FAIL if any individual is FAIL.

**For any:** JSON object with `verdicts` array where each element has
`criterion_id`, `verdict` (drawn from `{"PASS", "FAIL", "MAYBE", ""}`) and
`evidence`.

**Invariant:** Every verdict in the parsed result has verdict in
`{"PASS", "FAIL"}`. If any parsed verdict is FAIL, overall_verdict is FAIL.

**Assertion pseudocode:**
```
FOR ANY verdict_dicts IN lists(dicts_with_random_verdict_values):
    json_str = json.dumps({"verdicts": verdict_dicts, "overall_verdict": "PASS", "summary": "s"})
    result = parse_fix_review_output(json_str, "fix-issue-1", "s1")
    FOR EACH v IN result.verdicts:
        ASSERT v.verdict IN {"PASS", "FAIL"}
    IF any(v.verdict == "FAIL" for v in result.verdicts):
        ASSERT result.overall_verdict == "FAIL"
```

### TS-82-P3: Escalation ladder consistency

**Property:** Property 3 from design.md
**Validates:** 82-REQ-8.2, 82-REQ-8.3, 82-REQ-8.4
**Type:** property
**Description:** For any sequence of N FAIL verdicts, the pipeline's
escalation state matches a fresh EscalationLadder after N failures.

**For any:** `n` in range(1, 10), `retries_before_escalation` in {0, 1, 2},
`max_retries` in range(1, 6).

**Invariant:** After N failures, the ladder's `current_tier`,
`is_exhausted`, and `escalation_count` match the reference ladder.

**Assertion pseudocode:**
```
FOR ANY n, retries_before, max_retries IN valid_ranges:
    ref_ladder = EscalationLadder(starting_tier, ceiling, retries_before, max_retries)
    FOR i IN range(n):
        ref_ladder.record_failure()
    # Pipeline ladder after n FAILs should match
    ASSERT pipeline_ladder.current_tier == ref_ladder.current_tier
    ASSERT pipeline_ladder.is_exhausted == ref_ladder.is_exhausted
    ASSERT pipeline_ladder.escalation_count == ref_ladder.escalation_count
```

### TS-82-P4: Retry feedback injection

**Property:** Property 4 from design.md
**Validates:** 82-REQ-8.1
**Type:** property
**Description:** For any FAIL verdict, the next coder prompt contains all
FAIL evidence.

**For any:** `FixReviewResult` with 1-5 verdicts, random subset being FAILs
with random evidence strings.

**Invariant:** The coder's task prompt on retry contains the evidence text
of every FAIL verdict.

**Assertion pseudocode:**
```
FOR ANY review_result IN fix_review_results_with_fails:
    _, task_prompt = pipeline._build_coder_prompt(spec, triage, review_feedback=review_result)
    FOR EACH v IN review_result.verdicts:
        IF v.verdict == "FAIL":
            ASSERT v.evidence IN task_prompt
```

## Integration Smoke Tests

### TS-82-SMOKE-1: Full pipeline happy path

**Execution Path:** Paths 1, 2, 3 from design.md
**Description:** End-to-end pipeline run with triage, coder, and reviewer all
succeeding on the first attempt.

**Setup:**
- Mock `GitHubPlatform` (external I/O).
- Mock agent backend (`run_session`) to return canned responses:
  - triage: valid JSON with 2 acceptance criteria
  - coder: completed outcome
  - fix_reviewer: PASS verdict for both criteria
- Mock `_create_fix_branch`, `_harvest_and_push` (git I/O).

**Trigger:**
- `await pipeline.process_issue(issue, issue_body="bug description")`

**Expected side effects:**
- `add_issue_comment` called 4 times: (1) "Starting fix...",
  (2) triage report, (3) review report, (4) closing comment via
  `close_issue`.
- Triage comment contains "AC-1" and "AC-2".
- Review comment contains "PASS".
- `close_issue` called once.

**Must NOT satisfy with:**
- Mocking `parse_triage_output` or `parse_fix_review_output` — parsing must
  use real code.

**Assertion pseudocode:**
```
platform = MockPlatform()
pipeline = FixPipeline(config, platform)
pipeline._run_session = mock_backend_responses
pipeline._create_fix_branch = AsyncMock()
pipeline._harvest_and_push = AsyncMock(return_value=True)
metrics = await pipeline.process_issue(issue, issue_body="bug description")
ASSERT platform.add_issue_comment.call_count >= 3
ASSERT platform.close_issue.call_count == 1
ASSERT metrics.sessions_run == 3  # triage + coder + reviewer
```

### TS-82-SMOKE-2: Retry loop with escalation

**Execution Path:** Path 4 from design.md
**Description:** End-to-end pipeline run where the reviewer FAILs twice,
escalation occurs, and the third attempt passes.

**Setup:**
- Mock platform and backend.
- Config: `retries_before_escalation=1`, `max_retries=3`.
- Reviewer responses: FAIL, FAIL, PASS (in sequence).
- Track model IDs passed to coder sessions.

**Trigger:**
- `await pipeline.process_issue(issue, issue_body="hard bug")`

**Expected side effects:**
- Coder called 3 times.
- Reviewer called 3 times.
- Model tier changes after second FAIL (escalation).
- Final review comment contains "PASS".
- `close_issue` called once.

**Must NOT satisfy with:**
- Mocking `EscalationLadder` — real ladder must be used.

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, platform)
# ... setup mock responses ...
metrics = await pipeline.process_issue(issue, issue_body="hard bug")
ASSERT metrics.sessions_run == 7  # 1 triage + 3 coder + 3 reviewer
ASSERT model_ids_used[0] != model_ids_used[2]  # escalation occurred
ASSERT platform.close_issue.call_count == 1
```

### TS-82-SMOKE-3: Triage failure with graceful fallback

**Execution Path:** Paths 2, 3 with Path 1 failing
**Description:** Pipeline continues when triage session fails, using issue
body only.

**Setup:**
- Mock platform and backend.
- Triage `_run_session` raises `Exception("backend error")`.
- Coder and reviewer succeed.

**Trigger:**
- `await pipeline.process_issue(issue, issue_body="simple bug")`

**Expected side effects:**
- Pipeline completes without raising.
- Coder called with issue body but no acceptance criteria in prompt.
- Reviewer runs and produces verdict.
- `close_issue` called once.

**Must NOT satisfy with:**
- Skipping the triage attempt entirely — it must be attempted and fail.

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, platform)
pipeline._run_session = mock_that_raises_for_triage_only
metrics = await pipeline.process_issue(issue, issue_body="simple bug")
ASSERT metrics.sessions_run >= 2  # coder + reviewer
ASSERT platform.close_issue.call_count == 1
```

### TS-82-P5: Pipeline archetype sequence

**Property:** Property 5 from design.md
**Validates:** 82-REQ-7.1, 82-REQ-8.4
**Type:** property
**Description:** For any pipeline invocation that completes, the archetype
execution sequence starts with triage and ends with fix_reviewer PASS or
ladder exhaustion.

**For any:** Pipeline run with 0-5 reviewer FAILs before PASS (or
exhaustion), using random `max_retries` in {1..4}.

**Invariant:** The first archetype invoked is always `"triage"`. On success,
the last archetype invoked is `"fix_reviewer"` with overall_verdict PASS. On
exhaustion, `is_exhausted` is true and no further coder sessions run.

**Assertion pseudocode:**
```
FOR ANY n_fails IN range(0, 5), max_retries IN range(1, 5):
    archetypes_called = run_pipeline_recording_archetypes(n_fails, max_retries)
    ASSERT archetypes_called[0] == "triage"
    IF n_fails < max_retries:
        ASSERT archetypes_called[-1] == "fix_reviewer"
```

### TS-82-P6: Comment posting resilience

**Property:** Property 6 from design.md
**Validates:** 82-REQ-3.E1, 82-REQ-6.E1
**Type:** property
**Description:** For any comment posting failure, the pipeline continues
without raising.

**For any:** Pipeline run where `add_issue_comment` raises an exception on a
random subset of calls (0 to all calls).

**Invariant:** The pipeline returns a `FixMetrics` object without raising,
regardless of which comment posts fail. The number of archetype sessions
run is unaffected by comment failures.

**Assertion pseudocode:**
```
FOR ANY failing_indices IN subsets(range(total_comment_calls)):
    platform = MockPlatform(fail_on=failing_indices)
    metrics = await pipeline.process_issue(issue, issue_body="bug")
    ASSERT metrics is not None
    ASSERT metrics.sessions_run >= 2  # at least coder + reviewer
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 82-REQ-1.1 | TS-82-1 | unit |
| 82-REQ-1.2 | TS-82-2 | unit |
| 82-REQ-2.1 | TS-82-3, TS-82-E3 | unit |
| 82-REQ-2.2 | TS-82-3, TS-82-4 | unit |
| 82-REQ-2.3 | TS-82-3 | unit |
| 82-REQ-2.4 | TS-82-2 | unit |
| 82-REQ-2.E1 | TS-82-5, TS-82-E1 | unit |
| 82-REQ-3.1 | TS-82-13 | unit |
| 82-REQ-3.E1 | TS-82-19 | unit |
| 82-REQ-4.1 | TS-82-6 | unit |
| 82-REQ-4.2 | TS-82-7 | unit |
| 82-REQ-5.1 | TS-82-8, TS-82-9, TS-82-E4 | unit |
| 82-REQ-5.2 | TS-82-SMOKE-1 | integration |
| 82-REQ-5.3 | TS-82-12 | unit |
| 82-REQ-5.E1 | TS-82-E2 | unit |
| 82-REQ-6.1 | TS-82-14 | unit |
| 82-REQ-6.E1 | TS-82-19 | unit |
| 82-REQ-7.1 | TS-82-10 | unit |
| 82-REQ-7.2 | TS-82-11 | unit |
| 82-REQ-7.3 | TS-82-12 | unit |
| 82-REQ-7.E1 | TS-82-18 | unit |
| 82-REQ-8.1 | TS-82-15 | unit |
| 82-REQ-8.2 | TS-82-16 | unit |
| 82-REQ-8.3 | TS-82-16 | unit |
| 82-REQ-8.4 | TS-82-17 | unit |
| 82-REQ-8.E1 | TS-82-20 | unit |
| Property 1 | TS-82-P1 | property |
| Property 2 | TS-82-P2 | property |
| Property 3 | TS-82-P3 | property |
| Property 4 | TS-82-P4 | property |
| Property 5 | TS-82-P5 | property |
| Property 6 | TS-82-P6 | property |
| Path 1+2+3 | TS-82-SMOKE-1 | integration |
| Path 4 | TS-82-SMOKE-2 | integration |
| Path 1 fail | TS-82-SMOKE-3 | integration |
