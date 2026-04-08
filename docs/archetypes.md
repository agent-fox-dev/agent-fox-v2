# Agent Archetypes

agent-fox uses specialized agent archetypes to assign distinct roles at
different stages of the development pipeline. Each archetype has a focused
purpose, a dedicated prompt template, and its own model tier and injection
mode.

## Overview

| Archetype | Purpose | Injection | Default |
|-----------|---------|-----------|---------|
| **Coder** | Implement features, fix bugs, write tests | default | always enabled |
| **Skeptic** | Review specs for issues before coding | auto, before first coder group | enabled |
| **Oracle** | Validate spec assumptions against codebase | auto, before first coder group | disabled |
| **Auditor** | Validate test code against test_spec contracts | auto, mid-execution | disabled |
| **Verifier** | Check code quality after coding | auto, after last coder group | enabled |
| **Librarian** | Documentation tasks | manual assignment | disabled |
| **Cartographer** | Architecture mapping | manual assignment | disabled |

When both Skeptic and Oracle are enabled, they run in parallel before the
first coder group. If either produces blocking findings, coder sessions are
not started.

---

## Coder

**Purpose:** Implement code for one task group per session — features, bug
fixes, tests, refactoring.

- **Model tier:** STANDARD (default)
- **Injection:** Default — every task runs as a coder unless assigned another
  archetype
- **Always enabled:** The `coder` toggle cannot be disabled

The coder receives specification documents, memory facts, and any findings
from prior skeptic/oracle/verifier reviews. It follows a test-first workflow:
group 1 writes failing tests from `test_spec.md`, subsequent groups implement
code.

**Outputs:** Implemented code, tests, conventional commits, session summary.

---

## Skeptic

**Purpose:** Critically review specifications for completeness, consistency,
and feasibility **before** implementation begins.

- **Model tier:** ADVANCED (default)
- **Injection:** `auto_pre` — runs automatically before the first coder group
- **Default:** Enabled
- **Instances:** Configurable (1–5, default 1)
- **Allowlist:** `ls`, `cat`, `git`, `wc`, `head`, `tail`

The skeptic reads all specification documents and produces structured JSON
findings categorized by severity (critical, major, minor, observation). It
checks for:

- Completeness gaps (missing requirements, untested paths)
- Internal consistency (contradictions between artifacts)
- Feasibility issues (unrealistic constraints, missing dependencies)
- Testability (vague or unverifiable acceptance criteria)
- Edge case coverage
- Security concerns

**Blocking:** If the number of majority-agreed critical findings exceeds
`block_threshold` (default 3), coder sessions are blocked until the specs
are revised.

**Multi-instance convergence:** When `archetypes.instances.skeptic > 1`,
multiple independent reviewers run in parallel. Their findings are converged
using majority agreement — a finding must appear in a majority of reviews to
count.

### Configuration

```toml
[archetypes]
skeptic = true

[archetypes.instances]
skeptic = 3           # run 3 independent reviewers

[archetypes.skeptic_settings]
block_threshold = 3   # block if > 3 majority-agreed critical findings
```

---

## Oracle

**Purpose:** Validate specification assumptions against the current codebase
state — detect drift between what specs expect and what actually exists.

- **Model tier:** ADVANCED (default)
- **Injection:** `auto_pre` — runs before the first coder group
- **Default:** Disabled
- **Allowlist:** `ls`, `cat`, `git`, `grep`, `find`, `head`, `tail`, `wc`

The oracle reads specs and then explores the actual codebase to verify
assumptions. It checks, in priority order:

1. File and module existence
2. Class and function existence
3. Function signatures and parameter types
4. API contracts and interfaces
5. Behavioral assumptions

**Blocking:** When `block_threshold` is set, blocks coder sessions if
critical drift findings exceed the threshold. When omitted, the oracle is
advisory only — findings are logged but do not block.

### Configuration

```toml
[archetypes]
oracle = true

[archetypes.oracle_settings]
block_threshold = 5   # block if > 5 critical drift findings (omit for advisory)

[archetypes.models]
oracle = "STANDARD"   # override to Sonnet (default: ADVANCED)

[archetypes.allowlists]
oracle = ["ls", "cat", "git", "grep", "find", "head", "tail", "wc"]
```

