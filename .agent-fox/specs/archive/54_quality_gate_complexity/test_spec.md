# Test Specification: Post-Session Quality Gate & Complexity Enrichment

## Overview

Tests validate quality gate execution, timeout handling, result recording,
and the four new feature vector fields. Tests are split between quality gate
behavior (unit + integration) and feature extraction logic (unit + property).

## Test Cases

### TS-54-1: Quality gate runs after completed session

**Requirement:** 54-REQ-1.1
**Type:** unit
**Description:** Verify that the quality gate command is executed after a
coder session completes successfully.

**Preconditions:**
- `quality_gate = "make check"` in config.
- Session status: `"completed"`.

**Input:**
- Mock subprocess that exits with code 0.

**Expected:**
- `subprocess.run` called with `"make check"`.
- Result recorded as passed.

**Assertion pseudocode:**
```
mock_subprocess = mock(subprocess.run, return_code=0)
lifecycle.run_quality_gate(workspace, node_id)
ASSERT mock_subprocess.called_once_with("make check", ...)
```

### TS-54-2: Quality gate skipped when not configured

**Requirement:** 54-REQ-1.3
**Type:** unit
**Description:** Verify that no subprocess is spawned when quality_gate is
empty.

**Preconditions:**
- `quality_gate = ""` in config.

**Input:**
- Session status: `"completed"`.

**Expected:**
- No subprocess spawned.
- Method returns None.

**Assertion pseudocode:**
```
mock_subprocess = mock(subprocess.run)
result = lifecycle.run_quality_gate(workspace, node_id)
ASSERT NOT mock_subprocess.called
ASSERT result IS None
```

### TS-54-3: Quality gate timeout handling

**Requirement:** 54-REQ-1.2
**Type:** unit
**Description:** Verify that a command exceeding the timeout is killed and
recorded as failure.

**Preconditions:**
- `quality_gate = "sleep 600"`, `quality_gate_timeout = 1`.

**Input:**
- Mock subprocess that raises `subprocess.TimeoutExpired`.

**Expected:**
- Result has exit_code=-1, passed=False.

**Assertion pseudocode:**
```
mock_subprocess = mock(subprocess.run, side_effect=TimeoutExpired)
result = lifecycle.run_quality_gate(workspace, node_id)
ASSERT result.exit_code == -1
ASSERT result.passed == False
```

### TS-54-4: Quality gate result audit event

**Requirement:** 54-REQ-2.1
**Type:** unit
**Description:** Verify that a `quality_gate.result` audit event is emitted.

**Preconditions:**
- Quality gate configured and run.
- Sink dispatcher available.

**Input:**
- Quality gate exits with code 0, duration 500ms.

**Expected:**
- `quality_gate.result` audit event with exit_code=0, passed=True,
  duration_ms=500.

**Assertion pseudocode:**
```
events = capture_audit_events(lifecycle.run_quality_gate(...))
gate_events = [e for e in events if e.event_type == "quality_gate.result"]
ASSERT len(gate_events) == 1
ASSERT gate_events[0].payload["exit_code"] == 0
ASSERT gate_events[0].payload["passed"] == True
```

### TS-54-5: Gate failure sets status

**Requirement:** 54-REQ-2.2
**Type:** unit
**Description:** Verify that a failed quality gate sets session status to
`completed_with_gate_failure`.

**Preconditions:**
- Quality gate exits with code 1.

**Input:**
- Mock subprocess exits with code 1.

**Expected:**
- Session status set to `"completed_with_gate_failure"`.

**Assertion pseudocode:**
```
mock_subprocess = mock(subprocess.run, return_code=1)
result = lifecycle.run_quality_gate(workspace, node_id)
ASSERT result.passed == False
ASSERT session.status == "completed_with_gate_failure"
```

### TS-54-6: Gate failure does not block next session

**Requirement:** 54-REQ-2.3
**Type:** integration
**Description:** Verify that a quality gate failure does not prevent the
next task group from executing.

**Preconditions:**
- Quality gate fails for task group 2.
- Task group 3 is queued.

**Input:**
- Run with two task groups, first gate fails.

**Expected:**
- Task group 3 still executes.

**Assertion pseudocode:**
```
# Group 2 gate fails
lifecycle.run_quality_gate(workspace_2, "coder_02_2")
# Group 3 starts normally
ASSERT engine.next_session_started("coder_03_3")
```

### TS-54-7: File count estimate extraction

**Requirement:** 54-REQ-3.1
**Type:** unit
**Description:** Verify that file paths are counted in task group description.

**Preconditions:**
- tasks.md contains a task group section with file paths.

**Input:**
- Task group 2 text: `"Modify agent_fox/cli/app.py and agent_fox/core/config.py, also update tests/test_app.py"`

