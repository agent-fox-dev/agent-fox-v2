# Agent Archetypes

## The Four Archetypes

v2 had seven archetypes (Coder, Skeptic, Oracle, Auditor, Verifier, Cartographer, Librarian). v3 collapses these to four, each with a clear separation of power.

### Coder

**What it does:** Implements code changes according to a task group description, guided by the PRD and optional design document. Writes code, runs tests, installs dependencies, modifies configuration.

**Permissions:** Read-write filesystem within the worktree. Shell execution. Network access (for package managers). Cannot modify spec files.

**Harness:** Typically `claude-code` (full tool access) or any harness that supports file editing and shell.

**Model tier:** Adaptive routing by default. Simple tier for straightforward tasks; standard for typical work; advanced for complex or cross-cutting changes. The routing system starts with heuristics and graduates to a trained classifier as historical data accumulates.

**Expected output:** Commits on the feature branch, a session summary (what was attempted, what succeeded, what was left incomplete), and a list of files created or modified. If the harness supports `structured_output`, the summary is extracted as JSON; otherwise, it is parsed from the final assistant message.

### Reviewer

**What it does:** Replaces the Skeptic, Oracle, and Auditor from v2 as a single configurable review archetype. A Reviewer session receives a *review mode* that determines its focus:

- **Pre-review** (Skeptic mode): Examines the spec before any coding. Checks for ambiguity, contradictions, missing edge cases, unrealistic scope. Produces findings that the Coder receives as context.
- **Drift-review** (Oracle mode): Compares the spec's design document against the existing codebase. Identifies where the current code diverges from the specified architecture — verifying function signatures, checking import structures, and confirming that specified modules exist. Skipped when the spec references no existing files.
- **Audit-review** (Auditor mode): Validates that tests written by the Coder cover the test spec contracts. Requires `test_spec.md` to be present.

The Reviewer cannot modify files. Its permission model is mode-specific:

- **Pre-review:** Read-only file access, no shell. Pre-review is a reading task — examining spec prose for logical issues. Shell access would not meaningfully improve it.
- **Drift-review and audit-review:** Read-only file access plus read-only shell execution in an ephemeral sandbox. This allows the Reviewer to run analysis commands — grep for function signatures, parse import graphs, run `pytest --collect-only` to enumerate test cases, check coverage reports — that provide empirical grounding for its findings. All shell writes go to an ephemeral overlay and are discarded. The codebase is never modified.

The safety property is preserved across all modes: a compromised or hallucinating Reviewer cannot damage the codebase. The difference from the Verifier is scope of intent, not security boundary — both run in ephemeral sandboxes with discarded writes.

**Harness:** `ClaudeCodeHarness` with a mode-specific permission callback. Pre-review: read-only file tools (no writes, no shell). Drift-review and audit-review: read-only file tools plus shell execution (ephemeral writes discarded). The Reviewer can read source files and spec artifacts directly. The `structured_output` capability ensures findings are parsed as typed JSON.

Audit-review validates test coverage by analyzing test files against test_spec.md contracts — parsing test file structure, checking function names against contract IDs, and running `pytest --collect-only` to enumerate test cases without executing them. It does not execute the test suite — that is the Verifier's responsibility.

**Multi-instance convergence:** Multiple Reviewer instances can run on the same input. Their findings are merged per mode:

| Review Mode | Convergence Strategy | Rationale |
|------------|---------------------|-----------|
| Pre-review | Worst-verdict-wins | Conservative — a single reviewer spotting ambiguity is enough to flag it |
| Drift-review | Worst-verdict-wins | Same rationale — any detected drift is worth investigating |
| Audit-review | Majority-voting | Coverage assessment benefits from consensus — one reviewer may miss a valid test mapping |

**Worst-verdict-wins** works as follows: all findings from all instances are unioned into a single list. If multiple instances report findings about the same aspect (matched by category and affected artifact), the finding with the highest severity is kept (`critical` > `major` > `minor` > `info`). Findings about different aspects are all retained — the union ensures nothing is lost. Each finding is annotated with its **agreement ratio** — the fraction of instances that reported it (e.g., 1/3 if only one of three instances flagged it). The agreement ratio is metadata, not a filter — low-agreement findings are still surfaced, but the Coder's context includes the ratio so it can calibrate its response. A finding reported by 3/3 instances warrants more attention than one reported by 1/3.

**Majority-voting** for audit-review: each instance produces a pass/fail verdict per test-spec contract. A contract is considered "covered" if a majority of instances (>50%) judge it covered. This smooths over individual reviewer hallucinations.

