# Requirements Document

## Introduction

This document specifies the requirements for the Agent Archetypes system in
agent-fox. The system introduces two capabilities:

1. **SDK abstraction layer** (Phase A) — an `AgentBackend` protocol that
   decouples session execution from the Claude Agent SDK, enabling alternative
   agent runtimes and improving testability.

2. **Agent archetypes** (Phase B) — specialized agent configurations (system
   prompt, model tier, security allowlist) that the orchestrator assigns to
   task graph nodes, enabling purpose-built agents for review, verification,
   documentation, and architecture mapping tasks.

## Glossary

| Term | Definition |
|------|-----------|
| **Archetype** | A named configuration bundle (prompt templates, model tier, allowlist override, injection mode) that determines how a task graph node's session is executed. |
| **AgentBackend** | A `typing.Protocol` defining the contract any agent SDK adapter must implement to execute sessions. |
| **ClaudeBackend** | The concrete `AgentBackend` adapter that wraps the Claude Agent SDK (`claude-code-sdk`). |
| **Canonical message** | One of three frozen dataclasses (`ToolUseMessage`, `AssistantMessage`, `ResultMessage`) that all backends must map their native messages into. |
| **Injection mode** | How an archetype enters the task graph: `auto_pre` (before first Coder group), `auto_post` (after last Coder group), or `manual` (explicit assignment only). |
| **Convergence** | The deterministic post-processing step that merges outputs from multiple instances of the same archetype into a single result. |
| **Instance** | A single independent session of an archetype. A node with `instances: 3` runs three independent sessions in parallel. |
| **Roster** | The set of archetypes assignable to task graph nodes: Coder, Skeptic, Verifier, Librarian, Cartographer. |
| **Registry** | A data structure mapping archetype names to their configuration (templates, model tier, allowlist, injection mode, flags). |
| **Retry-predecessor** | Orchestrator behavior where a downstream node's failure triggers re-execution of its predecessor node, not itself. |
| **Blocking threshold** | A configurable count of critical findings above which the Skeptic marks itself as blocked. |
| **Model tier** | One of SIMPLE, STANDARD, or ADVANCED — mapped to specific Claude model IDs via the model registry. |

## Requirements

### Requirement 1: AgentBackend Protocol

**User Story:** As a developer, I want session execution decoupled from the
Claude SDK, so that I can swap agent runtimes and write tests without mocking
SDK internals.

#### Acceptance Criteria

1. **26-REQ-1.1** — THE system SHALL define an `AgentBackend` runtime-checkable
   `typing.Protocol` with three members: a `name` property returning `str`, an
   async `execute()` method yielding `AsyncIterator[AgentMessage]`, and an async
   `close()` method.

2. **26-REQ-1.2** — THE `execute()` method SHALL accept parameters: `prompt`
   (str), `system_prompt` (str), `model` (str), `cwd` (str), and an optional
   `permission_callback`.

3. **26-REQ-1.3** — THE system SHALL define three frozen dataclass message types
   (`ToolUseMessage`, `AssistantMessage`, `ResultMessage`) that constitute the
   canonical message model.

4. **26-REQ-1.4** — THE `ResultMessage` dataclass SHALL carry fields: `status`
   (str), `input_tokens` (int), `output_tokens` (int), `duration_ms` (int),
   `error_message` (str | None), and `is_error` (bool).

#### Edge Cases

1. **26-REQ-1.E1** — IF a backend's `execute()` raises an exception, THEN THE
   session runner SHALL catch the exception and return a failed `SessionOutcome`
   with the exception message as `error_message`.

---

### Requirement 2: ClaudeBackend Adapter

**User Story:** As a developer, I want all Claude SDK code isolated in a single
adapter module, so that SDK changes only affect one file.

#### Acceptance Criteria

1. **26-REQ-2.1** — THE system SHALL provide a `ClaudeBackend` class in
   `agent_fox/session/backends/claude.py` that implements the `AgentBackend`
   protocol.

