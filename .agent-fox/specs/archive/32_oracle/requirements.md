# Requirements Document

## Introduction

The Oracle is a new agent archetype for agent-fox that validates a
specification's assumptions against the current codebase state before coding
begins. It detects drift between when a spec was authored and when it is
executed, producing structured findings that warn the coder about stale
references and changed contracts.

## Glossary

- **Drift**: A discrepancy between what a spec assumes about the codebase and
  the codebase's actual current state.
- **Drift finding**: A structured record describing a single instance of drift,
  categorized by severity (critical, major, minor, observation).
- **Assumption**: Any reference in a spec to a codebase artifact (file path,
  function name, class name, module structure) or behavioral contract (API
  signature, return format, error handling).
- **Oracle**: An agent archetype that performs assumption audits on specs.
- **auto_pre**: An archetype injection mode that places the archetype node
  before the first coder group in a spec's task graph.
- **Sync barrier**: A deterministic checkpoint in the orchestrator where
  execution pauses to discover new specs and perform maintenance.
- **Hot-load**: The process of discovering and incorporating new specs into the
  running task graph at a sync barrier.
- **Block threshold**: A configurable limit on the number of critical drift
  findings; exceeding it prevents coder sessions from starting.
- **Fox tools**: Token-efficient file tools (fox_outline, fox_read, fox_search,
  fox_edit) that can be registered with agent sessions.

## Requirements

### Requirement 1: Archetype Registration

**User Story:** As an agent-fox operator, I want the oracle to be a registered
archetype, so that I can enable it via configuration like other archetypes.

#### Acceptance Criteria

1. [32-REQ-1.1] WHEN the system initializes, THE `ARCHETYPE_REGISTRY` SHALL
   contain an entry named `"oracle"` with `injection="auto_pre"`,
   `task_assignable=True`, `default_model_tier="STANDARD"`, and a
   `default_allowlist` of `["ls", "cat", "git", "grep", "find", "head",
   "tail", "wc"]`.

2. [32-REQ-1.2] WHEN the oracle archetype is enabled in `config.toml` via
   `[archetypes] oracle = true`, THE system SHALL recognize the oracle as an
   active archetype for graph injection and session dispatch.

3. [32-REQ-1.3] THE oracle archetype entry SHALL reference a prompt template
   file `"oracle.md"` in its `templates` list.

#### Edge Cases

1. [32-REQ-1.E1] IF `[archetypes] oracle` is not set or is set to `false`,
   THEN THE system SHALL NOT inject oracle nodes into the task graph.

### Requirement 2: Graph Injection (auto_pre)

**User Story:** As an agent-fox operator, I want the oracle to run automatically
before coding begins, so that drift is caught before it causes wasted sessions.

#### Acceptance Criteria

1. [32-REQ-2.1] WHEN the oracle archetype is enabled and the graph builder
   constructs the task graph, THE system SHALL inject an oracle node for each
   spec, positioned before the first coder group, with an intra-spec edge from
   the oracle node to the first coder group.

2. [32-REQ-2.2] WHEN both oracle and skeptic archetypes are enabled, THE
   system SHALL inject distinct nodes for each, both positioned before the
   first coder group, and both nodes SHALL have intra-spec edges to the first
   coder group so they can execute in parallel.

3. [32-REQ-2.3] WHEN the oracle node completes, THE system SHALL allow the
   first coder group to become ready (subject to other dependency constraints).

#### Edge Cases

1. [32-REQ-2.E1] IF a spec has no coder groups (empty task list), THEN THE
   system SHALL NOT inject an oracle node for that spec.

### Requirement 3: Multi-auto_pre Support

**User Story:** As a developer, I want the graph builder to support multiple
auto_pre archetypes, so that oracle and skeptic can coexist.

#### Acceptance Criteria

1. [32-REQ-3.1] WHEN multiple archetypes with `injection="auto_pre"` are
   enabled, THE graph builder SHALL assign each a distinct node ID using the
   format `{spec_name}:0:{archetype_name}` and create intra-spec edges from
   each auto_pre node to the first coder group.

2. [32-REQ-3.2] WHEN only one auto_pre archetype is enabled, THE graph builder
   SHALL use the existing node ID format `{spec_name}:0` for backward
   compatibility.

3. [32-REQ-3.3] WHEN multiple auto_pre nodes exist for a spec, THE system
   SHALL NOT create edges between them, allowing them to execute in parallel.

