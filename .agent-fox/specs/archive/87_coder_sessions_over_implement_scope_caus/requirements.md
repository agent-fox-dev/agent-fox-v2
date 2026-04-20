# Requirements Document

## Introduction

This specification addresses the problem of coder sessions discovering that their assigned work was already implemented by a prior task group's coder. The root cause is twofold: (1) test-writing task groups produce full implementations instead of stubs, and (2) no pre-flight check verifies whether a task group's deliverables already exist before launching a coder session. The result is wasted sessions, wasted cost, and wasted wall-clock time. This spec defines requirements for stub enforcement, pre-flight scope checking, scope overlap detection, and no-op completion tracking.

## Glossary

| Term | Definition |
|:-----|:-----------|
| **Task Group** | A unit of work within a specification, assigned to a single coder session. Task groups are numbered and may have dependencies on other task groups within the same spec. |
| **Coder Session** | An autonomous agent session launched to complete the work defined by a task group. Each session has a cost and wall-clock duration. |
| **Stub** | A function or method with a valid type signature but no meaningful implementation body. The body consists only of a placeholder such as `todo!()`, `panic!("not implemented")`, `raise NotImplementedError`, `pass`, or equivalent for the target language. |
| **Test-Writing Task Group** | A task group whose archetype is to produce failing tests and corresponding stubs for the interfaces under test. It must not produce working implementations. |
| **Pre-Flight Scope Check** | An automated check executed before a coder session is launched that compares the task group's expected deliverables against the current state of the codebase to determine whether work remains. |
| **Scope Overlap** | A condition where two or more task groups within a specification graph modify or implement the same functions, methods, or file regions. |
| **No-Op Completion** | A coder session outcome where the session produces no new commits because the assigned work was already complete. |
| **Archetype** | A template or role definition that constrains a task group's expected behavior and output format (e.g., "write failing tests," "implement module," "integrate"). |
| **Deliverable** | A discrete code artifact (function, method, struct, class, module) that a task group is expected to produce or modify. |
| **DuckDB** | The embedded analytical database used by the system to store build, session, and task-tracking telemetry. |
| **Harvest** | The post-session process that collects commits, test results, and artifacts produced by a coder session. |
| **Specification Graph** | The directed acyclic graph of task groups and their dependencies within a specification, defining execution order. |

## Requirements

### Requirement 1: Stub Enforcement for Test-Writing Task Groups

**User Story:** As a system operator, I want test-writing task groups to produce only stubs (not full implementations), so that downstream implementation task groups have meaningful work to perform.

#### Acceptance Criteria

1. `[87-REQ-1.1]` WHEN a task group has a test-writing archetype, THE system SHALL include an explicit constraint in the coder session prompt instructing the agent to produce only type signatures and stub bodies (e.g., `todo!()`, `panic!("not implemented")`, `raise NotImplementedError`, or language-equivalent placeholder) for all non-test code.

2. `[87-REQ-1.2]` WHEN a test-writing task group's coder session completes AND the session has produced commits, THE system SHALL scan all non-test source files modified by the session and verify that every new or modified function/method body contains only stub placeholders, AND return a validation result indicating pass or fail with a list of offending functions to the caller.

3. `[87-REQ-1.3]` IF a test-writing task group's commits contain non-test function bodies that are not stubs, THEN THE system SHALL flag the session as a stub-enforcement violation in the task group's completion record and emit a warning to the operator.

4. `[87-REQ-1.4]` THE system SHALL support stub detection for at minimum: Rust (`todo!()`, `unimplemented!()`, `panic!(...)`), Python (`raise NotImplementedError`, `pass` as sole body), and TypeScript/JavaScript (`throw new Error("not implemented")`) source files.

#### Edge Cases

1. `[87-REQ-1.E1]` IF a test-writing task group modifies a file that contains both test code and production code (e.g., inline tests in Rust with `#[cfg(test)]`), THEN THE system SHALL apply stub enforcement only to code outside test-attributed blocks.

2. `[87-REQ-1.E2]` IF a function body contains a stub placeholder alongside additional non-stub statements (e.g., a `todo!()` preceded by setup logic), THEN THE system SHALL classify that function as a non-stub and include it in the violation list.

3. `[87-REQ-1.E3]` IF the modified file's language is not in the supported stub-detection set, THEN THE system SHALL log a warning indicating that stub enforcement was skipped for that file and include the file path in the validation result.

---

### Requirement 2: Pre-Flight Scope Check Before Coder Session Launch

**User Story:** As a system operator, I want each coder session to verify that its assigned work has not already been completed before beginning implementation, so that sessions are not wasted on already-complete work.

#### Acceptance Criteria

1. `[87-REQ-2.1]` WHEN a coder session is about to be launched for a task group, THE system SHALL execute a pre-flight scope check that compares each deliverable listed in the task group's work specification against the current codebase state AND return a scope-check result containing a per-deliverable status (pending, already-implemented, or indeterminate) to the session launcher.

2. `[87-REQ-2.2]` WHEN the pre-flight scope check determines that all deliverables for a task group are already implemented, THE system SHALL skip launching the coder session AND record the task group as a "pre-flight skip" completion with zero cost.

3. `[87-REQ-2.3]` WHEN the pre-flight scope check determines that some but not all deliverables are already implemented, THE system SHALL launch the coder session with a reduced scope prompt listing only the pending deliverables AND include the list of already-implemented deliverables for context.

4. `[87-REQ-2.4]` THE system SHALL determine a deliverable's implementation status by checking whether the corresponding function or method body contains only stub placeholders (as defined in Requirement 1) or has substantive implementation logic, AND classify stubs as "pending" and non-stubs as "already-implemented."