**Expected:**
- `file_count_estimate = 3`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir, task_group=2, archetype="coder")
ASSERT fv.file_count_estimate == 3
```

### TS-54-8: Cross-spec detection

**Requirement:** 54-REQ-4.1
**Type:** unit
**Description:** Verify that references to other spec names are detected.

**Preconditions:**
- tasks.md task group references `"03_api_routes"` but spec is `"05_auth"`.

**Input:**
- Task group text mentioning `03_api_routes`.

**Expected:**
- `cross_spec_integration = True`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir, task_group=2, archetype="coder", spec_name="05_auth")
ASSERT fv.cross_spec_integration == True
```

### TS-54-9: No cross-spec when only own spec

**Requirement:** 54-REQ-4.2
**Type:** unit
**Description:** Verify that referencing only the task's own spec does not
set cross_spec_integration.

**Preconditions:**
- Task group mentions only its own spec name.

**Input:**
- Task group for spec `"05_auth"` mentioning `"05_auth"`.

**Expected:**
- `cross_spec_integration = False`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir, task_group=2, archetype="coder", spec_name="05_auth")
ASSERT fv.cross_spec_integration == False
```

### TS-54-10: Language count from extensions

**Requirement:** 54-REQ-5.1
**Type:** unit
**Description:** Verify that distinct language extensions are counted.

**Preconditions:**
- Task group mentions `.py`, `.ts`, and `.proto` files.

**Input:**
- Task group text: `"Modify handler.py, update schema.proto, fix client.ts"`

**Expected:**
- `language_count = 3`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir, task_group=2, archetype="coder")
ASSERT fv.language_count == 3
```

### TS-54-11: Historical median duration

**Requirement:** 54-REQ-6.1
**Type:** integration
**Description:** Verify that historical median is computed from prior outcomes.

**Preconditions:**
- DuckDB with 3 successful outcomes for spec: 100ms, 200ms, 300ms.

**Input:**
- spec_name: `"03_api"`.

**Expected:**
- `historical_median_duration_ms = 200`

**Assertion pseudocode:**
```
insert_outcomes(conn, [100, 200, 300], spec_name="03_api")
fv = extract_features(spec_dir, 2, "coder", conn=conn, spec_name="03_api")
ASSERT fv.historical_median_duration_ms == 200
```

### TS-54-12: Heuristic ADVANCED threshold

**Requirement:** 54-REQ-7.1
**Type:** unit
**Description:** Verify that cross_spec or high file count triggers ADVANCED.

**Preconditions:**
- Feature vector with `cross_spec_integration=True`.

**Input:**
- FeatureVector with cross_spec_integration=True, file_count_estimate=2.

**Expected:**
- Heuristic predicts ADVANCED with confidence 0.7.

**Assertion pseudocode:**
```
fv = FeatureVector(..., cross_spec_integration=True, file_count_estimate=2)
assessment = heuristic_assess(fv)
ASSERT assessment.predicted_tier == ModelTier.ADVANCED
ASSERT assessment.confidence == 0.7
```

### TS-54-13: Feature vector JSON serialization

**Requirement:** 54-REQ-7.2
**Type:** unit
**Description:** Verify that all 10 fields are in the serialized JSON.

**Preconditions:** None.

**Input:**
- FeatureVector with all fields set.

**Expected:**
- JSON contains all 10 keys.

**Assertion pseudocode:**
```
fv = FeatureVector(subtask_count=5, ..., file_count_estimate=3, cross_spec_integration=True, language_count=2, historical_median_duration_ms=200)
j = json.loads(fv_to_json(fv))
ASSERT set(j.keys()) == {"subtask_count", "spec_word_count", "has_property_tests", "edge_case_count", "dependency_count", "archetype", "file_count_estimate", "cross_spec_integration", "language_count", "historical_median_duration_ms"}
```

## Edge Case Tests

### TS-54-E1: Command not found

**Requirement:** 54-REQ-1.E1
**Type:** unit
**Description:** Verify that a missing command is recorded as failure.

**Preconditions:**
- quality_gate = "nonexistent_command".

**Input:**
- Mock subprocess raises `FileNotFoundError`.

**Expected:**
- Result has exit_code=-2, passed=False.
- Warning logged.

**Assertion pseudocode:**
```
mock_subprocess = mock(subprocess.run, side_effect=FileNotFoundError)
result = lifecycle.run_quality_gate(workspace, node_id)
ASSERT result.exit_code == -2
ASSERT result.passed == False
ASSERT warning_logged("nonexistent_command")
```

### TS-54-E2: No prior outcomes returns None

**Requirement:** 54-REQ-6.2
**Type:** unit
**Description:** Verify that historical_median is None when no outcomes exist.