#### Edge Cases

1. [32-REQ-3.E1] IF a plan.json was generated before multi-auto_pre support
   was added and contains a single `{spec}:0` skeptic node, THEN THE runtime
   injection logic SHALL add the oracle node with a distinct ID without
   conflicting with the existing node.

### Requirement 4: Sync Barrier Integration

**User Story:** As an agent-fox operator, I want newly hot-loaded specs to
receive oracle validation, so that stale specs discovered at runtime are also
checked.

#### Acceptance Criteria

1. [32-REQ-4.1] WHEN new specs are hot-loaded at a sync barrier AND the oracle
   archetype is enabled, THE system SHALL inject oracle nodes for each newly
   discovered spec before their first coder group.

2. [32-REQ-4.2] WHEN oracle nodes are injected for hot-loaded specs, THE
   system SHALL add them to the running task graph with proper edges and update
   the execution state to include the new nodes as `"pending"`.

#### Edge Cases

1. [32-REQ-4.E1] IF hot-loading fails for a spec (e.g., missing tasks.md),
   THEN THE system SHALL skip oracle injection for that spec and log a warning,
   without affecting other specs.

### Requirement 5: Assumption Audit Execution

**User Story:** As a coder agent, I want the oracle to validate the spec's
assumptions against the codebase, so that I know which references are stale
before I start coding.

#### Acceptance Criteria

1. [32-REQ-5.1] WHEN the oracle session executes, THE oracle agent SHALL read
   all spec files (requirements.md, design.md, test_spec.md, tasks.md) and
   identify references to codebase artifacts (file paths, function names, class
   names, variable names, module names).

2. [32-REQ-5.2] WHEN the oracle identifies a referenced artifact, THE oracle
   agent SHALL verify its existence and accessibility in the current codebase
   using read-only tools.

3. [32-REQ-5.3] WHEN the oracle identifies design assumptions (module
   responsibilities, API signatures, data flow descriptions), THE oracle agent
   SHALL verify that the referenced modules and interfaces still match the
   spec's description.

4. [32-REQ-5.4] WHEN the oracle identifies behavioral assumptions (return
   formats, error handling contracts, data model shapes), THE oracle agent
   SHALL verify that the referenced behavior still holds in the current code.

#### Edge Cases

1. [32-REQ-5.E1] IF a spec file is missing (e.g., no test_spec.md), THEN THE
   oracle agent SHALL skip validation for that file and note the absence as a
   minor finding.

2. [32-REQ-5.E2] IF the oracle cannot determine whether an assumption is valid
   (e.g., the referenced code is too complex to analyze), THEN THE oracle agent
   SHALL report the assumption as an observation-severity finding with an
   "inconclusive" note rather than a false positive.

### Requirement 6: Structured Output

**User Story:** As a system operator, I want oracle findings in a structured
format, so that they can be stored, queried, and rendered consistently.

#### Acceptance Criteria

1. [32-REQ-6.1] WHEN the oracle completes its audit, THE oracle agent SHALL
   output a JSON block containing a `"drift_findings"` array where each entry
   has `"severity"` (one of `"critical"`, `"major"`, `"minor"`,
   `"observation"`), `"description"` (string), and optionally
   `"spec_ref"` (the spec file and section where the assumption was found) and
   `"artifact_ref"` (the codebase artifact that drifted).

2. [32-REQ-6.2] WHEN the oracle output is parsed, THE system SHALL use the
   existing `_extract_json_blocks` mechanism from `review_parser.py` to extract
   the JSON, and a new `parse_oracle_output` function to validate and convert
   entries to `DriftFinding` dataclass instances.

3. [32-REQ-6.3] THE `DriftFinding` dataclass SHALL have fields: `id` (UUID),
   `severity` (str), `description` (str), `spec_ref` (str | None),
   `artifact_ref` (str | None), `spec_name` (str), `task_group` (str),
   `session_id` (str), `superseded_by` (str | None), `created_at`
   (datetime | None).

#### Edge Cases

1. [32-REQ-6.E1] IF the oracle output contains no valid JSON blocks, THEN THE
   parser SHALL return an empty list and log a warning.

2. [32-REQ-6.E2] IF a drift finding entry is missing required fields
   (`severity`, `description`), THEN THE parser SHALL skip that entry and log
   a warning.