See the [Oracle ADR](adr/oracle-archetype.md) for design rationale.

---

## Auditor

**Purpose:** Validate test code written by coders against `test_spec.md`
contracts — a test quality gate that ensures tests match their specifications.

- **Model tier:** STANDARD (default)
- **Injection:** `auto_mid` — runs during task group execution, after the
  coder writes tests
- **Default:** Disabled
- **Instances:** Configurable (1–5, default 1)
- **Allowlist:** `ls`, `cat`, `git`, `grep`, `find`, `head`, `tail`, `wc`, `uv`

The auditor compares each test function against its corresponding
`test_spec.md` entry and produces a structured JSON audit with per-entry
verdicts:

| Verdict | Meaning |
|---------|---------|
| **PASS** | Test fully covers the spec entry |
| **WEAK** | Test exists but assertions are insufficient |
| **MISSING** | No test found for the spec entry |
| **MISALIGNED** | Test exists but tests something different |

**Audit dimensions:**
- Coverage (test function exists, happy path covered)
- Assertion strength (meaningful assertions, specific values)
- Precondition fidelity (setup matches spec entry exactly)
- Edge case rigor (boundaries, error paths tested)
- Independence (tests run in isolation)

**Fail criteria:** The auditor fails (triggering a coder retry) if:
- Any `MISSING` verdict
- Any `MISALIGNED` verdict
- Two or more `WEAK` verdicts

The auditor-coder retry loop runs up to `max_retries` times (default 2).

### Configuration

```toml
[archetypes]
auditor = true

[archetypes.auditor_config]
min_ts_entries = 5    # minimum test_spec entries to trigger injection
max_retries = 2       # maximum auditor-coder retry iterations

[archetypes.instances]
auditor = 1
```

---

## Verifier

**Purpose:** Verify that the coder's implementation matches specification
requirements and quality standards — a post-coding quality gate.

- **Model tier:** ADVANCED (default)
- **Injection:** `auto_post` — runs after the last coder group
- **Default:** Enabled
- **Instances:** Configurable (1–5, default 1)

The verifier receives the specification documents, any prior skeptic/oracle
findings, and the coder's implementation. It checks:

- Requirements coverage (all acceptance criteria met)
- Test execution (tests pass, no regressions)
- Code quality (style, naming, patterns)
- Spec conformance (implementation matches design)

**Verdict:** PASS or FAIL. If the verifier fails, the coder is retried with
the verifier's feedback.

### Configuration

```toml
[archetypes]
verifier = true

[archetypes.instances]
verifier = 1
```

---

## Librarian

**Purpose:** Create and maintain project documentation.

- **Model tier:** STANDARD (default)
- **Injection:** `manual` — must be explicitly assigned to a task group
- **Default:** Disabled

The librarian focuses on documentation quality: README updates, API docs,
ADRs, setup guides, and inline docstrings. Assign it to specific task
groups in `tasks.md`:

```markdown
- [ ] 5. Update documentation [archetype: librarian]
```

---

## Cartographer

**Purpose:** Map and document codebase architecture.

- **Model tier:** STANDARD (default)
- **Injection:** `manual` — must be explicitly assigned to a task group
- **Default:** Disabled

The cartographer produces architecture documentation, module diagrams, and
component interaction maps. Assign it to specific task groups in `tasks.md`:

```markdown
- [ ] 6. Map architecture [archetype: cartographer]
```

---

## Model Selection and Escalation

### Default Model Tiers

Each archetype has a default model tier that determines which Claude model
runs the session:

| Archetype | Default Tier | Model |
|-----------|-------------|-------|
| **Skeptic** | ADVANCED | Claude Opus |
| **Oracle** | ADVANCED | Claude Opus |
| **Verifier** | ADVANCED | Claude Opus |
| **Coder** | STANDARD | Claude Sonnet |
| **Auditor** | STANDARD | Claude Sonnet |
| **Librarian** | STANDARD | Claude Sonnet |
| **Cartographer** | STANDARD | Claude Sonnet |
| **Coordinator** | STANDARD | Claude Sonnet |

