# Test Specification: Timeout-Aware Escalation

## Overview

Tests validate four areas: (1) timeout detection and routing in the result
handler, (2) independent timeout retry counter, (3) parameter extension
math, and (4) configuration validation. Each test maps to a requirement
and/or correctness property.

## Test Cases

### TS-75-1: Timeout Routed to Timeout Handler

**Requirement:** 75-REQ-1.1
**Type:** unit
**Description:** Verify status "timeout" is routed to `_handle_timeout()`
instead of the escalation ladder.

**Preconditions:**
- SessionResultHandler with a mock escalation ladder.
- `max_timeout_retries >= 1`.

**Input:**
- SessionRecord with `status="timeout"`.

**Expected:**
- `_handle_timeout()` is called.
- Escalation ladder's `record_failure()` is NOT called.

**Assertion pseudocode:**
```
handler = SessionResultHandler(...)
record = SessionRecord(status="timeout", ...)
handler.process(record, attempt=1, ...)
ASSERT handler._handle_timeout_called == True
ASSERT ladder.record_failure.call_count == 0
```

### TS-75-2: Non-Timeout Failure Uses Escalation Ladder

**Requirement:** 75-REQ-1.2
**Type:** unit
**Description:** Verify status "failed" still uses the escalation ladder.

**Preconditions:**
- SessionResultHandler with a mock escalation ladder.

**Input:**
- SessionRecord with `status="failed"`.

**Expected:**
- Escalation ladder's `record_failure()` IS called.
- `_handle_timeout()` is NOT called.

**Assertion pseudocode:**
```
record = SessionRecord(status="failed", ...)
handler.process(record, ...)
ASSERT ladder.record_failure.call_count == 1
```

### TS-75-3: Timeout Detected by Status String

**Requirement:** 75-REQ-1.3
**Type:** unit
**Description:** Verify only `status == "timeout"` triggers timeout handling.

**Preconditions:**
- None.

**Input:**
- Records with statuses: "timeout", "failed", "completed".

**Expected:**
- Only "timeout" triggers `_handle_timeout()`.

**Assertion pseudocode:**
```
FOR status IN ["timeout", "failed", "completed"]:
    record = SessionRecord(status=status, ...)
    handler.process(record, ...)
ASSERT timeout_handler_calls == 1  # only for "timeout"
```

### TS-75-4: Failed Status With "timeout" in Error Message

**Requirement:** 75-REQ-1.E1
**Type:** unit
**Description:** Verify status "failed" with "timeout" in error message
does NOT trigger timeout handling.

**Preconditions:**
- None.

**Input:**
- SessionRecord with `status="failed"`,
  `error_message="Connection timeout after 30s"`.

**Expected:**
- Routed to escalation ladder, NOT timeout handler.

**Assertion pseudocode:**
```
record = SessionRecord(status="failed", error_message="Connection timeout after 30s")
handler.process(record, ...)
ASSERT ladder.record_failure.call_count == 1
ASSERT timeout_handler_calls == 0
```

### TS-75-5: Timeout Counter Increments Independently

**Requirement:** 75-REQ-2.1, 75-REQ-2.2
**Type:** unit
**Description:** Verify timeout retry counter increments without affecting
escalation ladder.

**Preconditions:**
- `max_timeout_retries = 2`.
- Fresh handler with no prior retries.

**Input:**
- Two consecutive timeout records for the same node.

**Expected:**
- `_timeout_retries[node_id]` == 2.
- Escalation ladder state unchanged.

**Assertion pseudocode:**
```
handler.process(timeout_record, attempt=1, ...)
handler.process(timeout_record, attempt=2, ...)
ASSERT handler._timeout_retries["node1"] == 2
ASSERT ladder.attempt_count == 1  # unchanged
```

### TS-75-6: Retry at Same Tier When Counter Below Max

**Requirement:** 75-REQ-2.3
**Type:** unit
**Description:** Verify timeout retry resets node to pending at same tier.

