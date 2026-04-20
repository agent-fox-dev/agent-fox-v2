# Test Specification: Auto-Improve

## Overview

Tests for the auto-improve extension to `agent-fox fix`: CLI option validation,
analyzer prompt building and response parsing, improvement filtering, coder
session integration, verifier verdict parsing, rollback logic, improve loop
termination, oracle context enrichment, and combined report rendering. Tests
map to requirements in `requirements.md` and correctness properties in
`design.md`.

All session invocations are mocked. AI model calls are mocked. Git commands
are mocked. No external processes, API calls, or file system mutations beyond
temp directories are made during testing.

## Test Cases

### TS-31-1: --auto flag enables Phase 2 after all-green

**Requirement:** 31-REQ-1.1, 31-REQ-2.1
**Type:** unit
**Description:** Verify that when `--auto` is set and Phase 1 achieves
ALL_FIXED, Phase 2 (improve loop) is invoked.

**Preconditions:**
- Mock Phase 1 (`run_fix_loop`) to return `TerminationReason.ALL_FIXED`.
- Mock Phase 2 (`run_improve_loop`) to return a default `ImproveResult`.

**Input:**
- CLI invocation: `["fix", "--auto"]`

**Expected:**
- `run_improve_loop` is called exactly once.
- Exit code is 0.

**Assertion pseudocode:**
```
WITH mock run_fix_loop RETURNING ALL_FIXED:
WITH mock run_improve_loop RETURNING converged_result:
    result = cli_runner.invoke(fix_cmd, ["--auto"])
    ASSERT result.exit_code == 0
    ASSERT run_improve_loop.called
```

---

### TS-31-2: Phase 2 skipped when Phase 1 not all-green

**Requirement:** 31-REQ-1.4, 31-REQ-2.1
**Type:** unit
**Description:** Verify Phase 2 does not run when Phase 1 terminates with
MAX_PASSES.

**Preconditions:**
- Mock Phase 1 to return `TerminationReason.MAX_PASSES`.

**Input:**
- CLI invocation: `["fix", "--auto"]`

**Expected:**
- `run_improve_loop` is NOT called.
- Exit code is 1.

**Assertion pseudocode:**
```
WITH mock run_fix_loop RETURNING MAX_PASSES:
    result = cli_runner.invoke(fix_cmd, ["--auto"])
    ASSERT result.exit_code == 1
    ASSERT NOT run_improve_loop.called
```

---

### TS-31-3: --improve-passes without --auto is an error

**Requirement:** 31-REQ-1.3
**Type:** unit
**Description:** Verify that `--improve-passes` without `--auto` produces
an error.

**Preconditions:**
- None.

**Input:**
- CLI invocation: `["fix", "--improve-passes", "5"]`

**Expected:**
- Exit code is non-zero.
- Error message mentions `--auto`.

**Assertion pseudocode:**
```
result = cli_runner.invoke(fix_cmd, ["--improve-passes", "5"])
ASSERT result.exit_code != 0
ASSERT "auto" IN result.output.lower()
```

---

### TS-31-4: --improve-passes clamped to 1 when zero or negative

**Requirement:** 31-REQ-1.E1
**Type:** unit
**Description:** Verify `--improve-passes 0` is clamped to 1.

**Preconditions:**
- Mock Phase 1 to return ALL_FIXED.
- Mock Phase 2 to capture the max_passes argument.

**Input:**
- CLI invocation: `["fix", "--auto", "--improve-passes", "0"]`

**Expected:**
- `run_improve_loop` is called with `max_passes=1`.

**Assertion pseudocode:**
```
WITH mock run_fix_loop RETURNING ALL_FIXED:
WITH mock run_improve_loop:
    result = cli_runner.invoke(fix_cmd, ["--auto", "--improve-passes", "0"])
    ASSERT run_improve_loop.call_args.kwargs["max_passes"] == 1
```

---

### TS-31-5: --dry-run with --auto skips Phase 2

**Requirement:** 31-REQ-1.E2
**Type:** unit
**Description:** Verify Phase 2 does not run in dry-run mode.

**Preconditions:**
- None.

