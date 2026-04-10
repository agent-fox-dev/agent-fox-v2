# Test Specification: Simplify Model Routing

## Overview

Tests verify that the prediction pipeline is fully removed, the escalation
ladder is always created from archetype defaults, and no regressions are
introduced. Existing escalation tests (`test_escalation.py`) are retained
unchanged.

## Test Cases

### TS-89-1: AssessmentManager creates ladder from archetype default

**Requirement:** 89-REQ-1.1
**Type:** unit
**Description:** assess_node() creates an EscalationLadder with starting_tier
from the archetype registry.

**Preconditions:**
- No pipeline configured (pipeline=None or removed).

**Input:**
- node_id = "some_spec:1", archetype = "coder"

**Expected:**
- `manager.ladders["some_spec:1"]` exists
- `ladder.current_tier == ModelTier.STANDARD` (coder default)

**Assertion pseudocode:**
```
manager = AssessmentManager(retries_before_escalation=1)
await manager.assess_node("some_spec:1", "coder")
ladder = manager.ladders["some_spec:1"]
ASSERT ladder.current_tier == ModelTier.STANDARD
```

### TS-89-2: Ladder tier ceiling is ADVANCED

**Requirement:** 89-REQ-1.2
**Type:** unit
**Description:** The escalation ladder's tier_ceiling is always ADVANCED.

**Preconditions:**
- Any archetype.

**Input:**
- node_id = "some_spec:1", archetype = "oracle" (default=ADVANCED)

**Expected:**
- Ladder tier_ceiling is ADVANCED.

**Assertion pseudocode:**
```
manager = AssessmentManager(retries_before_escalation=1)
await manager.assess_node("some_spec:1", "oracle")
ladder = manager.ladders["some_spec:1"]
ASSERT ladder._tier_ceiling == ModelTier.ADVANCED
```

### TS-89-3: assess_node always creates ladder (no pipeline dependency)

**Requirement:** 89-REQ-1.3
**Type:** unit
**Description:** assess_node() creates a ladder even when no pipeline exists.

**Preconditions:**
- AssessmentManager constructed without pipeline parameter.

**Input:**
- node_id = "spec:2", archetype = "skeptic"

**Expected:**
- Ladder exists in manager.ladders.
- Starting tier is ADVANCED (skeptic default).

**Assertion pseudocode:**
```
manager = AssessmentManager(retries_before_escalation=2)
await manager.assess_node("spec:2", "skeptic")
ASSERT "spec:2" in manager.ladders
ASSERT manager.ladders["spec:2"].current_tier == ModelTier.ADVANCED
```

### TS-89-4: Prediction pipeline modules deleted

**Requirement:** 89-REQ-2.1
**Type:** unit
**Description:** Importing removed modules raises ImportError.

**Preconditions:**
- Modules have been deleted from the filesystem.

**Input:**
- Attempt to import each removed module.

**Expected:**
- ImportError for each.

**Assertion pseudocode:**
```
FOR module IN ["agent_fox.routing.assessor",
               "agent_fox.routing.features",
               "agent_fox.routing.calibration",
               "agent_fox.routing.duration"]:
    ASSERT_RAISES ImportError: importlib.import_module(module)
```

### TS-89-5: DuckDB persistence functions removed from core

**Requirement:** 89-REQ-2.2
**Type:** unit
**Description:** core.py does not export DuckDB persistence functions.

**Preconditions:**
- `agent_fox.routing.core` is importable.

**Input:**
- Check for removed function names in module attributes.

**Expected:**
- None of the removed functions exist.

**Assertion pseudocode:**
```
import agent_fox.routing.core as core
FOR name IN ["persist_assessment", "persist_outcome",
             "count_outcomes", "query_outcomes",
             "_feature_vector_to_json"]:
    ASSERT NOT hasattr(core, name)
```

### TS-89-6: Dataclasses retained in core

