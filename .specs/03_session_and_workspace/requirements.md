# Requirements Document

## Introduction

This document specifies the session execution and workspace isolation layer of
agent-fox v2. It covers git worktree management, coding session execution via
the claude-code-sdk, context assembly, prompt construction, timeout
enforcement, session outcome capture, and change integration (harvesting).

## Glossary

| Term | Definition |
|------|-----------|
| Worktree | A git worktree -- a separate working directory linked to the same repository, providing filesystem isolation for a coding session |
| Session | A single invocation of the claude-code-sdk `query()` function that executes a coding task in an isolated worktree |
| Harvester | The component that validates a session's changes and merges them from the feature branch into the development branch |
| Context | The collection of spec documents and memory facts assembled for a specific coding session |
| Feature branch | A git branch created per task group: `feature/{spec_name}/{group_number}` |
| Development branch | The long-lived integration branch (default: `develop`) where completed work is merged |
| Outcome | A structured record of a session's result: status, files touched, token usage, duration, and any error |
| Allowlist | The set of shell commands the coding agent is permitted to execute via the Bash tool |

## Requirements

### Requirement 1: Workspace Creation

**User Story:** As the orchestrator, I need to create an isolated workspace
for each coding session so that concurrent or sequential sessions cannot
interfere with each other or with already-integrated work.

#### Acceptance Criteria

1. [03-REQ-1.1] WHEN a workspace is requested for a spec and task group, THE
   system SHALL create a git worktree at
   `.agent-fox/worktrees/{spec_name}/{group_number}` branching from the
   current tip of the development branch.
2. [03-REQ-1.2] WHEN a workspace is created, THE system SHALL create a feature
   branch named `feature/{spec_name}/{group_number}` and check it out in the
   worktree.
3. [03-REQ-1.3] WHEN a workspace is created, THE system SHALL return a
   `WorkspaceInfo` containing the worktree path, branch name, spec name, and
   task group number.

#### Edge Cases

1. [03-REQ-1.E1] IF a worktree already exists at the target path, THEN THE
   system SHALL remove the stale worktree and re-create it from a fresh branch
   point.
2. [03-REQ-1.E2] IF the feature branch already exists, THEN THE system SHALL
   delete it before creating a fresh one to avoid stale state.
3. [03-REQ-1.E3] IF worktree creation fails (e.g., git error), THEN THE
   system SHALL raise a `WorkspaceError` with the underlying git error message.

---

### Requirement 2: Workspace Cleanup

**User Story:** As the orchestrator, I need to destroy workspaces after
sessions complete so that disk space is reclaimed and stale state does not
accumulate.

#### Acceptance Criteria

1. [03-REQ-2.1] WHEN a workspace is destroyed, THE system SHALL remove the git
   worktree and delete the feature branch (both local and any tracking ref).
2. [03-REQ-2.2] WHEN all workspaces for a spec are destroyed, THE system SHALL
   remove the empty spec directory under `.agent-fox/worktrees/`.

#### Edge Cases

1. [03-REQ-2.E1] IF the worktree path does not exist, THEN THE system SHALL
   treat cleanup as a no-op and not raise an error.
2. [03-REQ-2.E2] IF branch deletion fails (e.g., branch does not exist), THEN
   THE system SHALL log a warning and continue cleanup.

---

### Requirement 3: Session Execution

**User Story:** As the orchestrator, I need to execute a coding session that
drives the claude-code-sdk with a task-specific prompt in an isolated
workspace, and receive a structured outcome when the session completes.

#### Acceptance Criteria

1. [03-REQ-3.1] THE session runner SHALL invoke the claude-code-sdk `query()`
   function with a prompt string, a system prompt, the workspace path as
   `cwd`, and the configured coding model.
2. [03-REQ-3.2] THE session runner SHALL iterate over all messages from the
   async iterator returned by `query()`, collecting the final `ResultMessage`
   to extract token usage, duration, and error status.
3. [03-REQ-3.3] WHEN the session completes, THE session runner SHALL return
   a `SessionOutcome` containing: spec name, task group, node ID, status
   (`completed` | `failed` | `timeout`), files touched, input tokens, output
   tokens, duration in milliseconds, and any error message.
4. [03-REQ-3.4] THE session runner SHALL set `permission_mode` to
   `"bypassPermissions"` and register a PreToolUse hook that enforces the
   configured command allowlist on Bash tool invocations.

#### Edge Cases

1. [03-REQ-3.E1] IF the claude-code-sdk raises a `ClaudeSDKError` or any of
   its subclasses, THEN THE session runner SHALL catch it, wrap it in a
   `SessionError`, and return a `SessionOutcome` with status `failed`.
2. [03-REQ-3.E2] IF the `ResultMessage` indicates `is_error=True`, THEN THE
   session runner SHALL set the outcome status to `failed` and capture the
   error details in `error_message`.