**Input:**
- CLI invocation: `["fix", "--auto", "--dry-run"]`

**Expected:**
- `run_improve_loop` is NOT called.

**Assertion pseudocode:**
```
WITH mock run_fix_loop:
WITH mock run_improve_loop:
    result = cli_runner.invoke(fix_cmd, ["--auto", "--dry-run"])
    ASSERT NOT run_improve_loop.called
```

---

### TS-31-6: Analyzer prompt includes project conventions

**Requirement:** 31-REQ-3.2
**Type:** unit
**Description:** Verify the analyzer prompt includes content from CLAUDE.md
or README.md.

**Preconditions:**
- A temp directory with a `CLAUDE.md` containing "Use ruff for formatting".

**Input:**
- `build_analyzer_prompt(project_root=tmp_dir, config=config)`

**Expected:**
- The system prompt contains "Use ruff for formatting".

**Assertion pseudocode:**
```
system_prompt, task_prompt = build_analyzer_prompt(tmp_dir, config)
ASSERT "ruff" IN system_prompt
ASSERT "formatting" IN system_prompt
```

---

### TS-31-7: Analyzer prompt includes oracle context when available

**Requirement:** 31-REQ-3.2, 31-REQ-4.1, 31-REQ-4.2
**Type:** unit
**Description:** Verify oracle context is included in the analyzer prompt.

**Preconditions:**
- Mock `query_oracle_context` to return "ADR-001: Use dataclasses for models".

**Input:**
- `build_analyzer_prompt(project_root=tmp_dir, config=config, oracle_context="ADR-001: Use dataclasses for models")`

**Expected:**
- System prompt contains "## Project Knowledge".
- System prompt contains "ADR-001: Use dataclasses for models".

**Assertion pseudocode:**
```
system_prompt, _ = build_analyzer_prompt(
    tmp_dir, config,
    oracle_context="ADR-001: Use dataclasses for models",
)
ASSERT "## Project Knowledge" IN system_prompt
ASSERT "ADR-001" IN system_prompt
```

---

### TS-31-8: Analyzer prompt omits oracle when unavailable

**Requirement:** 31-REQ-4.3, 31-REQ-4.E1
**Type:** unit
**Description:** Verify the analyzer prompt works without oracle context.

**Preconditions:**
- No oracle context provided (empty string).

**Input:**
- `build_analyzer_prompt(project_root=tmp_dir, config=config, oracle_context="")`

**Expected:**
- System prompt does NOT contain "## Project Knowledge".
- No error is raised.

**Assertion pseudocode:**
```
system_prompt, _ = build_analyzer_prompt(tmp_dir, config, oracle_context="")
ASSERT "## Project Knowledge" NOT IN system_prompt
```

---

### TS-31-9: Analyzer response parsing — valid JSON

**Requirement:** 31-REQ-3.3
**Type:** unit
**Description:** Verify the analyzer response parser correctly extracts
improvements from valid JSON.

**Preconditions:**
- A valid JSON string with two improvements.

**Input:**
```json
{
  "improvements": [
    {"id": "IMP-1", "tier": "quick_win", "title": "Remove dead import",
     "description": "...", "files": ["foo.py"], "impact": "low",
     "confidence": "high"},
    {"id": "IMP-2", "tier": "structural", "title": "Consolidate validators",
     "description": "...", "files": ["a.py", "b.py"], "impact": "medium",
     "confidence": "medium"}
  ],
  "summary": "Found 2 improvements.",
  "diminishing_returns": false
}
```

**Expected:**
- Returns `AnalyzerResult` with 2 improvements.
- `diminishing_returns` is False.
- Improvement tiers and confidence values are preserved.

**Assertion pseudocode:**
```
result = parse_analyzer_response(valid_json)
ASSERT len(result.improvements) == 2
ASSERT result.improvements[0].tier == "quick_win"
ASSERT result.improvements[1].confidence == "medium"
ASSERT result.diminishing_returns == False
```

---

### TS-31-10: Analyzer response parsing — invalid JSON