**Preconditions:**
- Empty execution_outcomes table.

**Input:**
- spec_name: `"new_spec"`.

**Expected:**
- `historical_median_duration_ms = None`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir, 2, "coder", conn=empty_conn, spec_name="new_spec")
ASSERT fv.historical_median_duration_ms IS None
```

### TS-54-E3: Single prior outcome

**Requirement:** 54-REQ-6.E1
**Type:** unit
**Description:** Verify that median of one value equals that value.

**Preconditions:**
- One successful outcome: 500ms.

**Input:**
- spec_name: `"03_api"`.

**Expected:**
- `historical_median_duration_ms = 500`

**Assertion pseudocode:**
```
insert_outcomes(conn, [500], spec_name="03_api")
fv = extract_features(spec_dir, 2, "coder", conn=conn, spec_name="03_api")
ASSERT fv.historical_median_duration_ms == 500
```

### TS-54-E4: No file paths in task

**Requirement:** 54-REQ-3.2
**Type:** unit
**Description:** Verify that file_count_estimate defaults to 0.

**Preconditions:**
- Task group text contains no file paths.

**Input:**
- Task group text: `"Refactor the module structure"`

**Expected:**
- `file_count_estimate = 0`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir_no_paths, task_group=2, archetype="coder")
ASSERT fv.file_count_estimate == 0
```

### TS-54-E5: Language count defaults to 1

**Requirement:** 54-REQ-5.2
**Type:** unit
**Description:** Verify that language_count defaults to 1 when no extensions
found.

**Preconditions:**
- Task group text mentions no file extensions.

**Input:**
- Task group text: `"Update the configuration"`

**Expected:**
- `language_count = 1`

**Assertion pseudocode:**
```
fv = extract_features(spec_dir_no_ext, task_group=2, archetype="coder")
ASSERT fv.language_count == 1
```

### TS-54-E6: Both cross-spec and high file count

**Requirement:** 54-REQ-7.E1
**Type:** unit
**Description:** Verify no double-upgrade when both conditions are met.

**Preconditions:**
- cross_spec_integration=True AND file_count_estimate=10.

**Input:**
- FeatureVector with both flags set.

**Expected:**
- ADVANCED with confidence 0.7 (not higher).

**Assertion pseudocode:**
```
fv = FeatureVector(..., cross_spec_integration=True, file_count_estimate=10)
assessment = heuristic_assess(fv)
ASSERT assessment.predicted_tier == ModelTier.ADVANCED
ASSERT assessment.confidence == 0.7
```

## Property Test Cases

### TS-54-P1: Quality gate only when configured

**Property:** Property 1 from design.md
**Validates:** 54-REQ-1.3
**Type:** property
**Description:** No subprocess is spawned when quality_gate is empty.

**For any:** quality_gate in {"", None} and valid session state.
**Invariant:** subprocess.run is never called.

**Assertion pseudocode:**
```
FOR ANY gate IN sampled_from(["", None]):
    config.quality_gate = gate
    mock_sub = mock(subprocess.run)
    lifecycle.run_quality_gate(workspace, node_id)
    ASSERT NOT mock_sub.called
```

### TS-54-P2: Timeout enforcement

**Property:** Property 2 from design.md
**Validates:** 54-REQ-1.2
**Type:** property
**Description:** Timed-out gates always record exit_code=-1.

**For any:** quality gate that exceeds timeout.
**Invariant:** Result has exit_code=-1 and passed=False.

**Assertion pseudocode:**
```
FOR ANY timeout IN integers(1, 10):
    config.quality_gate_timeout = timeout
    mock_sub = mock(subprocess.run, side_effect=TimeoutExpired)
    result = lifecycle.run_quality_gate(workspace, node_id)
    ASSERT result.exit_code == -1
    ASSERT result.passed == False
```

### TS-54-P3: Gate failure does not block

**Property:** Property 3 from design.md
**Validates:** 54-REQ-2.3
**Type:** property
**Description:** Gate failure never prevents the next session.

**For any:** exit code in [1, 255].
**Invariant:** Engine proceeds to next session after gate failure.

**Assertion pseudocode:**
```
FOR ANY exit_code IN integers(1, 255):
    mock_sub = mock(subprocess.run, return_code=exit_code)
    lifecycle.run_quality_gate(workspace, node_id)
    ASSERT engine.can_start_next_session()
```

### TS-54-P4: Feature vector serialization

**Property:** Property 4 from design.md
**Validates:** 54-REQ-7.2
**Type:** property
**Description:** All 10 fields present in JSON serialization.

**For any:** valid FeatureVector with random field values.
**Invariant:** JSON has exactly 10 keys, all named correctly.