**Requirement:** 89-REQ-2.4
**Type:** unit
**Description:** FeatureVector, ComplexityAssessment, ExecutionOutcome still importable.

**Preconditions:**
- `agent_fox.routing.core` is importable.

**Input:**
- Import each dataclass.

**Expected:**
- All three are importable and are dataclasses.

**Assertion pseudocode:**
```
from agent_fox.routing.core import FeatureVector, ComplexityAssessment, ExecutionOutcome
ASSERT dataclasses.is_dataclass(FeatureVector)
ASSERT dataclasses.is_dataclass(ComplexityAssessment)
ASSERT dataclasses.is_dataclass(ExecutionOutcome)
```

### TS-89-7: No AssessmentPipeline in run.py

**Requirement:** 89-REQ-2.3
**Type:** unit
**Description:** run.py does not import or reference AssessmentPipeline.

**Preconditions:**
- None.

**Input:**
- Read source of `agent_fox/engine/run.py`.

**Expected:**
- No occurrence of "AssessmentPipeline" in the file.

**Assertion pseudocode:**
```
source = Path("agent_fox/engine/run.py").read_text()
ASSERT "AssessmentPipeline" NOT IN source
```

### TS-89-8: No record_node_outcome in result handler

**Requirement:** 89-REQ-3.1
**Type:** unit
**Description:** SessionResultHandler has no record_node_outcome method.

**Preconditions:**
- None.

**Input:**
- Inspect SessionResultHandler class.

**Expected:**
- No `record_node_outcome` attribute.

**Assertion pseudocode:**
```
from agent_fox.engine.result_handler import SessionResultHandler
ASSERT NOT hasattr(SessionResultHandler, "record_node_outcome")
```

### TS-89-9: No routing_pipeline in SessionResultHandler.__init__

**Requirement:** 89-REQ-3.2
**Type:** unit
**Description:** SessionResultHandler.__init__ does not accept routing_pipeline.

**Preconditions:**
- None.

**Input:**
- Inspect __init__ signature.

**Expected:**
- "routing_pipeline" not in parameter names.

**Assertion pseudocode:**
```
import inspect
sig = inspect.signature(SessionResultHandler.__init__)
ASSERT "routing_pipeline" NOT IN sig.parameters
```

### TS-89-10: Prediction-only config fields removed

**Requirement:** 89-REQ-4.1
**Type:** unit
**Description:** RoutingConfig does not have training_threshold, accuracy_threshold, retrain_interval.

**Preconditions:**
- None.

**Input:**
- Inspect RoutingConfig fields.

**Expected:**
- Removed fields absent; retries_before_escalation present.

**Assertion pseudocode:**
```
from agent_fox.core.config import RoutingConfig
fields = RoutingConfig.model_fields
ASSERT "training_threshold" NOT IN fields
ASSERT "accuracy_threshold" NOT IN fields
ASSERT "retrain_interval" NOT IN fields
ASSERT "retries_before_escalation" IN fields
```

### TS-89-11: Prediction pipeline test files deleted

**Requirement:** 89-REQ-5.1
**Type:** unit
**Description:** Test files for removed modules do not exist.

**Preconditions:**
- None.

**Input:**
- Check file existence.

**Expected:**
- Files do not exist.

**Assertion pseudocode:**
```
FOR path IN ["tests/test_routing/test_assessor.py",
             "tests/test_routing/test_features.py",
             "tests/test_routing/test_calibration.py",
             "tests/test_routing/test_storage.py",
             "tests/test_routing/test_integration.py"]:
    ASSERT NOT Path(path).exists()
```

### TS-89-12: No duration imports in engine or CLI

**Requirement:** 89-REQ-6.1
**Type:** unit
**Description:** engine.py and status.py do not import from routing.duration.

**Preconditions:**
- None.

**Input:**
- Read source of both files.

**Expected:**
- No "routing.duration" in either file.