2. **26-REQ-2.2** — THE `ClaudeBackend` SHALL map `ClaudeCodeOptions`,
   `ClaudeSDKClient`, and SDK message types (`ResultMessage`,
   `PermissionResultAllow`, `PermissionResultDeny`, `ToolPermissionContext`)
   to the canonical message model.

3. **26-REQ-2.3** — WHEN `ClaudeBackend.execute()` is called, THE adapter SHALL
   construct `ClaudeCodeOptions`, send the prompt via `ClaudeSDKClient`, and
   yield canonical messages from the response stream.

4. **26-REQ-2.4** — THE session runner (`run_session`) SHALL import only from
   the `AgentBackend` protocol and canonical message types — no direct imports
   from `claude_code_sdk`.

#### Edge Cases

1. **26-REQ-2.E1** — IF the `ClaudeSDKClient` raises during streaming, THEN THE
   `ClaudeBackend` SHALL yield a `ResultMessage` with `is_error=True` and the
   exception message.

---

### Requirement 3: Archetype Registry

**User Story:** As a developer, I want archetypes defined as data in a registry,
so that adding a new archetype with standard execution semantics requires only a
template file and a registry entry.

#### Acceptance Criteria

1. **26-REQ-3.1** — THE system SHALL maintain an archetype registry mapping
   archetype names to their configuration: template file names (list of str),
   default model tier (str), injection mode (`auto_pre` | `auto_post` |
   `manual` | None), and optional flags (`retry_predecessor`: bool).

2. **26-REQ-3.2** — THE registry SHALL include entries for: `coder`, `skeptic`,
   `verifier`, `librarian`, `cartographer`, and `coordinator`.

3. **26-REQ-3.3** — THE `coordinator` entry SHALL NOT be assignable to task
   graph nodes. WHEN a plan node references archetype `"coordinator"`, THE
   orchestrator SHALL log a warning and fall back to `"coder"`.

4. **26-REQ-3.4** — WHEN an archetype declares an allowlist override in the
   registry or config, THE session runner SHALL use that override instead of the
   global `security.bash_allowlist`.

5. **26-REQ-3.5** — THE `build_system_prompt()` function SHALL resolve template
   files from the archetype registry by name, replacing the hardcoded
   `_ROLE_TEMPLATES` dict.

#### Edge Cases

1. **26-REQ-3.E1** — IF a plan node references an archetype name not present in
   the registry, THEN THE system SHALL log a warning and fall back to `"coder"`.

2. **26-REQ-3.E2** — IF an archetype's template file does not exist on disk,
   THEN THE system SHALL raise a `ConfigError` identifying the missing template.

---

### Requirement 4: Node Archetype Metadata

**User Story:** As a planner, I want task graph nodes to carry archetype
metadata, so that the orchestrator can dispatch sessions with the correct
configuration.

#### Acceptance Criteria

1. **26-REQ-4.1** — THE `Node` dataclass SHALL include an `archetype` field
   (str, default: `"coder"`) and an `instances` field (int, default: 1).

2. **26-REQ-4.2** — WHEN the plan is serialized to `plan.json`, THE `archetype`
   and `instances` fields SHALL be included in the node data.

3. **26-REQ-4.3** — WHEN a `plan.json` file without `archetype` or `instances`
   fields is loaded, THE system SHALL default to `archetype="coder"` and
   `instances=1`.

4. **26-REQ-4.4** — THE `NodeSessionRunner` SHALL read the `archetype` field
   from node metadata and resolve the corresponding prompt templates, model
   tier, and allowlist from the registry.

#### Edge Cases

1. **26-REQ-4.E1** — IF `instances` is set to a value > 1 for the `coder`
   archetype, THEN THE system SHALL clamp to 1 and log a warning.

2. **26-REQ-4.E2** — IF `instances` exceeds 5 for any archetype, THEN THE
   system SHALL clamp to 5 and log a warning.

---