**Preconditions:**
- `max_timeout_retries = 2`, counter at 0.

**Input:**
- Timeout record.

**Expected:**
- Node status set to "pending".
- Escalation ladder current_tier unchanged.

**Assertion pseudocode:**
```
handler.process(timeout_record, ...)
ASSERT graph_sync.node_states["node1"] == "pending"
ASSERT ladder.current_tier == ModelTier.STANDARD  # unchanged
```

### TS-75-7: Fall Through When Counter Reaches Max

**Requirement:** 75-REQ-2.4
**Type:** unit
**Description:** Verify escalation ladder is invoked when timeout retries
exhausted.

**Preconditions:**
- `max_timeout_retries = 2`, counter at 2.

**Input:**
- Third timeout record.

**Expected:**
- Escalation ladder's `record_failure()` IS called.

**Assertion pseudocode:**
```
handler._timeout_retries["node1"] = 2
handler.process(timeout_record, ...)
ASSERT ladder.record_failure.call_count == 1
```

### TS-75-8: Mixed Timeout and Logical Failures

**Requirement:** 75-REQ-2.E1
**Type:** unit
**Description:** Verify timeout and failure counters are independent when
mixed.

**Preconditions:**
- `max_timeout_retries = 2`, `retries_before_escalation = 1`.

**Input:**
- Sequence: timeout, failed, timeout, failed.

**Expected:**
- Timeout counter reaches 2 (from 2 timeouts).
- Escalation ladder records 2 failures (from 2 failed records).
- Counters are independent.

**Assertion pseudocode:**
```
handler.process(timeout_record, ...)  # timeout_retries = 1
handler.process(failed_record, ...)   # ladder failures = 1
handler.process(timeout_record, ...)  # timeout_retries = 2
handler.process(failed_record, ...)   # ladder failures = 2
ASSERT handler._timeout_retries["node1"] == 2
ASSERT ladder._total_failures == 2
```

### TS-75-9: Zero Max Timeout Retries Skips Handling

**Requirement:** 75-REQ-2.E2
**Type:** unit
**Description:** Verify timeout goes directly to escalation ladder when
max_timeout_retries is 0.

**Preconditions:**
- `max_timeout_retries = 0`.

**Input:**
- Timeout record.

**Expected:**
- Escalation ladder's `record_failure()` called immediately.
- No timeout retry attempted.

**Assertion pseudocode:**
```
handler = SessionResultHandler(max_timeout_retries=0, ...)
handler.process(timeout_record, ...)
ASSERT ladder.record_failure.call_count == 1
ASSERT handler._timeout_retries.get("node1", 0) == 0
```

### TS-75-10: Max Turns Extended by Multiplier

**Requirement:** 75-REQ-3.1
**Type:** unit
**Description:** Verify max_turns is multiplied and rounded up.

**Preconditions:**
- Original max_turns = 200, timeout_multiplier = 1.5.

**Input:**
- Timeout retry triggered.

**Expected:**
- Extended max_turns = ceil(200 * 1.5) = 300.

**Assertion pseudocode:**
```
handler._extend_node_params("node1")
ASSERT handler._node_max_turns["node1"] == 300
```

### TS-75-11: Session Timeout Extended by Multiplier

**Requirement:** 75-REQ-3.2
**Type:** unit
**Description:** Verify session_timeout is multiplied and rounded up.

**Preconditions:**
- Original session_timeout = 30, timeout_multiplier = 1.5.

**Input:**
- Timeout retry triggered.

**Expected:**
- Extended session_timeout = ceil(30 * 1.5) = 45.

**Assertion pseudocode:**
```
handler._extend_node_params("node1")
ASSERT handler._node_timeout["node1"] == 45
```

### TS-75-12: Timeout Clamped to Ceiling

**Requirement:** 75-REQ-3.3
**Type:** unit
**Description:** Verify extended timeout does not exceed ceiling.