**Assertion pseudocode:**
```
FOR path IN ["agent_fox/engine/engine.py", "agent_fox/cli/status.py"]:
    source = Path(path).read_text()
    ASSERT "routing.duration" NOT IN source
```

### TS-89-13: Superseded specs have deprecation banners

**Requirement:** 89-REQ-7.1
**Type:** unit
**Description:** Archived specs 30 and 57 have SUPERSEDED banners.

**Preconditions:**
- Deprecation banners have been added.

**Input:**
- Read first lines of each file in both archived spec directories.

**Expected:**
- Each file contains "SUPERSEDED" in its first 5 lines.

**Assertion pseudocode:**
```
FOR spec_dir IN [".specs/archive/30_adaptive_model_routing",
                 ".specs/archive/57_archetype_model_tiers"]:
    FOR md_file IN glob(spec_dir + "/*.md"):
        header = read_first_5_lines(md_file)
        ASSERT "SUPERSEDED" IN header
```

## Edge Case Tests

### TS-89-E1: Unknown archetype defaults to coder

**Requirement:** 89-REQ-1.E1
**Type:** unit
**Description:** assess_node with unknown archetype creates ladder at STANDARD.

**Preconditions:**
- Archetype "nonexistent_archetype" not in registry.

**Input:**
- node_id = "spec:1", archetype = "nonexistent_archetype"

**Expected:**
- Ladder created with starting_tier = STANDARD (coder fallback).

**Assertion pseudocode:**
```
manager = AssessmentManager(retries_before_escalation=1)
await manager.assess_node("spec:1", "nonexistent_archetype")
ladder = manager.ladders["spec:1"]
ASSERT ladder.current_tier == ModelTier.STANDARD
```

## Property Test Cases

### TS-89-P1: Archetype tier always becomes ladder starting tier

**Property:** Property 1 from design.md
**Validates:** 89-REQ-1.1, 89-REQ-1.2
**Type:** property
**Description:** For any archetype in the registry, assess_node creates a
ladder whose starting tier matches the archetype default.

**For any:** archetype name drawn from ARCHETYPE_REGISTRY.keys()
**Invariant:** ladder.current_tier == ModelTier(archetype.default_model_tier)

**Assertion pseudocode:**
```
FOR ANY archetype_name IN ARCHETYPE_REGISTRY.keys():
    manager = AssessmentManager(retries_before_escalation=1)
    await manager.assess_node(f"test_spec:1", archetype_name)
    ladder = manager.ladders["test_spec:1"]
    expected = ModelTier(ARCHETYPE_REGISTRY[archetype_name].default_model_tier)
    ASSERT ladder.current_tier == expected
```

### TS-89-P2: Prediction pipeline modules not importable

**Property:** Property 2 from design.md
**Validates:** 89-REQ-2.1
**Type:** property
**Description:** All removed modules raise ImportError.

**For any:** module path in [assessor, features, calibration, duration]
**Invariant:** importlib.import_module raises ImportError.

**Assertion pseudocode:**
```
FOR ANY module IN ["agent_fox.routing.assessor",
                   "agent_fox.routing.features",
                   "agent_fox.routing.calibration",
                   "agent_fox.routing.duration"]:
    ASSERT_RAISES ImportError: importlib.import_module(module)
```

### TS-89-P3: No DuckDB routing writes

**Property:** Property 3 from design.md
**Validates:** 89-REQ-2.2, 89-REQ-3.1
**Type:** property
**Description:** The routing module contains no functions that write to DuckDB.

**For any:** public callable in `agent_fox.routing.core`
**Invariant:** No callable performs DuckDB INSERT or SELECT.

**Assertion pseudocode:**
```
source = Path("agent_fox/routing/core.py").read_text()
ASSERT "INSERT INTO" NOT IN source
ASSERT "SELECT" NOT IN source
```

### TS-89-P4: Escalation behavior preserved after simplification

