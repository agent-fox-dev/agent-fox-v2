# Test Specification: Core Foundation

## Overview

Tests for the project skeleton: CLI entry point, configuration system,
init command, error hierarchy, model registry, logging, and theme.
Tests map to requirements in `requirements.md` and correctness properties
in `design.md`.

## Test Cases

### TS-01-1: CLI displays version

**Requirement:** 01-REQ-1.1
**Type:** integration
**Description:** Verify `agent-fox --version` prints the package version.

**Preconditions:**
- Package is installed in the environment.

**Input:**
- CLI invocation: `["agent-fox", "--version"]`

**Expected:**
- Output contains the version string (e.g., "0.1.0").
- Exit code 0.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--version"])
ASSERT result.exit_code == 0
ASSERT "0.1.0" IN result.output OR version_pattern MATCHES result.output
```

---

### TS-01-2: CLI displays help

**Requirement:** 01-REQ-1.1
**Type:** integration
**Description:** Verify `agent-fox --help` lists available subcommands.

**Preconditions:**
- Package is installed; `init` command is registered.

**Input:**
- CLI invocation: `["agent-fox", "--help"]`

**Expected:**
- Output contains "init".
- Exit code 0.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--help"])
ASSERT result.exit_code == 0
ASSERT "init" IN result.output
```

---

### TS-01-3: Config loads defaults from empty TOML

**Requirement:** 01-REQ-2.1, 01-REQ-2.3
**Type:** unit
**Description:** Verify that an empty config file produces all defaults.

**Preconditions:**
- A temporary file containing only valid but empty TOML (`""`).

**Input:**
- `load_config(path=empty_toml_file)`

**Expected:**
- `config.orchestrator.parallel == 1`
- `config.orchestrator.sync_interval == 5`
- `config.orchestrator.max_retries == 2`
- `config.orchestrator.session_timeout == 30`
- `config.theme.playful == True`
- `config.models.coding == "ADVANCED"`

**Assertion pseudocode:**
```
config = load_config(path=empty_file)
ASSERT config.orchestrator.parallel == 1
ASSERT config.orchestrator.sync_interval == 5
ASSERT config.theme.playful == True
ASSERT config.models.coding == "ADVANCED"
```

---

### TS-01-4: Config loads overrides from TOML

**Requirement:** 01-REQ-2.1
**Type:** unit
**Description:** Verify that values in TOML override defaults.

**Preconditions:**
- A TOML file with `[orchestrator]\nparallel = 4`.

**Input:**
- `load_config(path=toml_file)`

**Expected:**
- `config.orchestrator.parallel == 4`
- All other fields remain at defaults.

**Assertion pseudocode:**
```
config = load_config(path=toml_with_parallel_4)
ASSERT config.orchestrator.parallel == 4
ASSERT config.orchestrator.sync_interval == 5  # unchanged
```

---

### TS-01-5: Config rejects invalid type

**Requirement:** 01-REQ-2.2
**Type:** unit
**Description:** Verify that a string where an int is expected raises ConfigError.

**Preconditions:**
- A TOML file with `[orchestrator]\nparallel = "not_a_number"`.

**Input:**
- `load_config(path=bad_type_toml)`

**Expected:**
- `ConfigError` raised.
- Error message mentions "parallel" and the invalid value.

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError FROM load_config(path=bad_type_file)
ASSERT "parallel" IN str(error)
```

---

### TS-01-6: Init creates project structure

**Requirement:** 01-REQ-3.1, 01-REQ-3.2
**Type:** integration
**Description:** Verify init creates `.agent-fox/` with config, hooks, worktrees,
and the develop branch.

**Preconditions:**
- A fresh temporary git repository with no `.agent-fox/` directory.

**Input:**
- Run `agent-fox init` in the temp repo.

**Expected:**
- `.agent-fox/config.toml` exists and is valid TOML.
- `.agent-fox/hooks/` directory exists.
- `.agent-fox/worktrees/` directory exists.
- Git branch `develop` exists.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["init"])
ASSERT result.exit_code == 0
ASSERT Path(".agent-fox/config.toml").exists()
ASSERT Path(".agent-fox/hooks").is_dir()
ASSERT Path(".agent-fox/worktrees").is_dir()
ASSERT "develop" IN git_branches()
```

---

### TS-01-7: Init is idempotent

**Requirement:** 01-REQ-3.3
**Type:** integration
**Description:** Verify running init twice doesn't overwrite existing config.