**Preconditions:**
- Original timeout = 30, multiplier = 1.5, ceiling = 2.0.
- After first retry: 45. After second retry: would be 68 but ceiling = 60.

**Input:**
- Two consecutive timeout retries.

**Expected:**
- First retry: 45 minutes.
- Second retry: clamped to 60 minutes (30 * 2.0).

**Assertion pseudocode:**
```
handler._extend_node_params("node1")  # 45
handler._extend_node_params("node1")  # min(ceil(45*1.5), 60) = 60
ASSERT handler._node_timeout["node1"] == 60
```

### TS-75-13: Unlimited Turns Not Modified

**Requirement:** 75-REQ-3.4
**Type:** unit
**Description:** Verify max_turns=None stays None after timeout retry.

**Preconditions:**
- Original max_turns = None (unlimited).

**Input:**
- Timeout retry triggered.

**Expected:**
- max_turns remains None.

**Assertion pseudocode:**
```
handler._node_max_turns["node1"] = None
handler._extend_node_params("node1")
ASSERT handler._node_max_turns["node1"] is None
```

### TS-75-14: Per-Node Parameter Isolation

**Requirement:** 75-REQ-3.5
**Type:** unit
**Description:** Verify extending one node's params doesn't affect others.

**Preconditions:**
- Two nodes: node1 and node2.

**Input:**
- Timeout retry for node1 only.

**Expected:**
- node1 params extended.
- node2 params unchanged (not in override dicts).

**Assertion pseudocode:**
```
handler._extend_node_params("node1")
ASSERT "node1" in handler._node_timeout
ASSERT "node2" not in handler._node_timeout
```

### TS-75-15: Ceiling Clamp

**Requirement:** 75-REQ-3.E1
**Type:** unit
**Description:** Verify ceiling clamp works correctly.

**Preconditions:**
- Original timeout = 20, multiplier = 2.0, ceiling = 1.5.
- First retry would be 40, ceiling = 30.

**Input:**
- Timeout retry.

**Expected:**
- Clamped to 30 (20 * 1.5 ceiling).

**Assertion pseudocode:**
```
handler._extend_node_params("node1")
ASSERT handler._node_timeout["node1"] == 30
```

### TS-75-16: Config Default Values

**Requirement:** 75-REQ-4.1, 75-REQ-4.2, 75-REQ-4.3
**Type:** unit
**Description:** Verify default configuration values.

**Preconditions:**
- Default RoutingConfig.

**Input:**
- `RoutingConfig()` with no overrides.

**Expected:**
- `max_timeout_retries == 2`
- `timeout_multiplier == 1.5`
- `timeout_ceiling_factor == 2.0`

**Assertion pseudocode:**
```
config = RoutingConfig()
ASSERT config.max_timeout_retries == 2
ASSERT config.timeout_multiplier == 1.5
ASSERT config.timeout_ceiling_factor == 2.0
```

### TS-75-17: Config Validation - Negative Retries

**Requirement:** 75-REQ-4.4
**Type:** unit
**Description:** Verify negative max_timeout_retries is rejected or clamped.

**Preconditions:**
- None.

**Input:**
- `RoutingConfig(max_timeout_retries=-1)`.

**Expected:**
- Validation error or clamped to 0.

**Assertion pseudocode:**
```
config = RoutingConfig(max_timeout_retries=-1)
ASSERT config.max_timeout_retries >= 0
```

### TS-75-18: Config Validation - Multiplier Below 1.0

**Requirement:** 75-REQ-4.5
**Type:** unit
**Description:** Verify timeout_multiplier < 1.0 is rejected or clamped.

**Preconditions:**
- None.

**Input:**
- `RoutingConfig(timeout_multiplier=0.5)`.

**Expected:**
- Validation error or clamped to 1.0.