**Requirement:** 31-REQ-3.E1
**Type:** unit
**Description:** Verify the parser raises ValueError for invalid JSON.

**Preconditions:**
- An invalid JSON string.

**Input:**
- `parse_analyzer_response("This is not JSON")`

**Expected:**
- Raises `ValueError`.

**Assertion pseudocode:**
```
WITH RAISES ValueError:
    parse_analyzer_response("This is not JSON")
```

---

### TS-31-11: Analyzer response parsing — missing required fields

**Requirement:** 31-REQ-3.E1
**Type:** unit
**Description:** Verify the parser raises ValueError when required fields
are missing.

**Preconditions:**
- A JSON string with `improvements` key but missing `summary`.

**Input:**
- `parse_analyzer_response('{"improvements": []}')`

**Expected:**
- Raises `ValueError`.

**Assertion pseudocode:**
```
WITH RAISES ValueError:
    parse_analyzer_response('{"improvements": []}')
```

---

### TS-31-12: Improvement filtering excludes low confidence

**Requirement:** 31-REQ-3.4
**Type:** unit
**Description:** Verify low-confidence improvements are filtered out.

**Preconditions:**
- Three improvements: high, medium, low confidence.

**Input:**
- `filter_improvements([high_imp, medium_imp, low_imp])`

**Expected:**
- Returns 2 improvements (high and medium only).

**Assertion pseudocode:**
```
filtered = filter_improvements([high_imp, medium_imp, low_imp])
ASSERT len(filtered) == 2
ASSERT all(i.confidence in ("high", "medium") for i in filtered)
```

---

### TS-31-13: Improvement filtering sorts by tier priority

**Requirement:** 31-REQ-3.5, 31-REQ-5.3
**Type:** unit
**Description:** Verify filtered improvements are sorted: quick_win first,
structural second, design_level third.

**Preconditions:**
- Three improvements in wrong order: design_level, quick_win, structural.

**Input:**
- `filter_improvements([design_imp, quick_imp, structural_imp])`

**Expected:**
- Returns [quick_win, structural, design_level].

**Assertion pseudocode:**
```
filtered = filter_improvements([design_imp, quick_imp, structural_imp])
ASSERT filtered[0].tier == "quick_win"
ASSERT filtered[1].tier == "structural"
ASSERT filtered[2].tier == "design_level"
```

---

### TS-31-14: Verifier verdict parsing — PASS

**Requirement:** 31-REQ-6.2
**Type:** unit
**Description:** Verify verifier PASS verdict is correctly parsed.

**Preconditions:**
- Valid JSON verdict with `verdict: "PASS"`.

**Input:**
```json
{
  "quality_gates": "PASS",
  "improvement_valid": true,
  "verdict": "PASS",
  "evidence": "All tests pass. 3 files simplified."
}
```

**Expected:**
- Parsed verdict is "PASS".
- `improvement_valid` is True.

**Assertion pseudocode:**
```
verdict = parse_verifier_verdict(pass_json)
ASSERT verdict.verdict == "PASS"
ASSERT verdict.improvement_valid == True
ASSERT verdict.quality_gates == "PASS"
```

---

### TS-31-15: Verifier verdict parsing — FAIL

**Requirement:** 31-REQ-6.2
**Type:** unit
**Description:** Verify verifier FAIL verdict is correctly parsed.

**Preconditions:**
- Valid JSON verdict with `verdict: "FAIL"`.

**Input:**
```json
{
  "quality_gates": "PASS",
  "improvement_valid": false,
  "verdict": "FAIL",
  "evidence": "Public API changed in module.py"
}
```

**Expected:**
- Parsed verdict is "FAIL".

**Assertion pseudocode:**
```
verdict = parse_verifier_verdict(fail_json)
ASSERT verdict.verdict == "FAIL"
ASSERT verdict.improvement_valid == False
```

---

### TS-31-16: Verifier verdict parsing — invalid JSON

**Requirement:** 31-REQ-6.E2
**Type:** unit
**Description:** Verify invalid verifier response is treated as FAIL.

**Preconditions:**
- An invalid JSON string.

**Input:**
- `parse_verifier_verdict("not json")`