---

### Requirement 4: Context Assembly

**User Story:** As the orchestrator, I need to assemble task-specific context
for each coding session so that the coding agent has the information it needs
to complete the task correctly.

#### Acceptance Criteria

1. [03-REQ-4.1] THE context assembler SHALL locate and read the specification
   documents for the target spec: `requirements.md`, `design.md`, and
   `tasks.md` from the `.specs/{spec_name}/` directory.
2. [03-REQ-4.2] THE context assembler SHALL accept a list of memory facts
   (strings) relevant to the current task and include them in the assembled
   context.
3. [03-REQ-4.3] THE context assembler SHALL return the assembled context as a
   single string suitable for inclusion in the system prompt, with clear
   section headers separating spec documents from memory facts.

#### Edge Cases

1. [03-REQ-4.E1] IF a spec document file does not exist, THEN THE context
   assembler SHALL skip it and log a warning, rather than failing.

---

### Requirement 5: Prompt Building

**User Story:** As the session runner, I need system and task prompts that
instruct the coding agent on what to build, where, and how.

#### Acceptance Criteria

1. [03-REQ-5.1] THE prompt builder SHALL construct a system prompt that
   includes: the agent's role, the assembled context (spec docs + memory),
   the target task group number, and instructions to follow the spec's
   acceptance criteria.
2. [03-REQ-5.2] THE prompt builder SHALL construct a task prompt that
   identifies the specific task group to implement, references the tasks.md
   subtask list, and instructs the agent to commit changes on the feature
   branch.

---

### Requirement 6: Session Timeout

**User Story:** As the orchestrator, I need to enforce a maximum session
duration so that runaway sessions do not consume unbounded resources.

#### Acceptance Criteria

1. [03-REQ-6.1] THE session runner SHALL wrap the SDK query execution in
   `asyncio.wait_for()` with a timeout derived from
   `config.orchestrator.session_timeout` (converted from minutes to seconds).
2. [03-REQ-6.2] WHEN a session exceeds the timeout, THE system SHALL cancel
   the query, and return a `SessionOutcome` with status `timeout`.

#### Edge Cases

1. [03-REQ-6.E1] WHEN a timeout occurs, THE system SHALL preserve any partial
   metrics (tokens, duration) that were observed from messages received before
   the timeout.

---

### Requirement 7: Change Integration (Harvesting)

**User Story:** As the orchestrator, I need to integrate a session's committed
changes from the feature branch into the development branch, handling merge
conflicts automatically when possible.

#### Acceptance Criteria

1. [03-REQ-7.1] WHEN a session completes successfully with commits on the
   feature branch, THE harvester SHALL attempt a fast-forward merge of the
   feature branch into the development branch.
2. [03-REQ-7.2] IF a fast-forward merge fails due to conflicts, THEN THE
   harvester SHALL rebase the feature branch onto the current development
   branch tip and retry the merge.
3. [03-REQ-7.3] WHEN the merge succeeds, THE harvester SHALL return the list
   of files that were changed.

#### Edge Cases

1. [03-REQ-7.E1] IF the rebase also fails (unresolvable conflict), THEN THE
   harvester SHALL abort the rebase, raise an `IntegrationError`, and leave
   the development branch unchanged.
2. [03-REQ-7.E2] IF the feature branch has no new commits relative to the
   development branch, THEN THE harvester SHALL treat this as a no-op and
   return an empty file list.

---

### Requirement 8: Security Enforcement

**User Story:** As the operator, I need the coding agent's shell commands to
be restricted to a configured allowlist so that dangerous operations are
blocked.

#### Acceptance Criteria

1. [03-REQ-8.1] THE session runner SHALL register a PreToolUse hook that
   intercepts Bash tool invocations and extracts the command name (the first
   token of the command string).
2. [03-REQ-8.2] IF the command is not on the effective allowlist (configured
   allowlist or default + extensions), THEN THE hook SHALL block the tool
   invocation by returning a `decision: "block"` with a message identifying
   the blocked command.

#### Edge Cases

1. [03-REQ-8.E1] IF the command string is empty or cannot be parsed, THEN THE
   hook SHALL block the invocation with a descriptive error message.

---

### Requirement 9: Git Operations

**User Story:** As the workspace and harvester modules, I need reliable git
operations (branch creation, commit detection, merge, rebase) that are
implemented consistently and raise domain-specific errors.

#### Acceptance Criteria

1. [03-REQ-9.1] THE git module SHALL provide functions for: creating and
   deleting branches, checking out branches in worktrees, detecting new
   commits on a branch relative to another, performing fast-forward merges,
   and performing rebases.
2. [03-REQ-9.2] ALL git operations SHALL raise `WorkspaceError` or
   `IntegrationError` (as appropriate) when the underlying git command fails,
   wrapping the stderr output in the error message.
