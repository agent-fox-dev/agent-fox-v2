# Test Specification: Predecessor Escalation

## Overview

Tests verify that reviewer-triggered resets correctly record failures on the
predecessor's escalation ladder, trigger tier escalation, and block the
predecessor when all tiers are exhausted. Tests use mock orchestrator state
to exercise the `_process_session_result` code path directly.

## Test Cases

### TS-58-1: Reviewer Failure Records on Predecessor Ladder

**Requirement:** 58-REQ-1.1
**Type:** unit
**Description:** Verify that when a reviewer with `retry_predecessor` fails, a failure is recorded on the predecessor's escalation ladder.

**Preconditions:**
- Orchestrator with a graph: Coder node `spec:1` → Verifier node `spec:2`.
- Coder has an escalation ladder at STANDARD with `retries_before_escalation=1`.
- Verifier fails (session record with `status="failed"`).

**Input:**
- Call `_process_session_result` with the failed Verifier record.

**Expected:**
- Predecessor ladder `attempt_count` increases by 1.

**Assertion pseudocode:**
```
pred_ladder = orchestrator._routing.ladders["spec:1"]
initial_count = pred_ladder.attempt_count
process_session_result(failed_verifier_record)
ASSERT pred_ladder.attempt_count == initial_count + 1
```

### TS-58-2: Predecessor Reset to Pending After Recorded Failure

**Requirement:** 58-REQ-1.2
**Type:** unit
**Description:** Verify that the predecessor is reset to pending when its ladder is not exhausted.

**Preconditions:**
- Same as TS-58-1, first failure (ladder not exhausted).

**Input:**
- Call `_process_session_result` with the failed Verifier record.

**Expected:**
- Predecessor status is `"pending"`.
- Reviewer status is `"pending"`.

**Assertion pseudocode:**
```
process_session_result(failed_verifier_record)
ASSERT graph_sync.node_states["spec:1"] == "pending"
ASSERT graph_sync.node_states["spec:2"] == "pending"
```

### TS-58-3: Predecessor Escalates After Retries Exhausted at Tier

**Requirement:** 58-REQ-1.3
**Type:** unit
**Description:** Verify that the predecessor escalates from STANDARD to ADVANCED after exhausting retries at STANDARD.

**Preconditions:**
- Coder ladder at STANDARD, `retries_before_escalation=1`, ceiling ADVANCED.

**Input:**
- Process 2 reviewer failures (1 retry + 1 triggers escalation).

**Expected:**
- After 2nd failure, predecessor ladder `current_tier == ADVANCED`.
- Predecessor status is `"pending"` (not blocked, still has ADVANCED to try).

**Assertion pseudocode:**
```
process_session_result(failed_verifier_record_1)
ASSERT pred_ladder.current_tier == ModelTier.STANDARD  # still at STANDARD
process_session_result(failed_verifier_record_2)
ASSERT pred_ladder.current_tier == ModelTier.ADVANCED   # escalated
ASSERT graph_sync.node_states["spec:1"] == "pending"
```

### TS-58-4: Predecessor Blocks on Ladder Exhaustion

**Requirement:** 58-REQ-2.1
**Type:** unit
**Description:** Verify that the predecessor is blocked when its ladder is exhausted.

**Preconditions:**
- Coder ladder at ADVANCED (ceiling), `retries_before_escalation=1`.

**Input:**
- Process 2 reviewer failures (1 retry + 1 exhausts ladder).

**Expected:**
- Predecessor status is `"blocked"`.
- Dependents of the predecessor are cascade-blocked.

**Assertion pseudocode:**
```
process_session_result(failed_verifier_record_1)
process_session_result(failed_verifier_record_2)
ASSERT graph_sync.node_states["spec:1"] == "blocked"
ASSERT pred_ladder.is_exhausted == True
```

### TS-58-5: Outcome Recorded on Predecessor Block

**Requirement:** 58-REQ-2.2
**Type:** unit
**Description:** Verify that `_record_node_outcome` is called with "failed" when the predecessor blocks.

**Preconditions:**
- Coder ladder at ADVANCED, `retries_before_escalation=0` (immediate exhaustion after 1 failure).

**Input:**
- Process 1 reviewer failure.

**Expected:**
- `_record_node_outcome` called with `(pred_id, state, "failed")`.

**Assertion pseudocode:**
```
with mock _record_node_outcome as mock_record:
    process_session_result(failed_verifier_record)
    ASSERT mock_record.called_with("spec:1", state, "failed")
```

