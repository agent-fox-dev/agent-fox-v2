# Test Specification: Configuration Hot-Reload at Sync Barriers

## Overview

Tests validate the config reload lifecycle: hash-based no-op detection,
field updates, CircuitBreaker reconstruction, immutable field guarding,
error resilience, and audit event emission. All tests mock file I/O and
`load_config` to isolate orchestrator logic.

## Test Cases

### TS-66-1: Reload triggered at sync barrier

**Requirement:** 66-REQ-1.1
**Type:** unit
**Description:** Verify `_reload_config` is called during barrier sequence.

**Preconditions:**
- Orchestrator with `config_path` set.
- Mocked `run_sync_barrier_sequence` with `reload_config_fn`.

**Input:**
- Trigger a sync barrier.

**Expected:**
- The reload callback is invoked.

**Assertion pseudocode:**
```
mock reload_fn
await run_sync_barrier_sequence(..., reload_config_fn=reload_fn)
ASSERT reload_fn called once
```

### TS-66-2: No-op when hash matches

**Requirement:** 66-REQ-1.2, 66-REQ-6.E1
**Type:** unit
**Description:** Verify reload is skipped when file hash hasn't changed.

**Preconditions:**
- Orchestrator with config already loaded, hash stored.
- Config file unchanged.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `self._config` unchanged.
- No audit event emitted.

**Assertion pseudocode:**
```
orch._config_hash = compute_hash(config_file)
old_config = copy(orch._config)
orch._reload_config()
ASSERT orch._config == old_config
ASSERT no CONFIG_RELOADED event emitted
```

### TS-66-3: Reload when hash differs

**Requirement:** 66-REQ-1.3
**Type:** unit
**Description:** Verify config is reloaded when file content changes.

**Preconditions:**
- Orchestrator with old hash. Config file modified.

**Input:**
- Call `_reload_config()` with new config content.

**Expected:**
- Config is re-parsed and applied.
- Hash updated.

**Assertion pseudocode:**
```
orch._config_hash = "old_hash"
mock load_config to return new config with max_cost=100
orch._reload_config()
ASSERT orch._config.max_cost == 100
ASSERT orch._config_hash == compute_hash(new_content)
```

### TS-66-4: OrchestratorConfig fields updated

**Requirement:** 66-REQ-2.1
**Type:** unit
**Description:** Verify all mutable OrchestratorConfig fields are updated.

**Preconditions:**
- Orchestrator with default config.
- New config with changed `max_cost`, `max_retries`, `session_timeout`.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `self._config.max_cost`, `max_retries`, `session_timeout` match new values.

**Assertion pseudocode:**
```
new = OrchestratorConfig(max_cost=200, max_retries=5, session_timeout=60)
mock load_config to return AgentFoxConfig(orchestrator=new)
orch._reload_config()
ASSERT orch._config.max_cost == 200
ASSERT orch._config.max_retries == 5
ASSERT orch._config.session_timeout == 60
```

### TS-66-5: CircuitBreaker reconstructed

**Requirement:** 66-REQ-2.2
**Type:** unit
**Description:** Verify CircuitBreaker is rebuilt with new config.

**Preconditions:**
- Orchestrator with initial CircuitBreaker.
- New config with different `max_cost`.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `self._circuit` is a new `CircuitBreaker` instance.
- `self._circuit._config.max_cost` matches new value.

**Assertion pseudocode:**
```
old_circuit = orch._circuit
mock load_config with max_cost=999
orch._reload_config()
ASSERT orch._circuit is not old_circuit
ASSERT orch._circuit._config.max_cost == 999
```

### TS-66-6: Parallel change logged but not applied

**Requirement:** 66-REQ-3.1, 66-REQ-3.2
**Type:** unit
**Description:** Verify parallel change triggers warning and is not applied.

**Preconditions:**
- Orchestrator with `parallel=2`, `_is_parallel=True`.
- New config with `parallel=4`.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `self._config.parallel` remains 2.
- `self._is_parallel` remains True.
- Warning logged mentioning parallel change.

**Assertion pseudocode:**
```
mock load_config with parallel=4
orch._reload_config()
ASSERT orch._config.parallel == 2
ASSERT orch._is_parallel is True
ASSERT warning logged containing "parallel"
```

### TS-66-7: HookConfig updated

**Requirement:** 66-REQ-4.1
**Type:** unit
**Description:** Verify stored HookConfig is replaced on reload.

**Preconditions:**
- Orchestrator with initial HookConfig.
- New config with different HookConfig.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `self._hook_config` references the new HookConfig.

**Assertion pseudocode:**
```
new_hooks = HookConfig(...)
mock load_config with hooks=new_hooks
orch._reload_config()
ASSERT orch._hook_config == new_hooks
```

### TS-66-8: ArchetypesConfig updated

**Requirement:** 66-REQ-4.2
**Type:** unit
**Description:** Verify stored ArchetypesConfig is replaced on reload.

**Preconditions:**
- Orchestrator with initial ArchetypesConfig.

**Input:**
- Call `_reload_config()` with new ArchetypesConfig.

