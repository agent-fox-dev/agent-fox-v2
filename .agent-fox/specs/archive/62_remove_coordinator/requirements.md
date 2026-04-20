# Requirements Document

## Introduction

This spec removes the coordinator archetype from agent-fox. The coordinator was
a planned LLM-powered cross-spec dependency analyzer that was never wired up.
All coordinator code, configuration, templates, and tests are removed.

## Glossary

| Term | Definition |
|------|------------|
| Archetype | A named agent configuration (coder, skeptic, verifier, etc.) that determines an agent session's role, template, and model tier |
| Archetype registry | The `ARCHETYPE_REGISTRY` dict in `archetypes.py` mapping archetype names to `ArchetypeEntry` configurations |
| Coordinator | The archetype being removed; was intended as a cross-spec dependency analyzer with `task_assignable=False` |
| Layer 2 override | The coordinator's archetype assignment priority level in the three-layer system (Layer 1: default, Layer 2: coordinator, Layer 3: tasks.md tags) |
| Role mapping | The dict in `prompt.py` that maps role strings to archetype names for prompt template selection |

## Requirements

### Requirement 1: Remove Coordinator from Archetype Registry

**User Story:** As a maintainer, I want the coordinator removed from the
archetype registry so that the codebase contains no dead archetype definitions.

#### Acceptance Criteria

1. [62-REQ-1.1] THE archetype registry SHALL NOT contain a `"coordinator"` key.
2. [62-REQ-1.2] WHEN `get_archetype("coordinator")` is called, THE system SHALL
   return the fallback `"coder"` entry with a warning log.

### Requirement 2: Remove Coordinator Template

**User Story:** As a maintainer, I want the coordinator template deleted so that
no unused prompt templates remain in the codebase.

#### Acceptance Criteria

1. [62-REQ-2.1] THE template directory SHALL NOT contain a file named
   `coordinator.md`.

### Requirement 3: Remove Coordinator from Graph Builder

**User Story:** As a maintainer, I want the coordinator override code path
removed from the graph builder so that the three-layer archetype assignment
becomes a two-layer system (default + tasks.md tags).

#### Acceptance Criteria

1. [62-REQ-3.1] THE `build_graph()` function SHALL NOT accept a
   `coordinator_overrides` parameter.
2. [62-REQ-3.2] THE graph builder module SHALL NOT contain a
   `_apply_coordinator_overrides` function.
3. [62-REQ-3.3] WHEN building a graph, THE system SHALL apply archetype
   assignment in two layers: Layer 1 (default "coder") and Layer 2 (tasks.md
   tags).

### Requirement 4: Remove Coordinator from Prompt System

**User Story:** As a maintainer, I want the coordinator role mapping removed
from the prompt system so that it no longer accepts `"coordinator"` as a valid
role.

#### Acceptance Criteria

1. [62-REQ-4.1] THE prompt role mapping SHALL NOT contain a `"coordinator"`
   entry.

### Requirement 5: Remove Coordinator from Spec Parser

**User Story:** As a maintainer, I want `"coordinator"` removed from the known
archetypes list in the spec parser so that tasks.md files cannot tag groups
with a non-existent archetype.

#### Acceptance Criteria

1. [62-REQ-5.1] THE spec parser's known archetypes set SHALL NOT contain
   `"coordinator"`.

### Requirement 6: Remove Coordinator from Model Config

**User Story:** As a maintainer, I want the coordinator model tier config field
removed so that configuration does not reference a non-existent archetype.

#### Acceptance Criteria

1. [62-REQ-6.1] THE `ModelConfig` class SHALL NOT have a `coordinator` field.
2. [62-REQ-6.2] THE config generator SHALL NOT produce a coordinator model tier
   description.

#### Edge Cases

1. [62-REQ-6.E1] IF an existing config file contains a `coordinator` line under
   `[models]`, THEN THE system SHALL ignore it without error (Pydantic
   `extra="ignore"` already handles this).

### Requirement 7: Update Tests

**User Story:** As a maintainer, I want all tests updated so that no test
references a coordinator archetype that no longer exists.

#### Acceptance Criteria

1. [62-REQ-7.1] WHEN the full test suite runs, THE system SHALL pass with no
   failures related to the coordinator removal.
2. [62-REQ-7.2] THE test suite SHALL NOT contain test classes or functions that
   assert coordinator-specific behavior.