### TS-58-6: Neither Node Reset When Predecessor Blocks

**Requirement:** 58-REQ-2.3
**Type:** unit
**Description:** Verify that neither the predecessor nor the reviewer is reset to pending when the predecessor blocks.

**Preconditions:**
- Coder ladder exhausted after reviewer failure.

**Input:**
- Process reviewer failure that triggers predecessor exhaustion.

**Expected:**
- Predecessor is `"blocked"`, not `"pending"`.
- Reviewer is NOT reset to `"pending"`.

**Assertion pseudocode:**
```
process_session_result(failed_verifier_record)
ASSERT graph_sync.node_states["spec:1"] == "blocked"
ASSERT graph_sync.node_states["spec:2"] != "pending"
```

### TS-58-7: Multiple Reviewers Share Predecessor Ladder

**Requirement:** 58-REQ-3.1
**Type:** unit
**Description:** Verify that failures from Verifier and Auditor both accumulate on the same predecessor ladder.

**Preconditions:**
- Graph: Coder `spec:1` → Verifier `spec:2`, Coder `spec:1` → Auditor `spec:1:auditor`.
- Coder ladder at STANDARD, `retries_before_escalation=2`.

**Input:**
- Process 1 Verifier failure, then 1 Auditor failure, then 1 Verifier failure.

**Expected:**
- Predecessor ladder `attempt_count == 4` (1 initial + 3 failures).
- After 3rd failure, predecessor escalates to ADVANCED.

**Assertion pseudocode:**
```
process_session_result(failed_verifier)
ASSERT pred_ladder.attempt_count == 2
process_session_result(failed_auditor)
ASSERT pred_ladder.attempt_count == 3
process_session_result(failed_verifier_2)
ASSERT pred_ladder.attempt_count == 4
ASSERT pred_ladder.current_tier == ModelTier.ADVANCED
```

### TS-58-8: Cumulative Escalation Decision

**Requirement:** 58-REQ-3.2
**Type:** unit
**Description:** Verify that the escalation decision is based on cumulative failure count, not per-reviewer.

**Preconditions:**
- Coder ladder at STANDARD, `retries_before_escalation=1`.

**Input:**
- 1 Verifier failure + 1 Auditor failure (total 2).

**Expected:**
- Ladder escalates after the 2nd failure regardless of which reviewer caused it.

**Assertion pseudocode:**
```
process_session_result(failed_verifier)
ASSERT pred_ladder.current_tier == ModelTier.STANDARD
process_session_result(failed_auditor)
ASSERT pred_ladder.current_tier == ModelTier.ADVANCED
```

## Property Test Cases

### TS-58-P1: Reviewer Resets Accumulate on Predecessor Ladder

**Property:** Property 1 from design.md
**Validates:** 58-REQ-1.1, 58-REQ-3.1, 58-REQ-3.2
**Type:** property
**Description:** For any number of reviewer-triggered resets, the predecessor's ladder attempt count equals 1 plus the number of resets.

**For any:** Number of reviewer failures N in range [1, 10]
**Invariant:** After N `record_failure()` calls on the predecessor ladder, `attempt_count == N + 1`.

**Assertion pseudocode:**
```
FOR ANY n IN range(1, 11):
    ladder = EscalationLadder(STANDARD, ADVANCED, retries_before_escalation=3)
    FOR i IN range(n):
        ladder.record_failure()
    ASSERT ladder.attempt_count == n + 1
```

### TS-58-P2: Predecessor Escalates After N+1 Failures

**Property:** Property 2 from design.md
**Validates:** 58-REQ-1.3
**Type:** property
**Description:** For any retries_before_escalation N, a STANDARD predecessor escalates after N+1 reviewer-triggered failures.

**For any:** `retries_before_escalation` in range [0, 3]
**Invariant:** After `N + 1` reviewer-triggered failures, `current_tier == ADVANCED`.

**Assertion pseudocode:**
```
FOR ANY n IN range(0, 4):
    ladder = EscalationLadder(STANDARD, ADVANCED, retries_before_escalation=n)
    FOR i IN range(n + 1):
        ladder.record_failure()
    ASSERT ladder.current_tier == ModelTier.ADVANCED
```

### TS-58-P3: Exhausted Predecessor Is Blocked

**Property:** Property 3 from design.md
**Validates:** 58-REQ-2.1, 58-REQ-2.3
**Type:** property
**Description:** For any predecessor whose ladder is exhausted, status is blocked and not reset.