**Expected:**
- `self._archetypes_config` references the new value.

**Assertion pseudocode:**
```
new_arch = ArchetypesConfig(...)
mock load_config with archetypes=new_arch
orch._reload_config()
ASSERT orch._archetypes_config == new_arch
```

### TS-66-9: PlanningConfig updated

**Requirement:** 66-REQ-4.3
**Type:** unit
**Description:** Verify stored PlanningConfig is replaced on reload.

**Preconditions:**
- Orchestrator with initial PlanningConfig.

**Input:**
- Call `_reload_config()` with new PlanningConfig.

**Expected:**
- `self._planning_config` references the new value.

**Assertion pseudocode:**
```
new_plan = PlanningConfig(file_conflict_detection=True)
mock load_config with planning=new_plan
orch._reload_config()
ASSERT orch._planning_config == new_plan
```

### TS-66-10: Audit event emitted on change

**Requirement:** 66-REQ-6.1, 66-REQ-6.2
**Type:** unit
**Description:** Verify CONFIG_RELOADED event is emitted with changed fields.

**Preconditions:**
- Orchestrator with `max_cost=50`.
- New config with `max_cost=100`.

**Input:**
- Call `_reload_config()`.

**Expected:**
- `CONFIG_RELOADED` audit event emitted.
- Payload contains `changed_fields` with `orchestrator.max_cost`:
  `{"old": 50, "new": 100}`.

**Assertion pseudocode:**
```
mock load_config with max_cost=100
orch._reload_config()
ASSERT audit event of type CONFIG_RELOADED emitted
ASSERT event.payload["changed_fields"]["orchestrator.max_cost"] == {"old": 50.0, "new": 100.0}
```

### TS-66-11: Config path stored at construction

**Requirement:** 66-REQ-7.1, 66-REQ-7.2
**Type:** unit
**Description:** Verify Orchestrator accepts and stores config_path.

**Preconditions:**
- None.

**Input:**
- `Orchestrator(..., config_path=Path(".agent-fox/config.toml"))`.

**Expected:**
- `self._config_path == Path(".agent-fox/config.toml")`.

**Assertion pseudocode:**
```
orch = Orchestrator(..., config_path=Path(".agent-fox/config.toml"))
ASSERT orch._config_path == Path(".agent-fox/config.toml")
```

## Edge Case Tests

### TS-66-E1: Config file missing at reload

**Requirement:** 66-REQ-1.E1
**Type:** unit
**Description:** Verify missing file keeps current config.

**Preconditions:**
- Orchestrator with valid config.
- Config file does not exist.

**Input:**
- Call `_reload_config()`.

**Expected:**
- Config unchanged.
- Warning logged.

**Assertion pseudocode:**
```
orch._config_path = Path("/nonexistent/config.toml")
old = copy(orch._config)
orch._reload_config()
ASSERT orch._config == old
ASSERT warning logged
```

### TS-66-E2: Invalid TOML keeps current config

**Requirement:** 66-REQ-5.1
**Type:** unit
**Description:** Verify parse error preserves current config.

**Preconditions:**
- Orchestrator with valid config.
- Config file contains invalid TOML.

**Input:**
- Call `_reload_config()`.

**Expected:**
- Config unchanged.
- Warning logged with parse error details.

**Assertion pseudocode:**
```
mock load_config to raise ConfigError
old = copy(orch._config)
orch._reload_config()
ASSERT orch._config == old
ASSERT warning logged containing error details
```

### TS-66-E3: I/O error keeps current config

**Requirement:** 66-REQ-5.E1
**Type:** unit
**Description:** Verify I/O error preserves current config.

**Preconditions:**
- Orchestrator with valid config.
- Config file unreadable.

**Input:**
- Call `_reload_config()`.

**Expected:**
- Config unchanged.
- Warning logged.

**Assertion pseudocode:**
```
mock file read to raise OSError
old = copy(orch._config)
orch._reload_config()
ASSERT orch._config == old
ASSERT warning logged
```

### TS-66-E4: sync_interval set to 0 stops future barriers

**Requirement:** 66-REQ-2.E1
**Type:** unit
**Description:** Verify disabling sync_interval mid-run stops barriers.

**Preconditions:**
- Orchestrator with `sync_interval=5`.
- New config with `sync_interval=0`.

**Input:**
- Call `_reload_config()`, then check barrier trigger.

**Expected:**
- `self._config.sync_interval == 0`.
- `_should_trigger_barrier()` returns False.

**Assertion pseudocode:**
```
mock load_config with sync_interval=0
orch._reload_config()
ASSERT orch._config.sync_interval == 0
ASSERT orch._should_trigger_barrier(state) is False
```

## Property Test Cases

### TS-66-P1: No-op on unchanged config

**Property:** Property 1 from design.md
**Validates:** 66-REQ-1.2, 66-REQ-6.E1
**Type:** property
**Description:** Unchanged file produces zero state changes and no audit event.

**For any:** Valid config file content (from Hypothesis text strategy)
**Invariant:** If hash matches, `_reload_config` is a no-op.