The instance count is configurable per review mode (default: 1 for all modes, via `archetype.reviewer.instance_count`). When instance count is 1, convergence is a no-op — the single instance's findings are used directly.

**Correlated error risk:** Multi-instance convergence provides diminishing returns when all instances use the same model, temperature, and system prompt. Errors from a shared model tend to be correlated — all instances are likely to miss the same subtle issue or hallucinate the same false positive. The agreement ratio mitigates the false-positive problem for worst-verdict-wins (a finding reported by 1/N instances is flagged as low-agreement). For majority-voting, correlated errors are harder to detect. Potential mitigations — temperature variation, prompt variation, or model diversity — are future extensions, not v3 requirements. In practice, the primary value of multi-instance convergence is catching high-variance errors (where the model is uncertain and different samples diverge), not systematic blind spots.

**Verifier multi-instance:** The Verifier does not support multi-instance convergence. Verification is empirical (run tests, observe results), not subjective — running the same test suite twice produces the same verdicts. A single Verifier instance is always sufficient.

**Model tier:** Defaults to standard. v2 used advanced for all review agents; v3 defaults to standard because standard-tier models have improved sufficiently for careful reading tasks since v2. Per-mode overrides are available in archetype configuration.

### Verifier

**What it does:** Runs the test suite after coding and confirms that each requirement (if `requirements.md` exists) or success criterion (from `prd.md`) is met by the implementation. The Verifier evaluates **all requirements** in `requirements.md` for the spec, not just those relevant to the current task group — this catches regressions where fixing one thing breaks another. It produces a pass/fail verdict per requirement and an overall assessment. Verdict mapping: the Verifier parses test results and maps them to requirements by matching test names and descriptions against requirement IDs and keywords. If a requirement cannot be mapped to any test, it receives a verdict of `untested` (distinct from `fail`).

**Permissions:** Read-only filesystem. Shell execution (to run tests). No write access. No network access beyond localhost.

**Why it stays separate from Reviewer:** Verification is fundamentally different from review. Review is analytical (read and critique). Verification is empirical (run tests and observe). They need different tool permissions, different prompts, and different convergence strategies.

**Model tier:** Standard. Verification is structured and well-defined.

### Maintainer

**What it does:** Replaces the Cartographer and Librarian from v2. The Maintainer is the archetype for analysis and knowledge — finding problems and extracting learning. It does not implement fixes; that is the Coder's job.

Two modes:
- **Hunt mode** (night-shift): Scans the codebase using static analysis tools, interprets findings via LLM, consolidates with the critic, deduplicates against known issues. Produces structured work items.
- **Knowledge extraction** (spec pipeline): After a Coder session completes, a Maintainer session extracts facts (causal relationships, architectural decisions, failure patterns) from the session transcript and stores them in the knowledge system.

The night-shift fix pipeline uses the Coder archetype, not the Maintainer (see ch 04, Fix Pipeline). v2 conflated "finding problems" with "fixing problems" under a single role. v3 separates them: the Maintainer finds and analyzes, the Coder implements. This keeps the Maintainer's two modes coherent — both are read-only analysis producing structured output.

**Permissions:** Hunt mode has read-only filesystem access with shell execution (to run linters, static analysis tools, and test collection commands). Knowledge extraction is read-only with respect to the worktree — it reads transcripts via the orchestrator and writes facts to the knowledge store via the orchestrator's API, not via filesystem writes inside the sandbox.

### Archetype Permissions Summary

| Archetype | Filesystem | Shell | Network | Tool Restrictions |
|-----------|-----------|-------|---------|-------------------|
| Coder | Read-write (worktree) | Yes | Gated (proxy-only) | Cannot modify spec files |
| Reviewer (pre-review) | Read-only | No | Gated (API-only) | Read-only file tools only |
| Reviewer (drift/audit) | Read-only (ephemeral writes discarded) | Yes (analysis commands) | Gated (API-only) | Read-only file tools + shell |
| Verifier | Read-only (ephemeral writes discarded) | Yes (test execution) | Localhost only | No file-write tools |
| Maintainer (hunt) | Read-only | Yes (analysis tools) | Blocked | Read-only + shell |
| Maintainer (extraction) | N/A (reads via orchestrator) | No | None | Knowledge store write only |

### Archetype Profiles

The four archetypes define *what* an agent can do (permissions, tools, sandbox). **Archetype profiles** define *how* it behaves — the system prompt template that shapes the agent's approach, focus areas, and output format. Profiles make prompt construction transparent, inspectable, and customizable.