**Expected:**
- Raises `ValueError` (caller treats as FAIL).

**Assertion pseudocode:**
```
WITH RAISES ValueError:
    parse_verifier_verdict("not json")
```

---

### TS-31-17: Rollback executes git reset on FAIL

**Requirement:** 31-REQ-7.1, 31-REQ-7.3
**Type:** unit
**Description:** Verify rollback runs `git reset --hard HEAD~1`.

**Preconditions:**
- Mock `subprocess.run` to capture the git command.

**Input:**
- `rollback_improvement_pass(project_root=tmp_dir)`

**Expected:**
- `subprocess.run` is called with `["git", "reset", "--hard", "HEAD~1"]`.

**Assertion pseudocode:**
```
WITH mock subprocess.run:
    rollback_improvement_pass(tmp_dir)
    ASSERT subprocess.run.called
    cmd = subprocess.run.call_args[0][0]
    ASSERT cmd == ["git", "reset", "--hard", "HEAD~1"]
```

---

### TS-31-18: Rollback failure raises error

**Requirement:** 31-REQ-7.E1
**Type:** unit
**Description:** Verify rollback raises an error when git reset fails.

**Preconditions:**
- Mock `subprocess.run` to return non-zero exit code.

**Input:**
- `rollback_improvement_pass(project_root=tmp_dir)`

**Expected:**
- Raises an exception (AgentFoxError or similar).

**Assertion pseudocode:**
```
WITH mock subprocess.run RETURNING CompletedProcess(returncode=128, stderr="error"):
    WITH RAISES Exception:
        rollback_improvement_pass(tmp_dir)
```

---

### TS-31-19: Improve loop terminates on diminishing returns

**Requirement:** 31-REQ-8.1, 31-REQ-8.2
**Type:** unit
**Description:** Verify the improve loop stops when the analyzer reports
diminishing returns.

**Preconditions:**
- Mock analyzer session to return `diminishing_returns: true` on first pass.
- Mock quality checks to pass.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- `ImproveResult` with `termination_reason == CONVERGED`.
- `passes_completed == 1` (analyzer ran but no coder/verifier needed).

**Assertion pseudocode:**
```
WITH mock analyzer RETURNING diminishing_returns=True:
    result = await run_improve_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == ImproveTermination.CONVERGED
    ASSERT result.passes_completed == 1
```

---

### TS-31-20: Improve loop terminates on zero actionable improvements

**Requirement:** 31-REQ-8.1
**Type:** unit
**Description:** Verify the improve loop stops when the analyzer returns
no high/medium-confidence improvements.

**Preconditions:**
- Mock analyzer to return improvements with all `confidence: "low"`.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- `ImproveResult` with `termination_reason == CONVERGED`.

**Assertion pseudocode:**
```
WITH mock analyzer RETURNING only low-confidence improvements:
    result = await run_improve_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == ImproveTermination.CONVERGED
```

---

### TS-31-21: Improve loop terminates at pass limit

**Requirement:** 31-REQ-8.1
**Type:** unit
**Description:** Verify the improve loop stops after max_passes.

**Preconditions:**
- Mock analyzer to always return improvements.
- Mock coder sessions to succeed.
- Mock verifier to always PASS.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=2)`

**Expected:**
- `ImproveResult` with `termination_reason == PASS_LIMIT`.
- `passes_completed == 2`.

**Assertion pseudocode:**
```
WITH mock analyzer, coder, verifier all succeeding:
    result = await run_improve_loop(tmp_dir, config, max_passes=2)
    ASSERT result.termination_reason == ImproveTermination.PASS_LIMIT
    ASSERT result.passes_completed == 2
