# Requirements Document

## Introduction

This specification adds two capabilities to agent-fox's git integration layer:
a file-based merge lock that serializes concurrent merge operations on the
`develop` branch, and an agent-based fallback that intelligently resolves merge
conflicts when deterministic strategies fail.

## Glossary

| Term | Definition |
|------|-----------|
| Harvest | The process of merging a feature branch's changes into the `develop` branch after a successful coding session. |
| Merge lock | A file-based mutual exclusion mechanism that prevents concurrent merge operations on the `develop` branch. |
| Merge agent | A dedicated coding agent session spawned solely to resolve git merge conflicts. |
| Stale lock | A merge lock that was not released because the holding process crashed or timed out. |
| Develop sync | The operation of synchronizing local `develop` with `origin/develop` (`_sync_develop_with_remote`). |
| ADVANCED tier | The highest model tier in the agent-fox model registry, currently mapped to `claude-opus-4-6`. |
| Lock file | The file at `<repo>/.agent-fox/merge.lock` used to implement the merge lock. |

## Requirements

### Requirement 1: Merge Lock Acquisition

**User Story:** As an engine operator, I want merge operations to be serialized,
so that concurrent harvests do not corrupt the git working tree.

#### Acceptance Criteria

1. [45-REQ-1.1] WHEN a harvest or develop-sync operation begins, THE system
   SHALL acquire the merge lock before executing any git checkout or merge
   commands on the `develop` branch.

2. [45-REQ-1.2] WHILE the merge lock is held by another operation, THE system
   SHALL queue the requesting operation and wait until the lock becomes
   available or the timeout expires.

3. [45-REQ-1.3] WHEN the lock wait timeout expires, THE system SHALL raise an
   `IntegrationError` with a message indicating the lock could not be acquired.

4. [45-REQ-1.4] THE merge lock SHALL serialize access across asyncio tasks
   within a single process AND across separate OS processes operating on the
   same repository.

#### Edge Cases

1. [45-REQ-1.E1] IF the lock file's modification time is older than the stale
   lock timeout (default 5 minutes), THEN THE system SHALL treat the lock as
   stale, remove it, and attempt to acquire a fresh lock.

2. [45-REQ-1.E2] IF the `.agent-fox/` directory does not exist when lock
   acquisition is attempted, THEN THE system SHALL create it before writing
   the lock file.

3. [45-REQ-1.E3] IF two processes attempt to break the same stale lock
   simultaneously, THEN THE system SHALL ensure only one succeeds via atomic
   file operations.

### Requirement 2: Merge Lock Release

**User Story:** As an engine operator, I want the merge lock to be reliably
released, so that subsequent operations are not blocked.

#### Acceptance Criteria

1. [45-REQ-2.1] WHEN the merge operation completes (success or failure), THE
   system SHALL release the merge lock by removing the lock file.

2. [45-REQ-2.2] THE merge lock SHALL be usable as an async context manager
   (`async with merge_lock:`) to ensure automatic release on exit.

#### Edge Cases

1. [45-REQ-2.E1] IF the lock file has already been removed when release is
   attempted (e.g., broken by another process as stale), THEN THE system
   SHALL log a warning and continue without raising an error.

### Requirement 3: Lock Coverage

**User Story:** As an engine operator, I want all merge-related git operations
to be covered by the lock, so that no race conditions exist.

#### Acceptance Criteria

1. [45-REQ-3.1] THE merge lock SHALL cover the entire harvest operation:
   checkout of `develop`, merge/rebase, and post-harvest integration (push,
   PR creation).

2. [45-REQ-3.2] THE merge lock SHALL cover the develop-sync operation
   (`_sync_develop_with_remote`): fetch, checkout, rebase/merge of
   `origin/develop`.

### Requirement 4: Agent Fallback on Merge Failure

**User Story:** As an engine operator, I want an intelligent agent to resolve
merge conflicts when deterministic strategies fail, so that valid changes are
not silently discarded.

#### Acceptance Criteria

1. [45-REQ-4.1] WHEN fast-forward merge, rebase + fast-forward, and merge
   commit all fail during harvest, THE system SHALL spawn a merge agent to
   resolve the conflicts instead of using `-X theirs`.

2. [45-REQ-4.2] THE merge agent SHALL use the ADVANCED model tier
   (resolved via `resolve_model_id("ADVANCED")`).

3. [45-REQ-4.3] THE merge agent SHALL be instructed to resolve merge conflicts
   only — no test fixes, no refactoring, no feature changes.

4. [45-REQ-4.4] WHEN the merge agent is spawned, THE system SHALL provide the
   git conflict output (diff or conflict markers) as context in the agent's
   prompt, if available.

5. [45-REQ-4.5] WHEN the merge agent resolves all conflicts and commits, THE
   system SHALL complete the merge into `develop` using the agent's resolution.

#### Edge Cases

1. [45-REQ-4.E1] IF the merge agent fails to resolve the conflicts, THEN THE
   system SHALL abort the merge and raise an `IntegrationError` with a message
   describing the agent failure.

2. [45-REQ-4.E2] IF the merge agent session encounters an API error or timeout,
   THEN THE system SHALL treat it as an agent failure and abort the merge.

### Requirement 5: Agent Fallback for Develop Sync

**User Story:** As an engine operator, I want the agent fallback to also apply
to develop-sync conflicts, so that origin/develop reconciliation is robust.

#### Acceptance Criteria

1. [45-REQ-5.1] WHEN rebase and merge-commit strategies fail during
   `_sync_develop_with_remote`, THE system SHALL spawn a merge agent to
   resolve the conflicts instead of using `-X ours`.

2. [45-REQ-5.2] WHEN the merge agent resolves develop-sync conflicts, THE
   system SHALL complete the merge of `origin/develop` into local `develop`.

#### Edge Cases

1. [45-REQ-5.E1] IF the merge agent fails during develop-sync, THEN THE system
   SHALL log a warning and leave local `develop` as-is (matching the current
   behavior when all strategies fail).

### Requirement 6: Removal of Blind Strategy Options

**User Story:** As a developer, I want blind conflict resolution strategies
removed, so that merge conflicts are always resolved intelligently.

#### Acceptance Criteria

1. [45-REQ-6.1] THE system SHALL NOT use `-X theirs` as a merge strategy
   option in the harvest flow.

2. [45-REQ-6.2] THE system SHALL NOT use `-X ours` as a merge strategy option
   in the develop-sync flow.