5. `[87-REQ-2.5]` WHEN the pre-flight scope check completes, THE system SHALL log the check duration, the number of deliverables checked, and the per-deliverable status to the telemetry store.

#### Edge Cases

1. `[87-REQ-2.E1]` IF a deliverable references a function or file that does not yet exist in the codebase, THEN THE system SHALL classify that deliverable as "pending."

2. `[87-REQ-2.E2]` IF the pre-flight scope check cannot parse a source file (e.g., syntax error, binary file), THEN THE system SHALL classify all deliverables in that file as "indeterminate" AND proceed with launching the coder session for those deliverables.

3. `[87-REQ-2.E3]` IF the task group's work specification does not enumerate specific deliverables (e.g., it is described in natural language only without function-level granularity), THEN THE system SHALL classify the scope check result as "indeterminate" AND proceed with launching the coder session, logging a warning that scope check was inconclusive.

---

### Requirement 3: Scope Overlap Detection at the Specification Graph Level

**User Story:** As a specification author, I want the system to detect when multiple task groups modify the same code regions, so that I can resolve overlapping scopes before execution and prevent redundant work.

#### Acceptance Criteria

1. `[87-REQ-3.1]` WHEN a specification graph is finalized (i.e., all task groups and their deliverables are defined), THE system SHALL compare the deliverable lists across all task groups in the graph and identify any function, method, or file region that appears in more than one task group's deliverables, AND return a list of overlap records containing the overlapping deliverable identifier and the involved task group numbers.

2. `[87-REQ-3.2]` IF scope overlap is detected between two or more task groups, THEN THE system SHALL emit a warning to the operator listing each overlapping deliverable and the conflicting task group numbers.

3. `[87-REQ-3.3]` WHEN scope overlap is detected AND the overlapping task groups do not have a dependency relationship (neither depends on the other), THE system SHALL escalate the warning to an error that blocks execution until resolved by the operator.

4. `[87-REQ-3.4]` WHEN scope overlap is detected AND the overlapping task groups have an explicit dependency relationship (one depends on the other), THE system SHALL emit a warning but allow execution to proceed, noting that the downstream group's pre-flight check (Requirement 2) will handle already-complete deliverables.

#### Edge Cases

1. `[87-REQ-3.E1]` IF a task group's deliverable list is empty or undefined, THEN THE system SHALL exclude that task group from overlap analysis AND log a warning indicating the task group has no enumerated deliverables.

2. `[87-REQ-3.E2]` IF two task groups reference the same file but different functions within that file, THEN THE system SHALL NOT flag this as a scope overlap.

3. `[87-REQ-3.E3]` IF the specification graph contains only a single task group, THEN THE system SHALL skip overlap detection and return an empty overlap list.

---

### Requirement 4: No-Op Completion Tracking

**User Story:** As a system operator, I want no-op coder session completions tracked distinctly from successful completions, so that I can measure how often sessions find their work already done and use that signal to improve task decomposition.

#### Acceptance Criteria

1. `[87-REQ-4.1]` WHEN a coder session completes AND the harvest process detects zero new commits on the session's branch relative to the base branch, THE system SHALL record the session outcome as "no-op" in the DuckDB telemetry store, distinct from "success" or "failure" outcomes.

2. `[87-REQ-4.2]` WHEN a coder session is skipped due to a pre-flight scope check (per Requirement 2), THE system SHALL record the session outcome as "pre-flight-skip" in the DuckDB telemetry store, distinct from "no-op," "success," and "failure."

3. `[87-REQ-4.3]` THE system SHALL store the following fields for every no-op or pre-flight-skip completion: specification number, task group number, session duration, session cost, timestamp, and the reason classification (no-op or pre-flight-skip).

4. `[87-REQ-4.4]` WHEN queried, THE system SHALL return aggregate no-op and pre-flight-skip counts grouped by specification number, AND return per-specification totals of wasted session cost and duration to the caller.

#### Edge Cases

1. `[87-REQ-4.E1]` IF a coder session produces commits that consist solely of whitespace, formatting, or comment changes with no functional code changes, THEN THE system SHALL classify the session outcome as "no-op."

2. `[87-REQ-4.E2]` IF the harvest process fails to determine the commit count (e.g., git error, missing branch), THEN THE system SHALL classify the session outcome as "harvest-error" AND log the error details rather than misclassifying as no-op.

3. `[87-REQ-4.E3]` IF a session was launched, produced no commits, but the session itself ended in an error (e.g., agent crash, timeout), THEN THE system SHALL classify the outcome as "failure" rather than "no-op," preserving the distinction that no-op means the work was already done.

---

### Requirement 5: Prompt Content Verification for Stub Constraints

**User Story:** As a system operator, I want to verify that the stub-enforcement constraint is actually present in prompts sent to test-writing coder sessions, so that I can trust the enforcement mechanism is active.

#### Acceptance Criteria

1. `[87-REQ-5.1]` WHEN the system constructs a prompt for a test-writing task group's coder session, THE system SHALL include a machine-parseable directive (e.g., a tagged instruction block) constraining the agent to stub-only output for non-test code, AND return the complete prompt text to the caller for inspection or logging.

2. `[87-REQ-5.2]` THE system SHALL persist the full prompt text for every coder session in the telemetry store, enabling post-hoc audit of whether stub constraints were included.

3. `[87-REQ-5.3]` WHEN a stub-enforcement violation is detected (per Requirement 1), THE system SHALL include in the violation record whether the stub constraint directive was present in the session's prompt, to distinguish between "constraint missing from prompt" and "agent ignored constraint."

#### Edge Cases

1. `[87-REQ-5.E1]` IF the prompt exceeds the storage size limit for the telemetry store, THEN THE system SHALL store a truncated version retaining at least the first 500 and last 500 characters AND set a "truncated" flag on the record.