```

---

### TS-31-22: Improve loop terminates on verifier FAIL with rollback

**Requirement:** 31-REQ-7.1, 31-REQ-7.2, 31-REQ-8.1
**Type:** unit
**Description:** Verify verifier FAIL triggers rollback and loop termination.

**Preconditions:**
- Mock analyzer to return improvements.
- Mock coder to succeed.
- Mock verifier to return FAIL.
- Mock git reset to succeed.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- `ImproveResult` with `termination_reason == VERIFIER_FAIL`.
- `passes_completed == 1`.
- Git reset was called.
- `pass_results[0].rolled_back == True`.

**Assertion pseudocode:**
```
WITH mock verifier RETURNING FAIL:
WITH mock subprocess.run (git reset):
    result = await run_improve_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == ImproveTermination.VERIFIER_FAIL
    ASSERT result.pass_results[0].rolled_back == True
    ASSERT git_reset_called
```

---

### TS-31-23: Improve loop terminates on cost limit

**Requirement:** 31-REQ-2.3, 31-REQ-8.3
**Type:** unit
**Description:** Verify the improve loop stops when cost budget is exhausted.

**Preconditions:**
- `remaining_budget = 0.01` (insufficient for a full pass).

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3, remaining_budget=0.01)`

**Expected:**
- `ImproveResult` with `termination_reason == COST_LIMIT`.
- `passes_completed == 0`.

**Assertion pseudocode:**
```
result = await run_improve_loop(tmp_dir, config, max_passes=3, remaining_budget=0.01)
ASSERT result.termination_reason == ImproveTermination.COST_LIMIT
ASSERT result.passes_completed == 0
```

---

### TS-31-24: Analyzer session failure terminates Phase 2

**Requirement:** 31-REQ-3.E2
**Type:** unit
**Description:** Verify analyzer failure terminates the loop cleanly.

**Preconditions:**
- Mock analyzer session to raise an exception.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- `ImproveResult` with `termination_reason == ANALYZER_ERROR`.

**Assertion pseudocode:**
```
WITH mock analyzer RAISING RuntimeError:
    result = await run_improve_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == ImproveTermination.ANALYZER_ERROR
```

---

### TS-31-25: Coder session failure terminates Phase 2

**Requirement:** 31-REQ-5.E1
**Type:** unit
**Description:** Verify coder failure terminates the loop and discards
partial changes.

**Preconditions:**
- Mock analyzer to return improvements.
- Mock coder session to raise an exception.
- Mock `git checkout -- .` to succeed.

**Input:**
- `await run_improve_loop(project_root=tmp_dir, config=config, max_passes=3)`

**Expected:**
- `ImproveResult` with `termination_reason == CODER_ERROR`.
- `git checkout -- .` was called to discard partial changes.

**Assertion pseudocode:**
```
WITH mock coder RAISING RuntimeError:
WITH mock subprocess.run:
    result = await run_improve_loop(tmp_dir, config, max_passes=3)
    ASSERT result.termination_reason == ImproveTermination.CODER_ERROR
```

---

### TS-31-26: Combined report renders both phases

**Requirement:** 31-REQ-9.1, 31-REQ-9.2
**Type:** unit
**Description:** Verify combined report includes Phase 1 and Phase 2 data.

**Preconditions:**
- A FixResult with `termination_reason=ALL_FIXED, passes_completed=1`.
- An ImproveResult with `passes_completed=2, total_improvements=5,
  termination_reason=CONVERGED`.

**Input:**
- `render_combined_report(fix_result, improve_result, total_cost=3.50, console=console)`

**Expected:**
- Console output contains "Phase 1" and "Phase 2" sections.
- Contains improvement count "5".
- Contains total cost "$3.50".

**Assertion pseudocode:**
```
console = Console(file=StringIO())
render_combined_report(fix_result, improve_result, 3.50, console)
output = console.file.getvalue()
ASSERT "Phase 1" IN output
ASSERT "Phase 2" IN output
ASSERT "5" IN output
ASSERT "3.50" IN output
```

---

### TS-31-27: Combined report omits Phase 2 when not run

**Requirement:** 31-REQ-9.E1
**Type:** unit
**Description:** Verify report omits Phase 2 section when improve_result
is None.

**Preconditions:**
- A FixResult with `termination_reason=MAX_PASSES`.
- `improve_result=None`.

**Input:**
- `render_combined_report(fix_result, None, total_cost=1.20, console=console)`

**Expected:**
- Console output does NOT contain "Phase 2".

