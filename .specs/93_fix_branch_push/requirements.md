# Requirements Document

## Introduction

This document specifies the requirements for optional push of night-shift fix
branches to the upstream remote. The feature is controlled by a boolean config
field in the `[night_shift]` section and defaults to disabled.

## Glossary

- **Fix branch**: A local git branch created by the fix pipeline for an
  `af:fix` issue, named with the `fix/` prefix (e.g., `fix/42-unused-imports`).
- **Harvest**: The process of merging a fix branch into the `develop` branch
  and pushing `develop` to the remote.
- **Upstream remote**: The git remote named `origin` -- the primary remote
  repository configured for the project.
- **Force-push**: A git push that overwrites the remote ref even if it is not
  a fast-forward, using `git push --force`.
- **Fix pipeline**: The night-shift subsystem that processes `af:fix` issues
  through triage, coding, and review sessions.

## Requirements

### Requirement 1: Push Fix Branch Configuration

**User Story:** As a night-shift operator, I want to control whether fix
branches are pushed to the upstream remote, so that I can choose between
local-only and remote-visible fix branches.

#### Acceptance Criteria

1. [93-REQ-1.1] WHERE `push_fix_branch` is configured in the `[night_shift]`
   section, THE system SHALL read a boolean `push_fix_branch` field and use
   its value to control whether fix branches are pushed to the upstream remote.

2. [93-REQ-1.2] WHERE `push_fix_branch` is not present in the configuration,
   THE system SHALL default to `false` (no branch push).

#### Edge Cases

1. [93-REQ-1.E1] IF `push_fix_branch` is set to a non-boolean value, THEN
   THE system SHALL reject the configuration with a validation error.

---

### Requirement 2: Fix Branch Naming with Issue Number

**User Story:** As a night-shift operator, I want fix branch names to include
the issue number, so that branches are easily traceable to their originating
issue.

#### Acceptance Criteria

1. [93-REQ-2.1] WHEN a fix branch is created for an issue, THE system SHALL
   include the issue number in the branch name.

2. [93-REQ-2.2] WHEN a fix branch is created for issue number N with title T,
   THE system SHALL produce a branch name in the format
   `fix/{N}-{sanitized_title}` AND return the branch name to the caller for
   use in workspace creation and push operations.

#### Edge Cases

1. [93-REQ-2.E1] IF the issue title is empty or contains only special
   characters, THEN THE system SHALL produce a valid branch name using only the
   issue number (e.g., `fix/{N}`).

---

### Requirement 3: Push Behavior

**User Story:** As a night-shift operator, I want fix branches pushed to origin
before harvest, so that the branch is visible on GitHub independently of the
merge into develop.

#### Acceptance Criteria

1. [93-REQ-3.1] WHERE `push_fix_branch` is `true`, WHEN the coder-reviewer
   loop passes for a fix, THE system SHALL push the fix branch to the `origin`
   remote before harvesting into `develop` AND return a boolean indicating
   push success to the caller.

2. [93-REQ-3.2] WHERE `push_fix_branch` is `true`, WHEN pushing the fix
   branch, THE system SHALL use force-push to overwrite any existing remote
   branch with the same name.

3. [93-REQ-3.3] WHERE `push_fix_branch` is `false`, THE system SHALL NOT push
   the fix branch to the remote.

4. [93-REQ-3.4] WHERE `push_fix_branch` is `true`, THE system SHALL NOT
   delete the remote fix branch after the fix is merged into `develop`.

#### Edge Cases

1. [93-REQ-3.E1] IF the push to origin fails, THEN THE system SHALL log a
   warning and continue with the harvest without raising an exception.

2. [93-REQ-3.E2] IF the push to origin fails, THEN THE system SHALL include
   the failure reason in the warning log message.

---

### Requirement 4: Independence from Merge Strategy

**User Story:** As a night-shift operator, I want the fix branch push behavior
to be independent of the merge strategy, so that I can combine both features
as needed.

#### Acceptance Criteria

1. [93-REQ-4.1] THE system SHALL evaluate `push_fix_branch` independently of
   the `merge_strategy` setting, allowing both `"direct"` and `"pr"` merge
   strategies to coexist with either push setting.