**Assertion pseudocode:**
```
FOR ANY fv IN feature_vectors():
    j = json.loads(fv_to_json(fv))
    ASSERT len(j) == 10
    ASSERT "file_count_estimate" IN j
    ASSERT "cross_spec_integration" IN j
    ASSERT "language_count" IN j
    ASSERT "historical_median_duration_ms" IN j
```

### TS-54-P5: File count accuracy

**Property:** Property 5 from design.md
**Validates:** 54-REQ-3.1, 54-REQ-3.2
**Type:** property
**Description:** File count matches the number of distinct file paths.

**For any:** task group text with 0-20 file path mentions.
**Invariant:** file_count_estimate equals the count of distinct paths.

**Assertion pseudocode:**
```
FOR ANY paths IN lists(file_paths(), max_size=20):
    text = " ".join(paths + ["some other words"])
    count = _count_file_paths_from_text(text)
    ASSERT count == len(set(paths))
```

### TS-54-P6: Cross-spec detection

**Property:** Property 6 from design.md
**Validates:** 54-REQ-4.1, 54-REQ-4.2
**Type:** property
**Description:** cross_spec_integration is True iff other spec names present.

**For any:** task text with 0-5 spec name references.
**Invariant:** True when at least one spec name differs from own.

**Assertion pseudocode:**
```
FOR ANY own_spec IN spec_names(), other_specs IN lists(spec_names()):
    text = " ".join([own_spec] + other_specs)
    result = _detect_cross_spec_from_text(text, own_spec)
    other_present = any(s != own_spec for s in other_specs)
    ASSERT result == other_present
```

### TS-54-P7: Historical median correctness

**Property:** Property 7 from design.md
**Validates:** 54-REQ-6.1, 54-REQ-6.2, 54-REQ-6.E1
**Type:** property
**Description:** Median equals the statistical median of prior durations.

**For any:** list of 0-50 positive integers (durations).
**Invariant:** Result equals statistics.median of the list, or None for empty.

**Assertion pseudocode:**
```
FOR ANY durations IN lists(integers(min_value=1, max_value=1000000)):
    insert_outcomes(conn, durations, spec_name="test")
    result = _get_historical_median_duration(conn, "test")
    IF len(durations) == 0:
        ASSERT result IS None
    ELSE:
        ASSERT result == statistics.median(durations)
```

### TS-54-P8: Heuristic ADVANCED threshold

**Property:** Property 8 from design.md
**Validates:** 54-REQ-7.1
**Type:** property
**Description:** ADVANCED predicted when cross_spec or file_count >= 8.

**For any:** feature vector with varying cross_spec and file_count.
**Invariant:** If cross_spec=True OR file_count>=8, predicted tier is ADVANCED.

**Assertion pseudocode:**
```
FOR ANY cross IN booleans(), file_count IN integers(0, 20):
    fv = FeatureVector(..., cross_spec_integration=cross, file_count_estimate=file_count)
    assessment = heuristic_assess(fv)
    IF cross OR file_count >= 8:
        ASSERT assessment.predicted_tier == ModelTier.ADVANCED
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 54-REQ-1.1 | TS-54-1 | unit |
| 54-REQ-1.2 | TS-54-3 | unit |
| 54-REQ-1.3 | TS-54-2 | unit |
| 54-REQ-1.E1 | TS-54-E1 | unit |
| 54-REQ-1.E2 | TS-54-4 | unit |
| 54-REQ-2.1 | TS-54-4 | unit |
| 54-REQ-2.2 | TS-54-5 | unit |
| 54-REQ-2.3 | TS-54-6 | integration |
| 54-REQ-2.E1 | TS-54-4 | unit |
| 54-REQ-3.1 | TS-54-7 | unit |
| 54-REQ-3.2 | TS-54-E4 | unit |
| 54-REQ-4.1 | TS-54-8 | unit |
| 54-REQ-4.2 | TS-54-9 | unit |
| 54-REQ-5.1 | TS-54-10 | unit |
| 54-REQ-5.2 | TS-54-E5 | unit |
| 54-REQ-6.1 | TS-54-11 | integration |
| 54-REQ-6.2 | TS-54-E2 | unit |
| 54-REQ-6.E1 | TS-54-E3 | unit |
| 54-REQ-7.1 | TS-54-12 | unit |
| 54-REQ-7.2 | TS-54-13 | unit |
| 54-REQ-7.E1 | TS-54-E6 | unit |
| Property 1 | TS-54-P1 | property |
| Property 2 | TS-54-P2 | property |
| Property 3 | TS-54-P3 | property |
| Property 4 | TS-54-P4 | property |
| Property 5 | TS-54-P5 | property |
| Property 6 | TS-54-P6 | property |
| Property 7 | TS-54-P7 | property |
| Property 8 | TS-54-P8 | property |