**Assertion pseudocode:**
```
console = Console(file=StringIO())
render_combined_report(fix_result, None, 1.20, console)
output = console.file.getvalue()
ASSERT "Phase 2" NOT IN output
```

---

### TS-31-28: JSON mode emits combined JSONL

**Requirement:** 31-REQ-9.3
**Type:** unit
**Description:** Verify JSON mode produces valid JSONL with both phase
summaries.

**Preconditions:**
- A FixResult and ImproveResult.

**Input:**
- `build_combined_json(fix_result, improve_result, total_cost=4.82)`

**Expected:**
- Returns a dict with `event: "complete"` and nested `summary.phase1`
  and `summary.phase2` objects.

**Assertion pseudocode:**
```
data = build_combined_json(fix_result, improve_result, 4.82)
ASSERT data["event"] == "complete"
ASSERT "phase1" IN data["summary"]
ASSERT "phase2" IN data["summary"]
ASSERT data["summary"]["total_cost"] == 4.82
```

---

### TS-31-29: Oracle context query returns formatted facts

**Requirement:** 31-REQ-4.1, 31-REQ-4.2
**Type:** unit
**Description:** Verify oracle query returns formatted context with
provenance.

**Preconditions:**
- Mock oracle to return 2 search results with provenance metadata.

**Input:**
- `query_oracle_context(config=config)`

**Expected:**
- Returns a non-empty string containing fact content and provenance.

**Assertion pseudocode:**
```
WITH mock oracle RETURNING [SearchResult(content="Use dataclasses", spec="01"), ...]:
    context = query_oracle_context(config)
    ASSERT len(context) > 0
    ASSERT "dataclasses" IN context
```

---

### TS-31-30: Oracle context query returns empty when unavailable

**Requirement:** 31-REQ-4.3
**Type:** unit
**Description:** Verify oracle returns empty string when knowledge store
is unavailable.

**Preconditions:**
- Mock oracle to raise KnowledgeStoreError.

**Input:**
- `query_oracle_context(config=config)`

**Expected:**
- Returns empty string.
- No exception raised.

**Assertion pseudocode:**
```
WITH mock oracle RAISING KnowledgeStoreError:
    context = query_oracle_context(config)
    ASSERT context == ""
```

## Property Test Cases

### TS-31-P1: Improve loop termination bound

**Property:** Property 2 from design.md
**Validates:** 31-REQ-8.1
**Type:** property
**Description:** The improve loop never exceeds max_passes iterations.

**For any:** max_passes in [1, 10]
**Invariant:** `result.passes_completed <= max_passes`

**Assertion pseudocode:**
```
FOR ANY max_passes IN integers(min_value=1, max_value=10):
    WITH mock sessions always succeeding:
        result = await run_improve_loop(tmp_dir, config, max_passes=max_passes)
        ASSERT result.passes_completed <= max_passes
```

---

### TS-31-P2: Improvement filtering soundness

**Property:** Property 5 from design.md
**Validates:** 31-REQ-3.4
**Type:** property
**Description:** Filtered improvements never contain low-confidence items.

**For any:** list of Improvement objects with random confidence values
**Invariant:** All items in `filter_improvements(items)` have confidence
in ("high", "medium").

**Assertion pseudocode:**
```
FOR ANY improvements IN lists(random_improvements()):
    filtered = filter_improvements(improvements)
    ASSERT all(i.confidence in ("high", "medium") for i in filtered)
```

---

### TS-31-P3: Tier priority ordering

**Property:** Property 6 from design.md
**Validates:** 31-REQ-3.5
**Type:** property
**Description:** Filtered improvements are always in tier priority order.

**For any:** list of Improvement objects with random tiers and
high/medium confidence
**Invariant:** In the output, all quick_win come before structural, all
structural come before design_level.

**Assertion pseudocode:**
```
TIER_ORDER = {"quick_win": 0, "structural": 1, "design_level": 2}
FOR ANY improvements IN lists(random_improvements(confidence=["high","medium"])):
    filtered = filter_improvements(improvements)
    orders = [TIER_ORDER[i.tier] for i in filtered]
    ASSERT orders == sorted(orders)
```