**Assertion pseudocode:**
```
config = RoutingConfig(timeout_multiplier=0.5)
ASSERT config.timeout_multiplier >= 1.0
```

### TS-75-19: Config Validation - Ceiling Below 1.0

**Requirement:** 75-REQ-4.6
**Type:** unit
**Description:** Verify timeout_ceiling_factor < 1.0 is rejected or clamped.

**Preconditions:**
- None.

**Input:**
- `RoutingConfig(timeout_ceiling_factor=0.8)`.

**Expected:**
- Validation error or clamped to 1.0.

**Assertion pseudocode:**
```
config = RoutingConfig(timeout_ceiling_factor=0.8)
ASSERT config.timeout_ceiling_factor >= 1.0
```

### TS-75-20: Multiplier 1.0 No Extension

**Requirement:** 75-REQ-4.E1
**Type:** unit
**Description:** Verify multiplier=1.0 means same params on retry.

**Preconditions:**
- `timeout_multiplier = 1.0`, original timeout = 30, max_turns = 200.

**Input:**
- Timeout retry.

**Expected:**
- Extended timeout = 30 (unchanged).
- Extended max_turns = 200 (unchanged).

**Assertion pseudocode:**
```
handler._extend_node_params("node1")
ASSERT handler._node_timeout["node1"] == 30
ASSERT handler._node_max_turns["node1"] == 200
```

### TS-75-21: Timeout Retry Audit Event

**Requirement:** 75-REQ-5.1
**Type:** unit
**Description:** Verify SESSION_TIMEOUT_RETRY event is emitted.

**Preconditions:**
- Mock sink.

**Input:**
- Timeout record processed with retries remaining.

**Expected:**
- SESSION_TIMEOUT_RETRY event emitted with correct payload fields.

**Assertion pseudocode:**
```
handler.process(timeout_record, ...)
event = find_event(sink, SESSION_TIMEOUT_RETRY)
ASSERT event is not None
ASSERT "timeout_retry_count" in event.payload
ASSERT "extended_timeout" in event.payload
```

### TS-75-22: Exhaustion Warning Log

**Requirement:** 75-REQ-5.2
**Type:** unit
**Description:** Verify warning logged when timeout retries exhausted.

**Preconditions:**
- `max_timeout_retries = 1`, counter at 1.
- caplog fixture.

**Input:**
- Timeout record.

**Expected:**
- Warning log mentioning "timeout retries exhausted" or equivalent.

**Assertion pseudocode:**
```
with caplog:
    handler.process(timeout_record, ...)
ASSERT any("exhausted" in r.message for r in caplog.records if r.levelname == "WARNING")
```

### TS-75-23: Audit Event Payload Contains Original and Extended Values

**Requirement:** 75-REQ-5.3
**Type:** unit
**Description:** Verify payload includes before/after values.

**Preconditions:**
- Mock sink.

**Input:**
- Timeout retry with original timeout=30, max_turns=200, multiplier=1.5.

**Expected:**
- Payload: `original_timeout=30, extended_timeout=45,
  original_max_turns=200, extended_max_turns=300`.

**Assertion pseudocode:**
```
event = find_event(sink, SESSION_TIMEOUT_RETRY)
ASSERT event.payload["original_timeout"] == 30
ASSERT event.payload["extended_timeout"] == 45
ASSERT event.payload["original_max_turns"] == 200
ASSERT event.payload["extended_max_turns"] == 300
```

## Property Test Cases

### TS-75-P1: Timeout Never Directly Escalates

**Property:** Property 1 from design.md
**Validates:** 75-REQ-1.1, 75-REQ-2.2
**Type:** property
**Description:** With retries remaining, timeout never calls record_failure().

**For any:** timeout_count in [1..max_timeout_retries]
**Invariant:** After processing timeout_count timeouts, escalation ladder
failures == 0.

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, max_timeout_retries):
    handler = fresh_handler(max_timeout_retries=max_timeout_retries)
    FOR i IN range(n):
        handler.process(timeout_record, ...)
    ASSERT ladder.record_failure.call_count == 0