**Property:** Property 4 from design.md
**Validates:** 89-REQ-1.1, 89-REQ-1.2
**Type:** property
**Description:** Escalation ladder retries N times at starting tier, then
escalates, preserving existing behavior.

**For any:** retries_before_escalation in [0, 1, 2, 3], starting_tier in [SIMPLE, STANDARD]
**Invariant:** After retries_before_escalation + 1 failures, tier has escalated.

**Assertion pseudocode:**
```
FOR ANY retries IN [0, 1, 2, 3]:
    FOR ANY start IN [SIMPLE, STANDARD]:
        ladder = EscalationLadder(start, ADVANCED, retries)
        FOR i IN range(retries + 1):
            ladder.record_failure()
        ASSERT ladder.current_tier > start  # escalated
```

### TS-89-P5: Unknown archetype always falls back to coder

**Property:** Property 5 from design.md
**Validates:** 89-REQ-1.E1
**Type:** property
**Description:** Any string not in ARCHETYPE_REGISTRY yields coder defaults.

**For any:** name drawn from arbitrary non-registry strings
**Invariant:** get_archetype(name).default_model_tier == "STANDARD"

**Assertion pseudocode:**
```
FOR ANY name IN ["xyz", "unknown", "", "foo_bar"]:
    entry = get_archetype(name)
    ASSERT entry.default_model_tier == "STANDARD"
```

## Integration Smoke Tests

### TS-89-SMOKE-1: Orchestrator dispatch creates ladder without pipeline

**Execution Path:** Path 1 from design.md
**Description:** Full orchestrator dispatch creates an escalation ladder from
archetype defaults without importing any prediction pipeline modules.

**Setup:** Mock session_runner_factory to return a passing session. Build a
minimal single-node plan with archetype "coder". Do NOT mock
AssessmentManager or EscalationLadder.

**Trigger:** Call orchestrator.run() with the single-node plan.

**Expected side effects:**
- Node is dispatched and completes.
- An EscalationLadder exists for the node in the assessment manager.
- The ladder's starting tier is STANDARD (coder default).
- No ImportError from removed modules during execution.

**Must NOT satisfy with:** Mocking AssessmentManager.assess_node or
EscalationLadder -- these must be the real implementations.

**Assertion pseudocode:**
```
config = minimal_orchestrator_config()
plan = single_node_plan(archetype="coder")
runner_factory = mock_passing_session_runner()
orchestrator = Orchestrator(config, plan, runner_factory)
await orchestrator.run()
ladder = orchestrator._routing.ladders["spec:1"]
ASSERT ladder.current_tier == ModelTier.STANDARD
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 89-REQ-1.1 | TS-89-1 | unit |
| 89-REQ-1.2 | TS-89-2 | unit |
| 89-REQ-1.3 | TS-89-3 | unit |
| 89-REQ-1.E1 | TS-89-E1 | unit |
| 89-REQ-2.1 | TS-89-4 | unit |
| 89-REQ-2.2 | TS-89-5 | unit |
| 89-REQ-2.3 | TS-89-7 | unit |
| 89-REQ-2.4 | TS-89-6 | unit |
| 89-REQ-3.1 | TS-89-8 | unit |
| 89-REQ-3.2 | TS-89-9 | unit |
| 89-REQ-4.1 | TS-89-10 | unit |
| 89-REQ-4.2 | TS-89-10 | unit |
| 89-REQ-5.1 | TS-89-11 | unit |
| 89-REQ-5.2 | TS-89-11 | unit |
| 89-REQ-5.3 | TS-89-SMOKE-1 | integration |
| 89-REQ-6.1 | TS-89-12 | unit |
| 89-REQ-7.1 | TS-89-13 | unit |
| Property 1 | TS-89-P1 | property |
| Property 2 | TS-89-P2 | property |
| Property 3 | TS-89-P3 | property |
| Property 4 | TS-89-P4 | property |
| Property 5 | TS-89-P5 | property |
| Path 1 | TS-89-SMOKE-1 | integration |
