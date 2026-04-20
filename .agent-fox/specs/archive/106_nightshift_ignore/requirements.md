# Requirements Document

## Introduction

This specification defines the `.night-shift` ignore file — a user-controlled
exclusion mechanism for the `night-shift` command's hunt scan. The file uses
`.gitignore` syntax and semantics to let users specify files and directories
that should not be inspected during hunt scans.

## Glossary

- **Hunt scan:** The periodic code-quality scan performed by the `night-shift`
  command. Runs all enabled hunt categories (todo_fixme, dead_code, etc.) in
  parallel against the repository.
- **Hunt category:** A pluggable detection module (e.g., `TodoFixmeCategory`,
  `DeadCodeCategory`) that produces `Finding` objects during a hunt scan.
- **`.night-shift` file:** A gitignore-syntax file in the repository root that
  specifies additional paths to exclude from hunt scans.
- **Default exclusions:** A hardcoded set of glob patterns (e.g.,
  `.agent-fox/**`, `.git/**`) that are always excluded from hunt scans,
  regardless of whether a `.night-shift` file exists.
- **pathspec:** A Python library that implements `.gitignore`-style pattern
  matching (gitwildmatch).
- **Ignore spec:** A compiled `pathspec.PathSpec` object that can test whether
  a given relative path matches any of its patterns.

## Requirements

### Requirement 1: Load and parse the `.night-shift` file

**User Story:** As a developer using night-shift, I want to specify files and
directories to exclude from hunt scans, so that irrelevant findings (generated
code, vendored deps, data files) don't clutter the results.

#### Acceptance Criteria

[106-REQ-1.1] WHEN the hunt scan starts, THE system SHALL look for a
`.night-shift` file in the repository root directory.

[106-REQ-1.2] WHEN a `.night-shift` file exists, THE system SHALL parse it
using `pathspec.PathSpec.from_lines("gitwildmatch", ...)` and return a compiled
ignore spec.

[106-REQ-1.3] THE system SHALL treat blank lines and lines starting with `#`
as comments, consistent with `.gitignore` semantics.

[106-REQ-1.4] WHEN no `.night-shift` file exists, THE system SHALL return an
ignore spec containing only the default exclusion patterns.

#### Edge Cases

[106-REQ-1.E1] IF the `.night-shift` file cannot be read (permission error,
encoding error), THEN THE system SHALL log a warning and return an ignore spec
containing only the default exclusion patterns.

[106-REQ-1.E2] IF the `.night-shift` file is empty (no non-comment lines),
THEN THE system SHALL return an ignore spec containing only the default
exclusion patterns.

### Requirement 2: Default exclusions

**User Story:** As a night-shift user, I want agent-fox internal directories
and common non-source directories automatically excluded, so I don't have to
list them in every project.

#### Acceptance Criteria

[106-REQ-2.1] THE system SHALL always exclude paths matching the following
patterns, regardless of `.night-shift` file content:
`.agent-fox/**`, `.git/**`, `node_modules/**`, `__pycache__/**`, `.claude/**`.

[106-REQ-2.2] THE system SHALL prepend the default exclusion patterns to any
user-supplied patterns before compiling the ignore spec, so that default
exclusions cannot be overridden by negation patterns in `.night-shift`.

#### Edge Cases

[106-REQ-2.E1] IF a user adds a negation pattern (e.g., `!.agent-fox/config.toml`)
to `.night-shift`, THEN THE system SHALL still exclude the path because default
exclusions are prepended and `pathspec` processes patterns in order (last match
wins — but the user patterns are appended after defaults, so a negation
*could* un-exclude). To guarantee defaults, the system SHALL apply default
patterns as a separate check that always wins.

### Requirement 3: Integrate with hunt scan

**User Story:** As a night-shift user, I want the hunt scan to respect my
`.night-shift` exclusions, so that findings from excluded paths are not
reported.

#### Acceptance Criteria

[106-REQ-3.1] WHEN the `HuntScanner.run()` method is called, THE system SHALL
load the ignore spec from the project root and pass it to each hunt category's
`detect()` method.

[106-REQ-3.2] WHEN a hunt category produces findings, THE system SHALL filter
out any `Finding` whose `affected_files` entries all match the ignore spec,
and remove matching entries from findings that have a mix of ignored and
non-ignored files.

[106-REQ-3.3] THE system SHALL apply the ignore spec additively with
`.gitignore` — a file excluded by either is excluded from the hunt scan.

#### Edge Cases

[106-REQ-3.E1] IF loading the ignore spec fails entirely (e.g., `pathspec`
import fails despite being a dependency), THEN THE system SHALL log a warning
and proceed with the hunt scan without any `.night-shift` filtering.

### Requirement 4: Init command creates `.night-shift`

**User Story:** As a developer setting up a new project, I want `agent-fox init`
to create a `.night-shift` file with sensible defaults, so I have a starting
point for customization.

#### Acceptance Criteria

[106-REQ-4.1] WHEN `agent-fox init` runs, THE system SHALL create a
`.night-shift` file in the project root if one does not already exist.

[106-REQ-4.2] THE created `.night-shift` file SHALL contain a comment header
explaining its purpose, followed by the default exclusion patterns as
commented-out entries for user reference.

[106-REQ-4.3] THE system SHALL report the creation of the `.night-shift` file
in the init command output (text mode: `"Created .night-shift."`, JSON mode:
`"night_shift_ignore": "created"`).

[106-REQ-4.4] THE `init_project()` function SHALL return the `.night-shift`
creation status in `InitResult` AND the CLI handler SHALL use that status to
produce output.

#### Edge Cases

[106-REQ-4.E1] IF a `.night-shift` file already exists, THEN THE system SHALL
skip creation and not modify the existing file.

[106-REQ-4.E2] IF the file cannot be created (permission error), THEN THE
system SHALL log a warning and continue initialization without failing.

### Requirement 5: `pathspec` as a required dependency

**User Story:** As a maintainer, I want `pathspec` to be a required dependency
so that `.night-shift` pattern matching is always available.

#### Acceptance Criteria

[106-REQ-5.1] THE project SHALL list `pathspec>=0.12` in the `[project]
dependencies` section of `pyproject.toml`.

### Requirement 6: Path matching semantics

**User Story:** As a developer, I want `.night-shift` to use familiar
`.gitignore` semantics so I don't have to learn a new syntax.

#### Acceptance Criteria

[106-REQ-6.1] THE system SHALL match paths using the gitwildmatch pattern
style, supporting: wildcards (`*`, `?`), directory separators (`/`),
double-star (`**`) for recursive matching, negation (`!`), and
character classes (`[abc]`).

[106-REQ-6.2] THE system SHALL match patterns against paths relative to the
repository root, using POSIX separators (`/`).

[106-REQ-6.3] WHEN testing a file path against the ignore spec, THE system
SHALL return a boolean indicating whether the path is ignored AND the
function SHALL be usable as a predicate for filtering file lists.