**Assertion pseudocode:**
```
FOR ANY config_content IN valid_toml_strategy:
    orch._config_hash = hashlib.sha256(config_content.encode()).hexdigest()
    old_config = deepcopy(orch._config)
    mock file read to return config_content
    orch._reload_config()
    ASSERT orch._config == old_config
    ASSERT no audit event emitted
```

### TS-66-P2: All mutable fields updated

**Property:** Property 2 from design.md
**Validates:** 66-REQ-2.1
**Type:** property
**Description:** Every mutable OrchestratorConfig field is updated on reload.

**For any:** Two different valid OrchestratorConfig instances
**Invariant:** After reload, all mutable fields match the new config (except parallel).

**Assertion pseudocode:**
```
FOR ANY new_orch IN orchestrator_config_strategy:
    mock load_config with orchestrator=new_orch
    orch._reload_config()
    FOR field IN mutable_fields:
        ASSERT getattr(orch._config, field) == getattr(new_orch, field)
```

### TS-66-P3: CircuitBreaker reconstructed

**Property:** Property 3 from design.md
**Validates:** 66-REQ-2.2
**Type:** property
**Description:** CircuitBreaker always uses the latest config after reload.

**For any:** OrchestratorConfig with max_cost in [0.1, 10000]
**Invariant:** After reload, `self._circuit._config` matches the new config.

**Assertion pseudocode:**
```
FOR ANY max_cost IN floats(0.1, 10000):
    new = OrchestratorConfig(max_cost=max_cost)
    mock load_config with orchestrator=new
    orch._reload_config()
    ASSERT orch._circuit._config.max_cost == max_cost
```

### TS-66-P4: Parallel is immutable

**Property:** Property 4 from design.md
**Validates:** 66-REQ-3.1, 66-REQ-3.2
**Type:** property
**Description:** Parallel value never changes after reload.

**For any:** New parallel value in [1, 8] different from current
**Invariant:** `self._config.parallel` remains the original value.

**Assertion pseudocode:**
```
original_parallel = orch._config.parallel
FOR ANY new_parallel IN integers(1, 8):
    mock load_config with parallel=new_parallel
    orch._reload_config()
    ASSERT orch._config.parallel == original_parallel
```

### TS-66-P5: Parse errors preserve config

**Property:** Property 5 from design.md
**Validates:** 66-REQ-5.1, 66-REQ-5.E1, 66-REQ-1.E1
**Type:** property
**Description:** Any error during reload leaves state unchanged.

**For any:** Exception type in [ConfigError, OSError, FileNotFoundError]
**Invariant:** Config and CircuitBreaker are unchanged.

**Assertion pseudocode:**
```
FOR ANY exc_type IN error_types:
    old_config = deepcopy(orch._config)
    old_circuit = orch._circuit
    mock load_config to raise exc_type
    orch._reload_config()
    ASSERT orch._config == old_config
    ASSERT orch._circuit is old_circuit
```

### TS-66-P6: Audit event captures exact diff

**Property:** Property 6 from design.md
**Validates:** 66-REQ-6.1, 66-REQ-6.2
**Type:** property
**Description:** Audit event payload contains exactly the changed fields.

**For any:** Two different valid AgentFoxConfig instances
**Invariant:** Audit event `changed_fields` keys match the fields that differ.

**Assertion pseudocode:**
```
FOR ANY (old_cfg, new_cfg) IN config_pair_strategy:
    expected_diff = diff_configs(old_cfg, new_cfg)
    mock load_config to return new_cfg
    orch._reload_config()
    IF expected_diff:
        ASSERT audit event emitted
        ASSERT event.payload["changed_fields"] == expected_diff
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|---|---|---|
| 66-REQ-1.1 | TS-66-1 | unit |
| 66-REQ-1.2 | TS-66-2 | unit |
| 66-REQ-1.3 | TS-66-3 | unit |
| 66-REQ-1.E1 | TS-66-E1 | unit |
| 66-REQ-2.1 | TS-66-4 | unit |
| 66-REQ-2.2 | TS-66-5 | unit |
| 66-REQ-2.E1 | TS-66-E4 | unit |
| 66-REQ-3.1 | TS-66-6 | unit |
| 66-REQ-3.2 | TS-66-6 | unit |
| 66-REQ-4.1 | TS-66-7 | unit |
| 66-REQ-4.2 | TS-66-8 | unit |
| 66-REQ-4.3 | TS-66-9 | unit |
| 66-REQ-5.1 | TS-66-E2 | unit |
| 66-REQ-5.E1 | TS-66-E3 | unit |
| 66-REQ-6.1 | TS-66-10 | unit |
| 66-REQ-6.2 | TS-66-10 | unit |
| 66-REQ-6.E1 | TS-66-2 | unit |
| 66-REQ-7.1 | TS-66-11 | unit |
| 66-REQ-7.2 | TS-66-11 | unit |
| Property 1 | TS-66-P1 | property |
| Property 2 | TS-66-P2 | property |
| Property 3 | TS-66-P3 | property |
| Property 4 | TS-66-P4 | property |
| Property 5 | TS-66-P5 | property |
| Property 6 | TS-66-P6 | property |
