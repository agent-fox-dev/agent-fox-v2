# Requirements Document

## Introduction

The task scheduler's `ready_tasks()` method returns ready tasks in alphabetical
order by node ID. Because node IDs are prefixed with spec names (which start
with sequential numbers), this creates systematic starvation: later-numbered
specs never run while earlier-numbered specs have pending work. This spec
introduces spec-fair round-robin ordering to guarantee every spec with ready
work gets representation before any spec gets a second dispatch slot.

## Glossary

- **Ready task**: A task node whose status is `pending` and whose predecessor
  dependencies all have status `completed`.
- **Spec group**: The set of ready tasks sharing the same spec name. The spec
  name is extracted from the node ID as everything before the first colon.
- **Round-robin interleaving**: An ordering where one element is taken from each
  group in turn before any group contributes a second element.
- **Spec number**: The numeric prefix of a spec name (e.g. `67` from
  `67_quality_gate_hunt_category`). Used for ordering specs within each round.
- **Duration hint**: A predicted execution time in milliseconds, used to
  prioritize longer tasks first within a spec group.

## Requirements

### Requirement 1: Spec-Fair Ordering

**User Story:** As an orchestrator operator, I want every spec with ready tasks
to get at least one task dispatched per scheduling round, so that newly
discovered specs are not starved by existing specs.

#### Acceptance Criteria

1. [69-REQ-1.1] WHEN multiple specs have ready tasks, THE `ready_tasks()` method
   SHALL return tasks in round-robin order across spec groups, taking one task
   from each spec before returning a second task from any spec.

2. [69-REQ-1.2] WHILE interleaving across specs, THE `ready_tasks()` method
   SHALL order spec groups by spec number ascending (numeric prefix of spec
   name).

3. [69-REQ-1.3] WHEN only one spec has ready tasks, THE `ready_tasks()` method
   SHALL return tasks in the same order as it would within a single spec group
   (alphabetical, or duration-ordered if hints provided).

4. [69-REQ-1.4] WHEN a spec name has no numeric prefix, THE `ready_tasks()`
   method SHALL sort that spec after all numerically-prefixed specs.

#### Edge Cases

1. [69-REQ-1.E1] IF all ready tasks belong to the same spec, THEN THE
   `ready_tasks()` method SHALL return them ordered alphabetically (or by
   duration if hints are provided), identical to current behavior.

2. [69-REQ-1.E2] IF the ready list is empty, THEN THE `ready_tasks()` method
   SHALL return an empty list.

### Requirement 2: Duration Hint Integration

**User Story:** As an orchestrator operator, I want duration hints to influence
ordering within each spec's slot so that long tasks still start first within a
spec, without overriding cross-spec fairness.

#### Acceptance Criteria

1. [69-REQ-2.1] WHEN duration hints are provided, THE `ready_tasks()` method
   SHALL order tasks within each spec group by duration descending (longest
   first) before interleaving across specs.

2. [69-REQ-2.2] WHEN duration hints are provided, THE `ready_tasks()` method
   SHALL still interleave across specs round-robin (duration hints SHALL NOT
   override spec-fair ordering).

3. [69-REQ-2.3] WHEN duration hints are provided for some tasks but not others
   within a spec group, THE `ready_tasks()` method SHALL place hinted tasks
   before unhinted tasks within that spec group, with unhinted tasks sorted
   alphabetically.

#### Edge Cases

1. [69-REQ-2.E1] IF duration hints are provided but all ready tasks belong to
   one spec, THEN THE `ready_tasks()` method SHALL order them by duration
   descending, identical to current behavior.

### Requirement 3: Spec Name Extraction

**User Story:** As a developer, I want spec name extraction to handle all node
ID formats correctly so that interleaving works reliably.

#### Acceptance Criteria

1. [69-REQ-3.1] THE `ready_tasks()` method SHALL extract the spec name from a
   node ID by taking everything before the first colon character.

2. [69-REQ-3.2] WHEN a node ID contains multiple colons (e.g.
   `67_quality_gate:1:auditor`), THE system SHALL use only the portion before
   the first colon as the spec name.

#### Edge Cases

1. [69-REQ-3.E1] IF a node ID contains no colon, THEN THE system SHALL use the
   entire node ID as the spec name.