**For any:** Starting tier in {STANDARD, ADVANCED}, `retries_before_escalation` in [0, 3]
**Invariant:** When `is_exhausted == True`, the predecessor must not be set to pending.

**Assertion pseudocode:**
```
FOR ANY starting IN [STANDARD, ADVANCED]:
    FOR ANY n IN range(0, 4):
        ladder = EscalationLadder(starting, ADVANCED, retries_before_escalation=n)
        WHILE NOT ladder.is_exhausted:
            ladder.record_failure()
        ASSERT ladder.is_exhausted == True
        # In orchestrator context: predecessor status == "blocked"
```

### TS-58-P4: Missing Ladder Created Defensively

**Property:** Property 4 from design.md
**Validates:** 58-REQ-1.E1
**Type:** property
**Description:** For any archetype, a missing predecessor ladder is created with correct defaults.

**For any:** Archetype name from the registry
**Invariant:** Created ladder has `starting_tier == archetype.default_model_tier` and `tier_ceiling == ADVANCED`.

**Assertion pseudocode:**
```
FOR ANY name IN ARCHETYPE_REGISTRY.keys():
    entry = ARCHETYPE_REGISTRY[name]
    ladder = EscalationLadder(
        ModelTier(entry.default_model_tier),
        ModelTier.ADVANCED,
        retries_before_escalation=1,
    )
    ASSERT ladder._tier_ceiling == ModelTier.ADVANCED
    ASSERT ladder.current_tier == ModelTier(entry.default_model_tier)
```

## Edge Case Tests

### TS-58-E1: Predecessor Has No Ladder

**Requirement:** 58-REQ-1.E1
**Type:** unit
**Description:** Verify that a ladder is created for the predecessor if none exists when retry_predecessor fires.

**Preconditions:**
- Coder node `spec:1` has no entry in `_routing.ladders`.
- Verifier with `retry_predecessor=True` fails.

**Input:**
- Call `_process_session_result` with the failed Verifier record.

**Expected:**
- A ladder is created in `_routing.ladders["spec:1"]`.
- The ladder has `starting_tier` matching the Coder's archetype default.
- The ladder has `tier_ceiling == ADVANCED`.

**Assertion pseudocode:**
```
ASSERT "spec:1" NOT IN orchestrator._routing.ladders
process_session_result(failed_verifier_record)
ASSERT "spec:1" IN orchestrator._routing.ladders
pred_ladder = orchestrator._routing.ladders["spec:1"]
ASSERT pred_ladder._tier_ceiling == ModelTier.ADVANCED
```

### TS-58-E2: Predecessor Already at ADVANCED Ceiling

**Requirement:** 58-REQ-2.E1
**Type:** unit
**Description:** Verify that a predecessor starting at ADVANCED blocks after exhausting retries (no tier to escalate to).

**Preconditions:**
- Coder ladder at ADVANCED, `retries_before_escalation=1`, ceiling ADVANCED.

**Input:**
- Process 2 reviewer failures.

**Expected:**
- Predecessor ladder `is_exhausted == True`.
- Predecessor status is `"blocked"`.

**Assertion pseudocode:**
```
pred_ladder = EscalationLadder(ADVANCED, ADVANCED, retries_before_escalation=1)
orchestrator._routing.ladders["spec:1"] = pred_ladder
process_session_result(failed_verifier_1)
process_session_result(failed_verifier_2)
ASSERT pred_ladder.is_exhausted == True
ASSERT graph_sync.node_states["spec:1"] == "blocked"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 58-REQ-1.1 | TS-58-1 | unit |
| 58-REQ-1.2 | TS-58-2 | unit |
| 58-REQ-1.3 | TS-58-3 | unit |
| 58-REQ-1.E1 | TS-58-E1 | unit |
| 58-REQ-2.1 | TS-58-4 | unit |
| 58-REQ-2.2 | TS-58-5 | unit |
| 58-REQ-2.3 | TS-58-6 | unit |
| 58-REQ-2.E1 | TS-58-E2 | unit |
| 58-REQ-3.1 | TS-58-7 | unit |
| 58-REQ-3.2 | TS-58-8 | unit |
| Property 1 | TS-58-P1 | property |
| Property 2 | TS-58-P2 | property |
| Property 3 | TS-58-P3 | property |
| Property 4 | TS-58-P4 | property |
