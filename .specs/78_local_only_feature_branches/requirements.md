# Requirements Document

## Introduction

This spec removes feature branch pushing from agent-fox's post-harvest
integration and updates all agent instructions and skill templates to reflect
a local-only feature branch workflow. Only `develop` (and `main` for releases)
is pushed to the remote.

## Glossary

- **Post-harvest integration**: The phase after a session's work is merged from
  the worktree into `develop`, where branches are pushed to the remote.
- **Feature branch**: A git branch created from `develop` for a specific task
  (e.g., `feature/78_local_only_feature_branches/1`).
- **Origin**: The remote git repository.
- **agents_md.md**: The bundled template at `_templates/agents_md.md` that is
  used to generate `AGENTS.md` in target repositories.

## Requirements

### Requirement 1: Remove Feature Branch Push from Post-Harvest

**User Story:** As a repository maintainer, I want feature branches to stay
local so that the remote forge is not polluted with short-lived branches.

#### Acceptance Criteria

1. [78-REQ-1.1] WHEN `post_harvest_integrate` is called, THE system SHALL
   NOT call `push_to_remote` with the feature branch name.
2. [78-REQ-1.2] WHEN `post_harvest_integrate` is called, THE system SHALL
   still call `_push_develop_if_pushable` to push `develop` to origin.
3. [78-REQ-1.3] WHEN `post_harvest_integrate` is called, THE system SHALL
   NOT check whether the feature branch exists locally (no
   `local_branch_exists` call for the feature branch).

#### Edge Cases

1. [78-REQ-1.E1] IF `post_harvest_integrate` is called with a workspace whose
   branch has already been deleted locally, THEN THE system SHALL still push
   `develop` without error.

### Requirement 2: Update Agent Instructions Template

**User Story:** As a coding agent, I want accurate instructions so that I do
not attempt to push feature branches to the remote.

#### Acceptance Criteria

1. [78-REQ-2.1] THE `_templates/agents_md.md` template SHALL NOT contain
   the phrase "pushed to `origin`" in the session completion section.
2. [78-REQ-2.2] THE `_templates/agents_md.md` template SHALL NOT contain
   the phrase "push the feature branch" in the git workflow section.
3. [78-REQ-2.3] THE `_templates/agents_md.md` template SHALL contain
   instructions that feature branches are local-only in the git workflow
   section.

### Requirement 3: Update af-spec Skill Template

**User Story:** As a spec author, I want the Definition of Done to reflect the
local-only branch workflow so that generated specs do not instruct agents to
push feature branches.

#### Acceptance Criteria

1. [78-REQ-3.1] THE `_templates/skills/af-spec` template SHALL NOT contain
   the phrase "pushed to remote" in the Definition of Done section.
2. [78-REQ-3.2] THE `_templates/skills/af-spec` template SHALL NOT contain
   instructions to push feature branches in the git-flow comment.

### Requirement 4: Create Spec 65 Erratum

**User Story:** As a developer, I want a documented record of the divergence
from spec 65 so that future audits understand why the code no longer matches
65-REQ-3.1.

#### Acceptance Criteria

1. [78-REQ-4.1] WHEN this spec is implemented, THE system SHALL have an
   erratum file at `docs/errata/65_no_feature_branch_push.md` documenting
   the divergence from 65-REQ-3.1 and 65-REQ-3.E1.