Review-oriented archetypes (Skeptic, Oracle, Verifier) default to ADVANCED
(Opus) for thorough analysis. Execution-oriented archetypes (Coder and others)
default to STANDARD (Sonnet) for cost-effective implementation.

### Overriding Model Tiers via config.toml

#### Unified per-archetype table (recommended)

Use `[archetypes.overrides.<name>]` to configure all per-archetype settings
in one place:

```toml
[archetypes.overrides.coder]
model_tier = "ADVANCED"   # promote coder to Opus for complex specs
max_turns = 200
thinking_mode = "adaptive"

[archetypes.overrides.skeptic]
model_tier = "STANDARD"   # downgrade skeptic to Sonnet (cost reduction)
max_turns = 50

[archetypes.overrides.verifier]
model_tier = "ADVANCED"
max_turns = 75
allowlist = ["ls", "cat", "git", "make", "uv"]
```

Each `[archetypes.overrides.<name>]` block supports:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_tier` | `"SIMPLE"` \| `"STANDARD"` \| `"ADVANCED"` | None (registry) | Model tier override |
| `max_turns` | int ≥ 0 | None (registry) | Turn limit; 0 = unlimited |
| `thinking_mode` | `"enabled"` \| `"adaptive"` \| `"disabled"` | None (registry) | Extended thinking mode |
| `thinking_budget` | int ≥ 0 | None (10000) | Thinking budget tokens |
| `allowlist` | list of strings | None (registry) | Bash command allowlist |

`None` values fall through to the registry default. Any field not specified
inherits from the archetype registry.

#### Legacy dict syntax (backwards compatible)

The older dict-based overrides remain supported:

```toml
[archetypes.models]
coder = "ADVANCED"      # promote coder to Opus for complex specs
skeptic = "STANDARD"    # downgrade skeptic to Sonnet to reduce cost
verifier = "SIMPLE"     # downgrade verifier to Haiku
```

Valid tier values are `"SIMPLE"` (Haiku), `"STANDARD"` (Sonnet), and
`"ADVANCED"` (Opus). An invalid value raises a `ConfigError` at startup.

**Resolution priority:** `[archetypes.overrides.<name>]` takes precedence
over the legacy dict fields (`models`, `max_turns`, `thinking`, `allowlists`),
which in turn take precedence over the archetype registry defaults.

If an adaptive routing assessment is available, the assessed tier takes
precedence over all config values.

### Escalation Behavior

When a session fails, the orchestrator retries it using an escalation ladder:

1. **Retry at current tier**: The session is retried up to
   `retries_before_escalation` times at the current model tier.
2. **Escalate to ADVANCED**: After retries are exhausted at the current tier,
   the session is promoted to ADVANCED (Opus) for one final attempt.
3. **Block**: If the session fails at ADVANCED, the task is blocked.

The escalation ceiling is always ADVANCED regardless of the archetype's
default tier. This means any archetype — even those that start at STANDARD or
SIMPLE — can escalate to Opus when retries are exhausted.

---

## Configuration Summary

All archetype configuration lives under `[archetypes]` in `config.toml`.
See the [configuration reference](configuration.md#archetypes) for the
complete field listing.

```toml
# Enable/disable archetypes
[archetypes]
skeptic = true        # enabled by default
verifier = true       # enabled by default
oracle = false        # disabled by default
auditor = false       # disabled by default
librarian = false     # disabled by default
cartographer = false  # disabled by default

# Instance counts (for multi-instance convergence)
[archetypes.instances]
skeptic = 1
verifier = 1
auditor = 1

# Unified per-archetype overrides (recommended — all knobs in one place)
[archetypes.overrides.coder]
model_tier = "ADVANCED"    # promote coder to Opus (default: STANDARD)
max_turns = 200
thinking_mode = "adaptive"

[archetypes.overrides.skeptic]
model_tier = "STANDARD"    # downgrade skeptic to Sonnet (default: ADVANCED)
max_turns = 50

[archetypes.overrides.verifier]
model_tier = "ADVANCED"
max_turns = 75

# Legacy dict overrides (still supported for backwards compat)
# [archetypes.models]
# coder = "ADVANCED"
# skeptic = "STANDARD"
```

See the [archetypes ADR](adr/agent-archetypes.md) for the overall design
rationale.
