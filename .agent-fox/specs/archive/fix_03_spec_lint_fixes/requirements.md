# Requirements Document

## Introduction

This spec fixes three bugs in the `agent-fox lint-spec` validator and updates
the `/af-spec` skill to prevent dangling cross-spec dependency references
during spec creation.

## Glossary

- **Verification step**: A subtask with ID pattern `N.V` (e.g., `1.V`) that
  represents the "verify task group N" checklist item.
- **Completed group**: A top-level task group whose checkbox is `[x]`.
- **Alternative dependency table**: A dependency table using the column format
  `| Spec | From Group | To Group | Relationship |`, as opposed to the
  standard `| This Spec | Depends On | What It Uses |` format.
- **Dangling reference**: A cross-spec dependency that references a spec name
  or task group number that does not exist.

## Requirements

### Requirement 1: Parse verification step subtasks

**User Story:** As a spec author, I want verification steps (`N.V`) to be
parsed as subtasks, so that the validator can correctly detect their presence.

#### Acceptance Criteria

1. [F3-REQ-1.1] WHEN a tasks.md file contains a subtask line matching the
   pattern `N.V` (e.g., `- [x] 1.V Verify task group 1`), THE parser SHALL
   include it in the task group's subtask list with `id` set to the matched
   ID string (e.g., `"1.V"`).

2. [F3-REQ-1.2] THE parser SHALL continue to parse numeric subtask IDs
   (e.g., `1.1`, `2.3`) without regression.

#### Edge Cases

1. [F3-REQ-1.E1] IF a subtask ID contains an unrecognised suffix (e.g.,
   `1.X`), THEN THE parser SHALL ignore that line (no parse, no error).

### Requirement 2: Skip structural checks for completed groups

**User Story:** As a spec author, I want completed task groups to be exempt
from structural convention warnings, so that finished specs do not produce
false-positive lint noise.

#### Acceptance Criteria

1. [F3-REQ-2.1] WHEN a task group has `completed == True`, THE validator's
   `check_oversized_groups` function SHALL skip that group.

2. [F3-REQ-2.2] WHEN a task group has `completed == True`, THE validator's
   `check_missing_verification` function SHALL skip that group.

3. [F3-REQ-2.3] WHEN a task group has `completed == False`, THE validator
   SHALL continue to check it for oversized groups and missing verification
   steps without change.

### Requirement 3: Validate alternative dependency table format

**User Story:** As a spec author, I want `lint-spec` to validate the
alternative dependency table format, so that dangling group references are
caught before `agent-fox plan` fails.

#### Acceptance Criteria

1. [F3-REQ-3.1] WHEN a `prd.md` file contains a dependency table with
   header `| Spec | From Group | To Group | Relationship |`, THE validator
   SHALL parse each data row and extract the spec name, from-group number,
   and to-group number.

2. [F3-REQ-3.2] WHEN the extracted spec name does not exist in known specs,
   THE validator SHALL produce an ERROR finding with rule
   `broken-dependency`.

3. [F3-REQ-3.3] WHEN the extracted from-group number does not exist in the
   referenced spec's task groups, THE validator SHALL produce an ERROR
   finding with rule `broken-dependency`.

4. [F3-REQ-3.4] WHEN the extracted to-group number does not exist in the
   current spec's task groups, THE validator SHALL produce an ERROR finding
   with rule `broken-dependency`.

#### Edge Cases

1. [F3-REQ-3.E1] IF a `prd.md` file contains both standard and alternative
   dependency tables, THEN THE validator SHALL validate both tables.

### Requirement 4: Update af-spec skill with dependency validation

**User Story:** As a spec author using `/af-spec`, I want the skill to
validate dependency references during spec creation, so that invalid
references are prevented before they reach `lint-spec`.

#### Acceptance Criteria

1. [F3-REQ-4.1] THE af-spec skill's SKILL.md SHALL include instructions
   to verify that every spec name in the dependency table exists as a folder
   in `.specs/`.

2. [F3-REQ-4.2] THE af-spec skill's SKILL.md SHALL include instructions
   to verify that every group number in the dependency table exists in the
   referenced spec's `tasks.md`.
