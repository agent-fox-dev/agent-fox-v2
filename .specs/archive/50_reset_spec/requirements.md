# Requirements Document

## Introduction

Spec-scoped reset command: a `--spec <spec_name>` option for `agent-fox reset`
that resets all tasks belonging to a single specification to `pending`, cleans
up associated artifacts, and synchronizes `tasks.md` and `plan.json` — without
affecting other specs or performing git rollback.

## Glossary

- **Spec**: A numbered specification folder under `.specs/` containing
  requirements, design, test spec, and tasks documents.
- **Node**: A task graph node representing either a coder task group or an
  injected archetype review (skeptic, auditor, verifier, oracle).
- **Spec name**: The folder name of a spec (e.g., `11_echo_server_migration`),
  used as the `spec_name` field on graph nodes.
- **Coder node**: A node with `archetype == "coder"` representing a real
  implementation task group from `tasks.md`.
- **Archetype node**: A node injected by the graph builder for review tasks
  (skeptic, auditor, verifier, oracle).
- **State file**: `.agent-fox/state.jsonl`, the append-only execution state.
- **Plan file**: `.agent-fox/plan.json`, the persisted task graph.

## Requirements

### Requirement 1: Spec-Scoped Reset

**User Story:** As a developer, I want to reset all tasks for a single spec so
that I can re-execute it without affecting other specs.

#### Acceptance Criteria

1. [50-REQ-1.1] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL set the status of every node whose `spec_name` matches `<spec_name>`
   to `pending` in `state.jsonl`.

2. [50-REQ-1.2] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL include both coder nodes and archetype nodes (skeptic, auditor,
   verifier, oracle) belonging to the spec in the reset.

3. [50-REQ-1.3] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL NOT modify the status of any node belonging to a different spec.

4. [50-REQ-1.4] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL clean up worktrees and local feature branches for all reset nodes.

5. [50-REQ-1.5] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL reset top-level `tasks.md` checkboxes for all task groups in the spec
   from `[x]` or `[-]` to `[ ]`.

6. [50-REQ-1.6] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL set the `status` field to `pending` in `plan.json` for all nodes
   belonging to the spec.

7. [50-REQ-1.7] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL NOT perform any git rollback on the `develop` branch.

8. [50-REQ-1.8] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL NOT compact the knowledge base.

#### Edge Cases

1. [50-REQ-1.E1] IF `<spec_name>` does not match any node in the plan, THEN
   THE system SHALL exit with a non-zero code and display an error listing
   all valid spec names.

2. [50-REQ-1.E2] IF the plan file does not exist, THEN THE system SHALL exit
   with a non-zero code and instruct the user to run `agent-fox plan`.

3. [50-REQ-1.E3] IF the state file does not exist, THEN THE system SHALL exit
   with a non-zero code and display an appropriate error message.

4. [50-REQ-1.E4] IF the spec has nodes in the plan but all are already
   `pending`, THEN THE system SHALL return a result with an empty
   `reset_tasks` list (no-op).

### Requirement 2: Mutual Exclusivity

**User Story:** As a developer, I want clear errors when combining incompatible
reset options so that I don't accidentally trigger the wrong reset mode.

#### Acceptance Criteria

1. [50-REQ-2.1] IF `--spec` is combined with `--hard`, THEN THE system SHALL
   exit with a non-zero code and display an error that the options are mutually
   exclusive.

2. [50-REQ-2.2] IF `--spec` is combined with a positional `<task_id>` argument,
   THEN THE system SHALL exit with a non-zero code and display an error that
   the options are mutually exclusive.

### Requirement 3: Confirmation and Output

**User Story:** As a developer, I want confirmation before a destructive spec
reset and clear output showing what was reset.

#### Acceptance Criteria

1. [50-REQ-3.1] WHEN the user runs `reset --spec <spec_name>` without `--yes`,
   THE system SHALL prompt for interactive confirmation before proceeding.

2. [50-REQ-3.2] WHEN the user declines the confirmation prompt, THE system
   SHALL abort without modifying any state.

3. [50-REQ-3.3] WHEN the user runs `reset --spec <spec_name> --yes`, THE system
   SHALL skip the confirmation prompt.

4. [50-REQ-3.4] WHEN JSON mode is active (`--json`), THE system SHALL skip the
   confirmation prompt and output a JSON object with keys `reset_tasks`,
   `cleaned_worktrees`, and `cleaned_branches`.

5. [50-REQ-3.5] WHEN the reset completes, THE system SHALL display the count
   and IDs of reset tasks, cleaned worktrees, and cleaned branches.

### Requirement 4: Preservation

**User Story:** As a developer, I want the spec reset to preserve session
history and cost data so that I don't lose audit information.

#### Acceptance Criteria

1. [50-REQ-4.1] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL preserve all session history records in `state.jsonl`.

2. [50-REQ-4.2] WHEN the user runs `reset --spec <spec_name>`, THE system
   SHALL preserve token counters and cost totals.