### Requirement 5: Archetype Assignment

**User Story:** As a spec author, I want to control which archetype runs for
each task group, with sensible defaults and LLM-assisted overrides.

#### Acceptance Criteria

1. **26-REQ-5.1** — THE task parser SHALL extract `[archetype: X]` tags from
   task group title lines in `tasks.md` and set the archetype on the
   `TaskGroupDef`.

2. **26-REQ-5.2** — THE graph builder SHALL apply archetype assignment using
   three layers in priority order: (1) explicit `tasks.md` tag (highest),
   (2) coordinator annotation, (3) graph builder default (lowest).

3. **26-REQ-5.3** — WHEN `archetypes.skeptic = true` in config, THE graph
   builder SHALL insert a group-0 node with `archetype="skeptic"` before the
   first task group of each spec, with appropriate intra-spec edges.

4. **26-REQ-5.4** — WHEN an `auto_post` archetype is enabled in config, THE
   graph builder SHALL insert a node with that archetype after the last Coder
   group of each spec, as an independent sibling (no edge between post-coder
   siblings).

5. **26-REQ-5.5** — THE graph builder SHALL log the final archetype assignment
   for each node at INFO level.

#### Edge Cases

1. **26-REQ-5.E1** — IF a coordinator annotation references a disabled
   archetype, THEN THE graph builder SHALL ignore the override and log a
   warning.

2. **26-REQ-5.E2** — IF an `[archetype: X]` tag in `tasks.md` references an
   unknown archetype, THEN THE task parser SHALL log a warning and leave the
   archetype unset (defaulting to `"coder"` at the graph builder level).

---

### Requirement 6: Archetype Configuration

**User Story:** As a user, I want to enable/disable archetypes and configure
instance counts, model tiers, and allowlists per archetype via `config.toml`.

#### Acceptance Criteria

1. **26-REQ-6.1** — THE `AgentFoxConfig` SHALL include an `archetypes` section
   with boolean enable/disable toggles for each roster archetype and the
   coordinator.

2. **26-REQ-6.2** — THE `archetypes.instances` sub-section SHALL allow setting
   the instance count per archetype (default: 1).

3. **26-REQ-6.3** — THE `archetypes.models` sub-section SHALL allow overriding
   the model tier per archetype.

4. **26-REQ-6.4** — THE `archetypes.allowlists` sub-section SHALL allow
   overriding the bash allowlist per archetype.

5. **26-REQ-6.5** — THE `coder` archetype SHALL always be enabled. WHEN config
   sets `archetypes.coder = false`, THE system SHALL ignore the setting and log
   a warning.

#### Edge Cases

1. **26-REQ-6.E1** — IF the `[archetypes]` section is absent from `config.toml`,
   THEN THE system SHALL use defaults: only `coder` enabled, all others disabled,
   all instances set to 1.

---

### Requirement 7: Multi-Instance Convergence

**User Story:** As a user, I want multiple independent reviewers to produce a
converged opinion, so that review quality improves through independent
verification.

#### Acceptance Criteria

1. **26-REQ-7.1** — WHEN a node has `instances > 1`, THE orchestrator SHALL
   dispatch N independent sessions of the same archetype in parallel and collect
   their outputs.

2. **26-REQ-7.2** — FOR the Skeptic archetype, THE convergence step SHALL union
   all findings across instances and deduplicate by exact match on the
   `(severity, description)` tuple (lowercased, whitespace-collapsed).

3. **26-REQ-7.3** — FOR the Skeptic archetype, a critical finding SHALL only
   count toward the blocking threshold IF it appears in >= ceil(N/2) instance
   outputs.

4. **26-REQ-7.4** — FOR the Verifier archetype, THE convergence step SHALL
   determine the verdict by majority vote: PASS if >= ceil(N/2) instances
   report PASS.

5. **26-REQ-7.5** — THE convergence step SHALL execute no LLM calls. It SHALL
   be deterministic string manipulation and counting only.