```

### TS-75-P2: Counter Independence

**Property:** Property 2 from design.md
**Validates:** 75-REQ-2.1, 75-REQ-2.E1
**Type:** property
**Description:** Interleaved timeouts and failures maintain independent counts.

**For any:** sequence of (timeout | failure) events, length 1-10
**Invariant:** timeout_count == number of "timeout" events (capped at max),
ladder_failures == number of "failure" events.

**Assertion pseudocode:**
```
FOR ANY events IN lists(sampled_from(["timeout", "failed"]), min=1, max=10):
    handler = fresh_handler()
    FOR event in events:
        handler.process(record(status=event), ...)
    expected_timeouts = min(sum(1 for e in events if e == "timeout"), max_timeout_retries)
    expected_failures = sum(1 for e in events if e == "failed")
    # Plus any timeouts that fell through after exhaustion
    ...
```

### TS-75-P3: Monotonic Timeout Extension

**Property:** Property 3 from design.md
**Validates:** 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.E1
**Type:** property
**Description:** Extended timeout is non-decreasing and bounded by ceiling.

**For any:** original_timeout in [1..120], multiplier in [1.0..3.0],
ceiling_factor in [1.0..5.0], retry_count in [1..5]
**Invariant:** Each extended timeout >= previous AND <= original * ceiling.

**Assertion pseudocode:**
```
FOR ANY (timeout, mult, ceil_f, retries) IN ...:
    prev = timeout
    FOR i IN range(retries):
        extended = min(ceil(prev * mult), ceil(timeout * ceil_f))
        ASSERT extended >= prev
        ASSERT extended <= ceil(timeout * ceil_f)
        prev = extended
```

### TS-75-P4: Timeout Exhaustion Falls Through

**Property:** Property 4 from design.md
**Validates:** 75-REQ-2.4
**Type:** property
**Description:** After max_timeout_retries, next timeout hits escalation.

**For any:** max_timeout_retries in [0..5]
**Invariant:** After exactly max_timeout_retries timeouts, the
(max_timeout_retries + 1)th timeout calls record_failure().

**Assertion pseudocode:**
```
FOR ANY max_retries IN integers(0, 5):
    handler = fresh_handler(max_timeout_retries=max_retries)
    FOR i IN range(max_retries):
        handler.process(timeout_record, ...)
    ASSERT ladder.record_failure.call_count == 0
    handler.process(timeout_record, ...)  # one more
    ASSERT ladder.record_failure.call_count == 1
```

### TS-75-P5: Unlimited Turns Preserved

**Property:** Property 5 from design.md
**Validates:** 75-REQ-3.4
**Type:** property
**Description:** None max_turns stays None through any number of retries.

**For any:** retry_count in [1..10]
**Invariant:** max_turns remains None.

**Assertion pseudocode:**
```
FOR ANY retries IN integers(1, 10):
    handler._node_max_turns["node1"] = None
    FOR i IN range(retries):
        handler._extend_node_params("node1")
    ASSERT handler._node_max_turns["node1"] is None
```

### TS-75-P6: Config Validation Bounds

**Property:** Property 6 from design.md
**Validates:** 75-REQ-4.4, 75-REQ-4.5, 75-REQ-4.6
**Type:** property
**Description:** Config fields are always within valid bounds.

**For any:** max_timeout_retries in [-10..100], multiplier in [0.0..10.0],
ceiling in [0.0..10.0]
**Invariant:** After construction/validation, all fields are within bounds.

**Assertion pseudocode:**
```
FOR ANY (retries, mult, ceil_f) IN ...:
    config = RoutingConfig(
        max_timeout_retries=retries,
        timeout_multiplier=mult,
        timeout_ceiling_factor=ceil_f,
    )
    ASSERT config.max_timeout_retries >= 0
    ASSERT config.timeout_multiplier >= 1.0
    ASSERT config.timeout_ceiling_factor >= 1.0
