# Requirements Document

## Introduction

This document specifies the enhanced CLI output banner for agent-fox. The
banner displays the fox ASCII art mascot, version, active coding model, and
current working directory on every CLI invocation.

## Glossary

| Term | Definition |
|------|-----------|
| Banner | The styled text block displayed at CLI startup before any command output |
| Coding model | The AI model configured for code generation sessions (`models.coding` in config) |
| Model resolution | The process of converting a tier name (e.g., "ADVANCED") to a specific model ID (e.g., "claude-opus-4-6") |
| Header role | The theme color role used for prominent text (bold orange by default) |
| Fox art | The ASCII art depiction of the agent-fox mascot |

## Requirements

### Requirement 1: Fox ASCII Art Display

**User Story:** As a developer, I want to see the fox ASCII art mascot in the
CLI banner, so that the tool has a distinctive visual identity.

#### Acceptance Criteria

1. [14-REQ-1.1] THE banner SHALL display the following fox ASCII art:
   ```
      /\_/\  _
     / o.o \/ \
    ( > ^ < )  )
     \_^/\_/--'
   ```
2. [14-REQ-1.2] THE banner SHALL style the fox ASCII art using the theme's
   `header` color role.

#### Edge Cases

1. [14-REQ-1.E1] IF the theme's `header` style is invalid, THEN THE banner
   SHALL fall back to the default header style (existing theme fallback
   behavior via 01-REQ-7.E1).

---

### Requirement 2: Version and Model Display

**User Story:** As a developer, I want to see the version and active coding
model in the banner, so that I know which version and model are in use.

#### Acceptance Criteria

1. [14-REQ-2.1] THE banner SHALL display the version and resolved coding model
   on a single line in the format: `agent-fox v{version}  model: {model_id}`.
2. [14-REQ-2.2] THE banner SHALL resolve the coding model from the
   `models.coding` configuration field using the model registry.
3. [14-REQ-2.3] THE banner SHALL style the version/model line using the
   theme's `header` color role.

#### Edge Cases

1. [14-REQ-2.E1] IF the configured coding model cannot be resolved, THEN THE
   banner SHALL display the raw config value (e.g., `model: ADVANCED`) instead
   of the resolved model ID.

---

### Requirement 3: Working Directory Display

**User Story:** As a developer, I want to see the current working directory in
the banner, so that I can confirm which project agent-fox is operating on.

#### Acceptance Criteria

1. [14-REQ-3.1] THE banner SHALL display `Path.cwd()` on its own line below
   the version/model line.
2. [14-REQ-3.2] THE banner SHALL style the working directory line using the
   theme's `muted` color role.

#### Edge Cases

1. [14-REQ-3.E1] IF `Path.cwd()` raises an `OSError` (e.g., directory
   deleted), THEN THE banner SHALL display `(unknown)` as the working
   directory.

---

### Requirement 4: Banner Display Timing

**User Story:** As a developer, I want the banner to appear every time I run
agent-fox, so that I always have context about the tool's state.

#### Acceptance Criteria

1. [14-REQ-4.1] THE CLI SHALL display the banner on every invocation,
   including when a subcommand is specified.
2. [14-REQ-4.2] WHILE the `--quiet` flag is set, THE CLI SHALL suppress the
   banner entirely.

#### Edge Cases

1. [14-REQ-4.E1] IF the `--version` flag is used, THEN THE CLI SHALL display
   only the version string (existing Click behavior) and NOT the banner.