**Preconditions:**
- A temp git repo where init has already been run.
- Config has been modified (e.g., `parallel = 8` added).

**Input:**
- Run `agent-fox init` again.

**Expected:**
- Exit code 0.
- Config file content is unchanged (parallel still 8).
- Output indicates project is already initialized.

**Assertion pseudocode:**
```
# First init
cli_runner.invoke(main, ["init"])
# Modify config
write_to_config("[orchestrator]\nparallel = 8")
# Second init
result = cli_runner.invoke(main, ["init"])
ASSERT result.exit_code == 0
ASSERT "already initialized" IN result.output.lower()
config = load_config()
ASSERT config.orchestrator.parallel == 8  # not overwritten
```

---

### TS-01-8: Init updates gitignore

**Requirement:** 01-REQ-3.4
**Type:** integration
**Description:** Verify init adds `.agent-fox/*` rules to `.gitignore`.

**Preconditions:**
- A temp git repo with no `.gitignore` or with one lacking agent-fox entries.

**Input:**
- Run `agent-fox init`.

**Expected:**
- `.gitignore` contains `.agent-fox/*`.
- `.gitignore` contains `!.agent-fox/config.toml`.

**Assertion pseudocode:**
```
cli_runner.invoke(main, ["init"])
gitignore = Path(".gitignore").read_text()
ASSERT ".agent-fox/*" IN gitignore
ASSERT "!.agent-fox/config.toml" IN gitignore
```

---

### TS-01-9: Model resolution by tier

**Requirement:** 01-REQ-5.1, 01-REQ-5.3
**Type:** unit
**Description:** Verify resolve_model returns correct entries for tier names.

**Preconditions:** None.

**Input:**
- `resolve_model("SIMPLE")`, `resolve_model("STANDARD")`, `resolve_model("ADVANCED")`

**Expected:**
- Each returns a ModelEntry with the correct tier and a valid model_id.

**Assertion pseudocode:**
```
entry = resolve_model("SIMPLE")
ASSERT entry.tier == ModelTier.SIMPLE
ASSERT entry.model_id != ""
ASSERT entry.input_price_per_m > 0
```

---

### TS-01-10: Cost calculation

**Requirement:** 01-REQ-5.4
**Type:** unit
**Description:** Verify cost calculation returns correct USD value.

**Preconditions:** None.

**Input:**
- `calculate_cost(input_tokens=1_000_000, output_tokens=500_000, model=sonnet_entry)`
- Sonnet: $3.00/M input, $15.00/M output.

**Expected:**
- Cost = (1.0 * 3.00) + (0.5 * 15.00) = $10.50

**Assertion pseudocode:**
```
model = resolve_model("STANDARD")
cost = calculate_cost(1_000_000, 500_000, model)
ASSERT abs(cost - 10.50) < 0.01
```

---

### TS-01-11: Error hierarchy

**Requirement:** 01-REQ-4.1, 01-REQ-4.2
**Type:** unit
**Description:** Verify all error classes are subclasses of AgentFoxError.

**Preconditions:** None.

**Input:**
- List of error classes: ConfigError, SessionError, WorkspaceError, etc.

**Expected:**
- Each is a subclass of AgentFoxError.
- Each can be caught by `except AgentFoxError`.

**Assertion pseudocode:**
```
FOR EACH cls IN [ConfigError, InitError, PlanError, SessionError,
                 WorkspaceError, IntegrationError, HookError,
                 SessionTimeoutError, CostLimitError, SecurityError]:
    ASSERT issubclass(cls, AgentFoxError)
    ASSERT isinstance(cls("test"), AgentFoxError)
```

---

### TS-01-12: Theme playful mode toggle

**Requirement:** 01-REQ-7.3, 01-REQ-7.4
**Type:** unit
**Description:** Verify theme returns different messages based on playful flag.

**Preconditions:** None.

**Input:**
- `create_theme(ThemeConfig(playful=True)).playful("task_complete")`
- `create_theme(ThemeConfig(playful=False)).playful("task_complete")`

**Expected:**
- Playful mode returns a fox-themed message.
- Non-playful mode returns a neutral message.
- Both are non-empty strings.

**Assertion pseudocode:**
```
playful_theme = create_theme(ThemeConfig(playful=True))
neutral_theme = create_theme(ThemeConfig(playful=False))
playful_msg = playful_theme.playful("task_complete")
neutral_msg = neutral_theme.playful("task_complete")
ASSERT playful_msg != neutral_msg
ASSERT len(playful_msg) > 0
ASSERT len(neutral_msg) > 0
```