### Requirement 7: Knowledge Store Persistence

**User Story:** As a system operator, I want oracle drift findings persisted in
the knowledge store, so that they can be queried across sessions and rendered
into coder context.

#### Acceptance Criteria

1. [32-REQ-7.1] WHEN oracle drift findings are parsed, THE system SHALL insert
   them into a `drift_findings` table in the DuckDB knowledge store using an
   `insert_drift_findings` function that follows the same supersession pattern
   as `insert_findings`.

2. [32-REQ-7.2] THE `drift_findings` table SHALL have columns matching the
   `DriftFinding` dataclass fields: `id` (UUID), `severity` (VARCHAR),
   `description` (VARCHAR), `spec_ref` (VARCHAR, nullable), `artifact_ref`
   (VARCHAR, nullable), `spec_name` (VARCHAR), `task_group` (VARCHAR),
   `session_id` (VARCHAR), `superseded_by` (UUID, nullable), `created_at`
   (TIMESTAMP).

3. [32-REQ-7.3] WHEN new drift findings are inserted for a (spec_name,
   task_group) pair, THE system SHALL supersede any existing active drift
   findings for the same pair by setting their `superseded_by` field to the
   new session_id.

4. [32-REQ-7.4] THE system SHALL provide a `query_active_drift_findings`
   function that returns non-superseded drift findings for a given spec_name,
   sorted by severity priority (critical first).

#### Edge Cases

1. [32-REQ-7.E1] IF the DuckDB connection is unavailable during insertion,
   THEN THE system SHALL log a warning and continue execution without blocking.

### Requirement 8: Context Rendering

**User Story:** As a coder agent, I want oracle drift findings injected into
my session context, so that I can adapt my implementation to account for
detected drifts.

#### Acceptance Criteria

1. [32-REQ-8.1] WHEN a coder session is prepared, THE system SHALL query active
   drift findings for the spec and render them as an `"## Oracle Drift Report"`
   markdown section in the session context.

2. [32-REQ-8.2] THE rendered drift report SHALL group findings by severity
   (critical, major, minor, observation) with a count summary at the top.

#### Edge Cases

1. [32-REQ-8.E1] IF no active drift findings exist for the spec, THEN THE
   system SHALL omit the `"## Oracle Drift Report"` section entirely.

### Requirement 9: Blocking Behavior

**User Story:** As an agent-fox operator, I want the oracle to block coding
when too many critical drifts are found, so that severely stale specs don't
waste coder sessions.

#### Acceptance Criteria

1. [32-REQ-9.1] WHERE the `oracle_settings.block_threshold` configuration is
   set, THE system SHALL count the number of critical-severity drift findings
   after oracle completion and compare against the threshold.

2. [32-REQ-9.2] WHEN the count of critical drift findings exceeds the
   `block_threshold`, THE system SHALL mark the oracle node as `"failed"` and
   cascade-block all downstream coder groups for that spec.

3. [32-REQ-9.3] WHEN the oracle blocks a spec, THE system SHALL log the block
   reason including the count of critical findings and the threshold value.

#### Edge Cases

1. [32-REQ-9.E1] IF `oracle_settings.block_threshold` is not configured, THEN
   THE system SHALL treat oracle findings as advisory only and always mark the
   oracle node as `"completed"`.

### Requirement 10: Configuration

**User Story:** As an agent-fox operator, I want to configure oracle behavior
through config.toml, so that I can tune the oracle for my project.

#### Acceptance Criteria

1. [32-REQ-10.1] THE system SHALL support `[archetypes] oracle = true|false`
   to enable or disable the oracle archetype (default: `false`).

2. [32-REQ-10.2] THE system SHALL support `[archetypes.oracle_settings]
   block_threshold = N` to set the critical drift count above which the oracle
   blocks execution (default: no blocking).

3. [32-REQ-10.3] THE system SHALL support `[archetypes.models] oracle =
   "TIER"` to override the oracle's model tier (default: `"STANDARD"`).

4. [32-REQ-10.4] THE system SHALL support `[archetypes.allowlists] oracle =
   [...]` to override the oracle's command allowlist.

#### Edge Cases

1. [32-REQ-10.E1] IF `oracle_settings.block_threshold` is set to a non-positive
   integer, THEN THE system SHALL clamp it to 1 and log a warning.
