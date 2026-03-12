# Requirements Document

## Introduction

This document specifies the Claude Code settings setup that the `agent-fox init`
command performs. When agent-fox drives Claude Code sessions, it needs
pre-approved tool permissions in `.claude/settings.local.json` to avoid
interactive permission prompts. This spec extends the init command (01-REQ-3)
to create and maintain that file.

## Glossary

| Term | Definition |
|------|-----------|
| settings.local.json | Claude Code's project-level permission configuration file at `.claude/settings.local.json` |
| Canonical permissions | The fixed set of tool permissions required for autonomous agent-fox session execution |
| Merge | Adding missing canonical entries to an existing file while preserving user-added entries |

## Requirements

### Requirement 1: Claude Code Settings Creation

**User Story:** As a developer, I want `agent-fox init` to create
`.claude/settings.local.json` with the required permissions, so that
coding sessions can run autonomously without interactive permission prompts.

#### Acceptance Criteria

1. [17-REQ-1.1] WHEN the init command runs and `.claude/settings.local.json`
   does not exist, THE system SHALL create the file containing the canonical
   permission list as a valid JSON object.

2. [17-REQ-1.2] WHEN the init command runs and the `.claude/` directory does
   not exist, THE system SHALL create the directory before writing the file.

3. [17-REQ-1.3] THE canonical permission list SHALL include all entries
   specified in the design document's `CANONICAL_PERMISSIONS` constant.

#### Edge Cases

1. [17-REQ-1.E1] IF the init command runs and `.claude/settings.local.json`
   already exists with all canonical entries present, THEN THE system SHALL
   leave the file unchanged.

---

### Requirement 2: Settings Merge on Re-Init

**User Story:** As a developer, I want re-running `agent-fox init` to add any
missing canonical permissions without removing my custom entries, so that my
hand-added permissions are preserved.

#### Acceptance Criteria

1. [17-REQ-2.1] WHEN the init command runs and `.claude/settings.local.json`
   exists with missing canonical entries, THE system SHALL add the missing
   entries to `permissions.allow` while preserving all existing entries.

2. [17-REQ-2.2] WHEN the init command merges entries, THE system SHALL NOT
   remove any existing entries from `permissions.allow`, even if they are not
   in the canonical list.

3. [17-REQ-2.3] WHEN the init command merges entries, THE system SHALL preserve
   the original ordering of existing entries and append new entries after them.

#### Edge Cases

1. [17-REQ-2.E1] IF `.claude/settings.local.json` exists but is not valid JSON,
   THEN THE system SHALL log a warning identifying the file and the parse error,
   and skip the settings update without failing the init command.

2. [17-REQ-2.E2] IF `.claude/settings.local.json` exists but has no
   `permissions` key or no `permissions.allow` key, THEN THE system SHALL
   create the missing structure and populate `permissions.allow` with the
   canonical entries, preserving any other top-level keys.

3. [17-REQ-2.E3] IF `.claude/settings.local.json` exists and `permissions.allow`
   is not a list, THEN THE system SHALL log a warning and skip the settings
   update without failing the init command.