## Property Test Cases

### TS-01-P1: Config defaults completeness

**Property:** Property 1 from design.md
**Validates:** 01-REQ-2.1, 01-REQ-2.3
**Type:** property
**Description:** An empty TOML always produces a fully-populated config.

**For any:** empty or whitespace-only TOML string
**Invariant:** All fields in the returned AgentFoxConfig have their documented
default values.

**Assertion pseudocode:**
```
FOR ANY toml_str IN whitespace_strings():
    config = load_config_from_string(toml_str)
    ASSERT config.orchestrator.parallel == 1
    ASSERT config.orchestrator.max_retries == 2
    ASSERT config.theme.playful == True
    ASSERT config.models.coding == "ADVANCED"
```

---

### TS-01-P2: Config numeric clamping

**Property:** Property 8 from design.md
**Validates:** 01-REQ-2.E3
**Type:** property
**Description:** Out-of-range numerics are clamped, not rejected.

**For any:** integer value for `orchestrator.parallel` outside [1, 8]
**Invariant:** The loaded config's `parallel` is clamped to [1, 8].

**Assertion pseudocode:**
```
FOR ANY n IN integers():
    toml = f"[orchestrator]\nparallel = {n}"
    config = load_config_from_string(toml)
    ASSERT 1 <= config.orchestrator.parallel <= 8
```

---

### TS-01-P3: Cost non-negativity

**Property:** Property 6 from design.md
**Validates:** 01-REQ-5.4
**Type:** property
**Description:** Cost is never negative for non-negative inputs.

**For any:** non-negative integers `input_tokens`, `output_tokens` and any
valid ModelEntry
**Invariant:** `calculate_cost(input_tokens, output_tokens, model) >= 0`

**Assertion pseudocode:**
```
FOR ANY input_tokens IN non_negative_integers(),
        output_tokens IN non_negative_integers(),
        model IN all_model_entries():
    cost = calculate_cost(input_tokens, output_tokens, model)
    ASSERT cost >= 0.0
```

---

### TS-01-P4: Model registry completeness

**Property:** Property 5 from design.md
**Validates:** 01-REQ-5.1, 01-REQ-5.3
**Type:** property
**Description:** Every tier resolves to a valid model.

**For any:** tier in ModelTier enum
**Invariant:** `resolve_model(tier.value)` returns a ModelEntry with matching
tier and positive prices.

**Assertion pseudocode:**
```
FOR ANY tier IN ModelTier:
    entry = resolve_model(tier.value)
    ASSERT entry.tier == tier
    ASSERT entry.input_price_per_m > 0
    ASSERT entry.output_price_per_m > 0
```

---

### TS-01-P5: Error hierarchy catches

**Property:** Property 7 from design.md
**Validates:** 01-REQ-4.1, 01-REQ-4.2
**Type:** property
**Description:** Every custom exception is caught by `except AgentFoxError`.

**For any:** exception class in the error hierarchy
**Invariant:** `issubclass(cls, AgentFoxError)` is True.

**Assertion pseudocode:**
```
FOR ANY cls IN all_error_classes():
    ASSERT issubclass(cls, AgentFoxError)
```

## Edge Case Tests

### TS-01-E1: Unknown subcommand

**Requirement:** 01-REQ-1.E1
**Type:** integration
**Description:** Unknown subcommand prints error and exits with code 2.

**Preconditions:** None.

**Input:**
- CLI invocation: `["agent-fox", "nonexistent"]`

