# Requirements Document

## Introduction

The `agent-fox plan` command builds a task graph from specifications in
`.specs/`. This spec removes the plan cache layer so the command always
rebuilds the graph, and removes the now-redundant `--reanalyze` CLI option
along with all supporting dead code.

## Glossary

| Term | Definition |
|------|-----------|
| Task graph | The directed acyclic graph of execution nodes built from spec task groups |
| Plan cache | The mechanism by which `plan` reuses a previously serialized `plan.json` instead of rebuilding |
| `PlanMetadata` | Dataclass storing plan metadata (timestamp, version, flags) |

## Requirements

### Requirement 1: Always Rebuild

**User Story:** As a developer, I want `agent-fox plan` to always build a
fresh task graph from `.specs/`, so that the plan always reflects the current
state of specifications without relying on cache invalidation heuristics.

#### Acceptance Criteria

1. [63-REQ-1.1] WHEN the user runs `agent-fox plan`, THE system SHALL build
   the task graph from `.specs/` regardless of whether `plan.json` exists.

2. [63-REQ-1.2] WHEN the plan is built, THE system SHALL persist the result
   to `plan.json` as before.

3. [63-REQ-1.3] WHEN the plan is built, THE system SHALL derive node statuses
   from `tasks.md` checkbox state (`[x]` = COMPLETED, `[ ]` = PENDING).

### Requirement 2: Remove --reanalyze Option

**User Story:** As a developer, I want the `--reanalyze` option removed from
the CLI, so that the interface is simpler and there is no confusion about
default behavior.

#### Acceptance Criteria

1. [63-REQ-2.1] THE `plan` command SHALL NOT accept a `--reanalyze` option.

2. [63-REQ-2.2] WHEN a user passes `--reanalyze` to `agent-fox plan`, THE
   system SHALL reject it as an unrecognized option.

### Requirement 3: Remove Dead Code

**User Story:** As a maintainer, I want all cache-related code removed, so
that the codebase is simpler and contains no unused functions or fields.

#### Acceptance Criteria

1. [63-REQ-3.1] THE `plan` module SHALL NOT contain the functions
   `_compute_specs_hash`, `_compute_config_hash`, or `_cache_matches_request`.

2. [63-REQ-3.2] THE `PlanMetadata` dataclass SHALL NOT contain the fields
   `specs_hash` or `config_hash`.

#### Edge Cases

1. [63-REQ-3.E1] IF an existing `plan.json` contains `specs_hash` or
   `config_hash` fields, THEN THE system SHALL ignore them when loading
   (backward compatibility with previously serialized plans).

### Requirement 4: Documentation Update

**User Story:** As a user, I want the CLI reference to accurately reflect the
available options for the `plan` command.

#### Acceptance Criteria

1. [63-REQ-4.1] THE CLI reference documentation SHALL NOT mention the
   `--reanalyze` option.

2. [63-REQ-4.2] THE CLI reference documentation SHALL NOT describe plan
   caching behavior.