#### Why profiles exist

Without profiles, archetype behavior is invisible. The engine constructs system prompts programmatically. When an agent misbehaves, the first diagnostic question — "what was it told?" — requires reading Python source. There is no place for a team to say "our Reviewers should always check accessibility" or "our Coders must run `make lint` before committing." `CLAUDE.md` is project-wide and role-agnostic; it cannot differentiate between archetypes.

This is the practical takeaway from OpenClaw's SOUL.md concept: an agent's behavior should be defined in a readable, editable file — not buried in code. SOUL.md defines a complete agent identity (personality, rules, working state) in a single document. agent-fox adapts the idea for a multi-archetype system: each archetype gets its own profile, and the engine merges it with project context and task context to build the full prompt.

#### Prompt layering

The system prompt for each session is assembled from three layers:

| Layer | Source | Scope | Who writes it |
|-------|--------|-------|---------------|
| Project context | `CLAUDE.md` | All agents, all sessions | Human (project-wide) |
| Archetype profile | `.agent-fox/profiles/<archetype>.md` | All sessions of this archetype | Human or package default (role-specific) |
| Task context | Spec artifacts + knowledge injection + findings | One session | Engine (assembled per-task) |

The engine prepends the project context, injects the archetype profile, then appends the task-specific context. The three layers are concatenated, not merged — each is a distinct block in the prompt, clearly delineated.

#### Profile structure

Profiles live in `.agent-fox/profiles/`:

```
.agent-fox/profiles/
  coder.md
  reviewer.md
  verifier.md
  maintainer.md
```

Each profile contains four sections:

- **Identity** — What this archetype is and does. One paragraph. Defines the agent's role in the pipeline. Package defaults ship with this section filled in; project overrides rarely need to change it.
- **Rules** — Hard behavioral constraints. "Never modify spec files." "Commit each logical change separately." "Do not refactor code outside the task scope." Package defaults define the invariants. Project overrides append additional rules.
- **Focus areas** — What to pay attention to. This is where customization matters most. A Reviewer at a fintech company focuses on transaction integrity and audit trails. A Reviewer at a game studio focuses on frame budget and memory allocations. Package defaults are intentionally generic; teams add domain-specific focus here.
- **Output format** — Expected structure of the session's output (files changed, test results, findings). Package defaults define the schema. Projects can extend it with additional fields.

#### Override semantics

The engine ships with **default profiles** embedded in the `agent_fox.harness` package. These are the baseline — they work without any project configuration. If a file exists at `.agent-fox/profiles/<archetype>.md`, the engine uses the project file instead of the package default.

The override is **full replacement**, not merge. If a team creates a `coder.md` profile, they are responsible for the complete profile — including the Identity and Rules sections. This avoids the complexity of section-level merging and makes the effective prompt fully visible in one file. To start from the defaults, `af init --profiles` copies the package defaults into the project directory for editing.

**Hard constraints are not overridable via profiles.** A profile cannot grant a Reviewer write access or give a Verifier network access. Permissions are enforced by the permission callback and sandbox profile (ch 02), not by the prompt. A malicious or poorly written profile can make an agent behave suboptimally, but it cannot make an agent violate its security boundary.

#### Archetype extensibility

The four archetypes are the shipped set. But the profile mechanism supports team-defined archetypes beyond the four. A team can:

1. Create a profile at `.agent-fox/profiles/deployer.md`.
2. Define a permission preset in project config (`archetype.deployer.permissions = "coder"` — reuse an existing permission profile).
3. Use it in task group tags: `[archetype: deployer]`.

The engine loads the profile, maps the permission preset to a sandbox profile and permission callback, and runs the session. The custom archetype's prompt comes from the profile; its security boundary comes from the permission preset.

This is an escape hatch, not a primary workflow. The four built-in archetypes cover the spec-driven execution loop. Two common gaps and how the escape hatch addresses them:

- **Deployment.** The pipeline produces merged code, not deployments. Teams that need deploy-and-verify-in-staging can define a `deployer` custom archetype with Coder permissions and a profile focused on deployment scripts and health checks.
- **Research/exploration.** Tasks that require investigating multiple approaches before committing ("evaluate library X vs Y") don't fit the Coder model. A `researcher` custom archetype with Reviewer permissions (read-only + shell) can explore, benchmark, and produce structured recommendations that subsequent Coder groups act on. Alternatively, a task group tagged `[archetype: reviewer]` with a research-focused description achieves the same thing within the built-in set.