#### Edge Cases

1. **26-REQ-7.E1** — IF one or more instances fail (session error, timeout),
   THEN THE convergence step SHALL proceed with the remaining successful
   instances. IF zero instances succeed, THE node SHALL be marked as failed.

---

### Requirement 8: Skeptic Archetype Behavior

**User Story:** As a developer, I want an automated spec reviewer that files
findings as GitHub issues and informs the Coder, blocking execution only when
critical issues are found.

#### Acceptance Criteria

1. **26-REQ-8.1** — THE Skeptic session SHALL produce a structured review file
   at `.specs/{spec_name}/review.md` with findings categorized by severity
   (critical, major, minor, observation).

2. **26-REQ-8.2** — WHEN the Skeptic completes, THE system SHALL file a GitHub
   issue titled `[Skeptic Review] {spec_name}` with the structured findings,
   using search-before-create idempotency.

3. **26-REQ-8.3** — THE Skeptic's review content SHALL be passed as additional
   context in the successor Coder session's system prompt.

4. **26-REQ-8.4** — THE Skeptic node SHALL complete successfully (status:
   completed) UNLESS the number of critical findings (after convergence) exceeds
   `archetypes.skeptic.block_threshold` (default: 3).

5. **26-REQ-8.5** — THE Skeptic archetype SHALL use a read-only allowlist
   override: `ls`, `cat`, `git log`, `git diff`, `git show`, `wc`, `head`,
   `tail`.

#### Edge Cases

1. **26-REQ-8.E1** — WHEN the Skeptic completes with zero critical findings AND
   an existing open GitHub issue exists, THEN THE system SHALL close the issue
   with a resolution comment.

---

### Requirement 9: Verifier Archetype Behavior

**User Story:** As a developer, I want post-implementation verification that
checks code quality, test coverage, and spec conformance, with automatic
Coder retry on failure.

#### Acceptance Criteria

1. **26-REQ-9.1** — THE Verifier session SHALL produce a verification report at
   `.specs/{spec_name}/verification.md` with per-requirement pass/fail
   assessments and an overall verdict (PASS or FAIL).

2. **26-REQ-9.2** — WHEN the Verifier verdict is FAIL, THE system SHALL file a
   GitHub issue titled `[Verifier] {spec_name} group {N}: FAIL` with detailed
   findings, using search-before-create idempotency.

3. **26-REQ-9.3** — WHEN a Verifier node with `retry_predecessor = true` fails,
   THE orchestrator SHALL reset the predecessor Coder node to `pending`, attach
   the Verifier's failure report as `previous_error`, and re-run the Coder.

4. **26-REQ-9.4** — THE retry-predecessor cycle SHALL repeat up to
   `max_retries` times. WHEN retries are exhausted, THE Verifier node SHALL be
   blocked per normal orchestrator rules.

#### Edge Cases

1. **26-REQ-9.E1** — IF the predecessor node is not a Coder (e.g., due to
   manual archetype reassignment), THEN THE retry-predecessor mechanism SHALL
   still reset and re-run the predecessor regardless of its archetype.

---

### Requirement 10: GitHub Issue Idempotency

**User Story:** As a user, I want review and verification findings visible as
GitHub issues without duplicate creation on re-runs.

#### Acceptance Criteria

1. **26-REQ-10.1** — BEFORE creating a GitHub issue, THE system SHALL search for
   an existing open issue with the same title prefix using
   `gh issue list --search`.

2. **26-REQ-10.2** — WHEN a matching open issue is found, THE system SHALL
   update the existing issue body and append a comment noting the re-run.

3. **26-REQ-10.3** — WHEN no matching issue is found, THE system SHALL create a
   new issue.

#### Edge Cases

1. **26-REQ-10.E1** — IF the `gh` CLI is unavailable or the search/create
   command fails, THEN THE system SHALL log a warning and continue execution
   without filing the issue. GitHub issue filing SHALL NOT block session
   completion.