---

### TS-31-P4: Cost budget monotonicity

**Property:** Property 4 from design.md
**Validates:** 31-REQ-2.3, 31-REQ-8.3
**Type:** property
**Description:** Cumulative cost never decreases and never exceeds budget.

**For any:** sequence of pass costs, budget > 0
**Invariant:** The improve loop respects budget and terminates at or before
exhaustion.

**Assertion pseudocode:**
```
FOR ANY budget IN floats(min_value=0.01, max_value=100.0):
    WITH mock sessions returning costs:
        result = await run_improve_loop(
            tmp_dir, config, max_passes=10, remaining_budget=budget,
        )
        ASSERT result.total_cost <= budget + epsilon
```

---

### TS-31-P5: Report field consistency

**Property:** Property 7 from design.md
**Validates:** 31-REQ-9.1
**Type:** property
**Description:** ImproveResult fields are internally consistent.

**For any:** valid ImproveResult
**Invariant:** `passes_completed <= max_passes` AND
`verifier_pass_count + verifier_fail_count <= passes_completed` AND
`sessions_consumed >= 0` AND `termination_reason` is a valid enum value.

**Assertion pseudocode:**
```
FOR ANY result IN valid_improve_results():
    ASSERT result.passes_completed <= result.max_passes
    ASSERT result.verifier_pass_count + result.verifier_fail_count <= result.passes_completed
    ASSERT result.sessions_consumed >= 0
    ASSERT result.termination_reason IN ImproveTermination
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 31-REQ-1.1 | TS-31-1 | unit |
| 31-REQ-1.3 | TS-31-3 | unit |
| 31-REQ-1.4 | TS-31-2 | unit |
| 31-REQ-1.E1 | TS-31-4 | unit |
| 31-REQ-1.E2 | TS-31-5 | unit |
| 31-REQ-2.1 | TS-31-1, TS-31-2 | unit |
| 31-REQ-2.3 | TS-31-23 | unit |
| 31-REQ-3.2 | TS-31-6, TS-31-7 | unit |
| 31-REQ-3.3 | TS-31-9 | unit |
| 31-REQ-3.4 | TS-31-12 | unit |
| 31-REQ-3.5 | TS-31-13 | unit |
| 31-REQ-3.E1 | TS-31-10, TS-31-11 | unit |
| 31-REQ-3.E2 | TS-31-24 | unit |
| 31-REQ-4.1 | TS-31-29 | unit |
| 31-REQ-4.2 | TS-31-29 | unit |
| 31-REQ-4.3 | TS-31-8, TS-31-30 | unit |
| 31-REQ-4.E1 | TS-31-30 | unit |
| 31-REQ-5.1 | TS-31-21 | unit |
| 31-REQ-5.3 | TS-31-13 | unit |
| 31-REQ-5.E1 | TS-31-25 | unit |
| 31-REQ-6.2 | TS-31-14, TS-31-15 | unit |
| 31-REQ-6.E1 | TS-31-22 | unit |
| 31-REQ-6.E2 | TS-31-16 | unit |
| 31-REQ-7.1 | TS-31-17, TS-31-22 | unit |
| 31-REQ-7.2 | TS-31-22 | unit |
| 31-REQ-7.3 | TS-31-17 | unit |
| 31-REQ-7.E1 | TS-31-18 | unit |
| 31-REQ-8.1 | TS-31-19, TS-31-20, TS-31-21, TS-31-22, TS-31-23 | unit |
| 31-REQ-8.2 | TS-31-19 | unit |
| 31-REQ-8.3 | TS-31-23 | unit |
| 31-REQ-9.1 | TS-31-26 | unit |
| 31-REQ-9.2 | TS-31-26 | unit |
| 31-REQ-9.3 | TS-31-28 | unit |
| 31-REQ-9.E1 | TS-31-27 | unit |
| Property 2 | TS-31-P1 | property |
| Property 4 | TS-31-P4 | property |
| Property 5 | TS-31-P2 | property |
| Property 6 | TS-31-P3 | property |
| Property 7 | TS-31-P5 | property |
