# Requirements Document

## Introduction

This specification creates the Maintainer archetype with two modes: hunt
(analysis and triage) and extraction (knowledge extraction from session
transcripts). It absorbs the standalone triage archetype and provides the
archetype identity for nightshift analysis tasks.

## Glossary

- **Maintainer**: The archetype for analysis and knowledge tasks. Does not
  implement fixes (that's the Coder's job).
- **Hunt mode**: Maintainer mode for scanning the codebase, triaging issues,
  and producing structured work items. Read-only + shell.
- **Extraction mode**: Maintainer mode for extracting facts from session
  transcripts into the knowledge store. No filesystem access.
- **Triage**: The legacy standalone archetype for issue prioritization,
  absorbed into maintainer:hunt.
- **HuntScanner**: The programmatic scanner that runs category detectors
  to produce findings.
- **Knowledge store**: The DuckDB-backed fact storage used by the knowledge
  system.
- **Session transcript**: The full conversation history from an agent session,
  used as input for knowledge extraction.

## Requirements

### Requirement 1: Maintainer Archetype Definition

**User Story:** As a developer, I want a maintainer archetype with modes so
that analysis tasks have a formal archetype identity with appropriate
permissions.

#### Acceptance Criteria

[100-REQ-1.1] THE `ARCHETYPE_REGISTRY` SHALL contain a `"maintainer"` entry
with modes `"hunt"` and `"extraction"`.

[100-REQ-1.2] THE maintainer's hunt mode SHALL have a read-only analysis
allowlist (`ls`, `cat`, `git`, `wc`, `head`, `tail`), no injection (manual
only), STANDARD model tier, and `task_assignable=False`.

[100-REQ-1.3] THE maintainer's extraction mode SHALL have an empty allowlist
(no shell access), no injection, STANDARD model tier, and
`task_assignable=False`.

[100-REQ-1.4] THE maintainer base entry SHALL have `task_assignable=False`
(neither mode is used in the spec-driven task graph).

#### Edge Cases

[100-REQ-1.E1] IF `get_archetype("triage")` is called after migration, THEN
THE system SHALL log a warning and fall back to the `"coder"` entry (same
as other removed archetypes).

### Requirement 2: Triage Absorption

**User Story:** As the nightshift pipeline, I need triage functionality to
use the maintainer:hunt identity so that archetype configuration is unified.

#### Acceptance Criteria

[100-REQ-2.1] THE `ARCHETYPE_REGISTRY` SHALL NOT contain a `"triage"` entry.

[100-REQ-2.2] WHEN the nightshift engine's `run_batch_triage()` function
executes an AI triage call, THE system SHALL reference
`archetype="maintainer"`, `mode="hunt"` for model tier resolution and
security configuration.

[100-REQ-2.3] THE maintainer:hunt mode's template SHALL incorporate the
triage template content (issue ordering, dependency detection, supersession
identification).

#### Edge Cases

[100-REQ-2.E1] IF config contains the old key `archetypes.triage`, THEN THE
system SHALL log a deprecation warning (but not fail, since triage was
not a user-toggled archetype).

### Requirement 3: Maintainer Template

**User Story:** As an agent, I need a template that defines my role as
maintainer in hunt or extraction mode.

#### Acceptance Criteria

[100-REQ-3.1] THE system SHALL provide a `maintainer.md` template (or default
profile) containing shared maintainer identity, plus mode-specific sections
for hunt and extraction.

[100-REQ-3.2] THE hunt mode section SHALL include guidance for: codebase
scanning, issue triage, dependency detection, finding consolidation, and
work item creation.

[100-REQ-3.3] THE extraction mode section SHALL include guidance for:
reading session transcripts, identifying causal relationships, extracting
architectural decisions, recording failure patterns, and writing structured
facts.

### Requirement 4: Extraction Mode Interface

**User Story:** As a future implementer of knowledge extraction, I need a
well-defined interface so that the extraction pipeline can be built
incrementally.

#### Acceptance Criteria

[100-REQ-4.1] THE system SHALL define an `ExtractionInput` dataclass with
fields: `session_id: str`, `transcript: str`, `spec_name: str`,
`archetype: str`, `mode: str | None`.

[100-REQ-4.2] THE system SHALL define an `ExtractionResult` dataclass with
fields: `facts: list[dict]`, `session_id: str`, `status: str`.

[100-REQ-4.3] THE system SHALL provide a stub function
`extract_knowledge(input: ExtractionInput) -> ExtractionResult` that returns
an empty result with `status="not_implemented"` AND logs an info message.

#### Edge Cases

[100-REQ-4.E1] WHEN `extract_knowledge()` is called, THE system SHALL NOT
raise an error — it SHALL return a valid empty result.

### Requirement 5: Nightshift Integration

**User Story:** As the nightshift engine, I need the triage AI call to resolve
its model tier and security config from the maintainer:hunt archetype.

#### Acceptance Criteria

[100-REQ-5.1] WHEN the nightshift engine resolves model tier for triage AI
calls, THE system SHALL use `resolve_model_tier(config, "maintainer",
mode="hunt")` AND return the resolved tier.

[100-REQ-5.2] WHEN the nightshift engine resolves security config for triage
AI calls, THE system SHALL use `resolve_security_config(config, "maintainer",
mode="hunt")` AND return the resolved config.

[100-REQ-5.3] THE nightshift triage prompt builder SHALL load the
maintainer:hunt template content for triage sessions.