**Expected:**
- Exit code 2.
- Output contains "No such command" or similar.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["nonexistent"])
ASSERT result.exit_code == 2
```

---

### TS-01-E2: Config file missing

**Requirement:** 01-REQ-2.E1
**Type:** unit
**Description:** Missing config file returns all defaults without error.

**Preconditions:**
- `path` points to a non-existent file.

**Input:**
- `load_config(path=Path("/nonexistent/config.toml"))`

**Expected:**
- Returns a valid AgentFoxConfig with all defaults.
- No exception raised.

**Assertion pseudocode:**
```
config = load_config(path=Path("/tmp/nonexistent.toml"))
ASSERT config.orchestrator.parallel == 1
```

---

### TS-01-E3: Config file invalid TOML

**Requirement:** 01-REQ-2.E2
**Type:** unit
**Description:** Invalid TOML raises ConfigError.

**Preconditions:**
- A file containing `[broken toml }{`.

**Input:**
- `load_config(path=broken_toml_file)`

**Expected:**
- `ConfigError` raised.

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError FROM load_config(path=broken_file)
```

---

### TS-01-E4: Init outside git repo

**Requirement:** 01-REQ-3.E5
**Type:** integration
**Description:** Init fails gracefully outside a git repository.

**Preconditions:**
- Working directory is a plain directory, not a git repo.

**Input:**
- Run `agent-fox init`.

**Expected:**
- Exit code 1.
- Output mentions "git repository".

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["init"])
ASSERT result.exit_code == 1
ASSERT "git" IN result.output.lower()
```

---

### TS-01-E5: Unknown model ID

**Requirement:** 01-REQ-5.E1
**Type:** unit
**Description:** Unknown model ID raises ConfigError with valid options.

**Preconditions:** None.

**Input:**
- `resolve_model("nonexistent-model")`

**Expected:**
- `ConfigError` raised.
- Error message includes at least one valid model ID.

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError FROM resolve_model("nonexistent-model")
ASSERT "claude" IN str(error)  # lists valid options
```

---

### TS-01-E6: Invalid theme color fallback

**Requirement:** 01-REQ-7.E1
**Type:** unit
**Description:** Invalid Rich style falls back to default.

**Preconditions:** None.

**Input:**
- `create_theme(ThemeConfig(header="not_a_valid_style"))`

**Expected:**
- Theme is created without error.
- Header role uses the default style ("bold #ff8c00").

**Assertion pseudocode:**
```
theme = create_theme(ThemeConfig(header="not_a_valid_style"))
ASSERT theme is not None
# Theme should still function; invalid style is replaced with default
```

---

### TS-01-E7: Unrecognized config keys ignored

**Requirement:** 01-REQ-2.6
**Type:** unit
**Description:** Unknown keys in TOML are silently ignored.

**Preconditions:**
- A TOML file with `[unknown_section]\nfoo = "bar"`.

**Input:**
- `load_config(path=toml_with_unknown)`

**Expected:**
- Config loads successfully with defaults.
- No exception raised.

**Assertion pseudocode:**
```
config = load_config(path=file_with_unknown_keys)
ASSERT config.orchestrator.parallel == 1  # defaults applied
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 01-REQ-1.1 | TS-01-1, TS-01-2 | integration |
| 01-REQ-1.E1 | TS-01-E1 | integration |
| 01-REQ-2.1, 01-REQ-2.3 | TS-01-3 | unit |
| 01-REQ-2.1 | TS-01-4 | unit |
| 01-REQ-2.2 | TS-01-5 | unit |
| 01-REQ-2.5 | (covered by TS-01-P1 setup) | property |
| 01-REQ-2.6 | TS-01-E7 | unit |
| 01-REQ-2.E1 | TS-01-E2 | unit |
| 01-REQ-2.E2 | TS-01-E3 | unit |
| 01-REQ-2.E3 | TS-01-P2 | property |
| 01-REQ-3.1, 01-REQ-3.2 | TS-01-6 | integration |
| 01-REQ-3.3 | TS-01-7 | integration |
| 01-REQ-3.4 | TS-01-8 | integration |
| 01-REQ-3.E1, 01-REQ-3.E2 | TS-01-7 | integration |
| 01-REQ-3.5 | TS-01-E4 | integration |
| 01-REQ-4.1, 01-REQ-4.2 | TS-01-11 | unit |
| 01-REQ-4.E1 | (covered by CLI error handler test) | integration |
| 01-REQ-5.1, 01-REQ-5.3 | TS-01-9 | unit |
| 01-REQ-5.4 | TS-01-10 | unit |
| 01-REQ-5.E1 | TS-01-E5 | unit |
| 01-REQ-6.1, 01-REQ-6.2 | (verified by logging setup) | unit |
| 01-REQ-7.1, 01-REQ-7.3, 01-REQ-7.4 | TS-01-12 | unit |
| 01-REQ-7.E1 | TS-01-E6 | unit |
| Property 1 | TS-01-P1 | property |
| Property 5 | TS-01-P4 | property |
| Property 6 | TS-01-P3 | property |
| Property 7 | TS-01-P5 | property |
| Property 8 | TS-01-P2 | property |