```

## Edge Case Tests

### TS-75-E1: Single Timeout Then Success

**Requirement:** 75-REQ-2.3
**Type:** integration
**Description:** Verify timeout → extended retry → success flow.

**Preconditions:**
- Mock backend: first call times out, second call succeeds.

**Input:**
- Run session that times out, then succeeds with extended params.

**Expected:**
- First session: timeout, retry initiated.
- Second session: success with extended timeout.

**Assertion pseudocode:**
```
run_session_sequence([timeout, success])
ASSERT final_status == "completed"
ASSERT sessions_run == 2
```

### TS-75-E2: All Retries Exhaust Then Escalate Then Succeed

**Requirement:** 75-REQ-2.4
**Type:** integration
**Description:** Verify timeout exhaustion → escalation → success flow.

**Preconditions:**
- `max_timeout_retries = 1`, `retries_before_escalation = 1`.
- Mock: 2 timeouts, then 1 failure at STANDARD, then success at ADVANCED.

**Input:**
- Sequence: timeout, timeout (exhausted), escalation to ADVANCED, success.

**Expected:**
- 2 timeout retries at STANDARD.
- 1 escalation to ADVANCED.
- Final success.

**Assertion pseudocode:**
```
run_sequence([timeout, timeout, success_at_advanced])
ASSERT final_tier == ModelTier.ADVANCED
ASSERT final_status == "completed"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 75-REQ-1.1 | TS-75-1, TS-75-P1 | unit, property |
| 75-REQ-1.2 | TS-75-2 | unit |
| 75-REQ-1.3 | TS-75-3 | unit |
| 75-REQ-1.E1 | TS-75-4 | unit |
| 75-REQ-2.1 | TS-75-5, TS-75-P2 | unit, property |
| 75-REQ-2.2 | TS-75-5, TS-75-P1 | unit, property |
| 75-REQ-2.3 | TS-75-6, TS-75-E1 | unit, integration |
| 75-REQ-2.4 | TS-75-7, TS-75-P4, TS-75-E2 | unit, property, integration |
| 75-REQ-2.E1 | TS-75-8, TS-75-P2 | unit, property |
| 75-REQ-2.E2 | TS-75-9 | unit |
| 75-REQ-3.1 | TS-75-10 | unit |
| 75-REQ-3.2 | TS-75-11, TS-75-P3 | unit, property |
| 75-REQ-3.3 | TS-75-12, TS-75-P3 | unit, property |
| 75-REQ-3.4 | TS-75-13, TS-75-P5 | unit, property |
| 75-REQ-3.5 | TS-75-14 | unit |
| 75-REQ-3.E1 | TS-75-15, TS-75-P3 | unit, property |
| 75-REQ-3.E2 | — | — (backend handles) |
| 75-REQ-4.1 | TS-75-16 | unit |
| 75-REQ-4.2 | TS-75-16 | unit |
| 75-REQ-4.3 | TS-75-16 | unit |
| 75-REQ-4.4 | TS-75-17, TS-75-P6 | unit, property |
| 75-REQ-4.5 | TS-75-18, TS-75-P6 | unit, property |
| 75-REQ-4.6 | TS-75-19, TS-75-P6 | unit, property |
| 75-REQ-4.E1 | TS-75-20 | unit |
| 75-REQ-5.1 | TS-75-21 | unit |
| 75-REQ-5.2 | TS-75-22 | unit |
| 75-REQ-5.3 | TS-75-23 | unit |
| Property 1 | TS-75-P1 | property |
| Property 2 | TS-75-P2 | property |
| Property 3 | TS-75-P3 | property |
| Property 4 | TS-75-P4 | property |
| Property 5 | TS-75-P5 | property |
| Property 6 | TS-75-P6 | property |
