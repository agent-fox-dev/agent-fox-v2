"""Night-shift ignore file loading and filtering.

Provides gitignore-style file exclusion for the night-shift hunt scan.
Loads patterns from .night-shift and .gitignore, combines them with
hardcoded default exclusions, and exposes a predicate and filter helper.

Requirements: 106-REQ-1.1, 106-REQ-1.2, 106-REQ-1.3, 106-REQ-1.4,
              106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-2.1, 106-REQ-2.E1,
              106-REQ-3.2, 106-REQ-3.3, 106-REQ-6.1, 106-REQ-6.2, 106-REQ-6.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

import pathspec

from agent_fox.nightshift.finding import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXCLUSIONS: list[str] = [
    ".agent-fox/**",
    ".git/**",
    "node_modules/**",
    "__pycache__/**",
    ".claude/**",
]

NIGHTSHIFT_IGNORE_FILENAME: str = ".night-shift"

NIGHTSHIFT_IGNORE_SEED: str = """\
# .night-shift — controls which files/folders the night-shift hunt scan skips.
# Syntax: same as .gitignore (one pattern per line, # for comments).
# These patterns are additive to .gitignore — both are applied.
#
# The following directories are always excluded by default:
# .agent-fox/**
# .git/**
# node_modules/**
# __pycache__/**
# .claude/**
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NightShiftIgnoreSpec:
    """Compiled ignore spec combining defaults, .gitignore, and .night-shift.

    Uses two compiled PathSpec objects:
    - ``defaults_spec``: only the hardcoded DEFAULT_EXCLUSIONS patterns.
      This is checked first and always wins, so user negation patterns cannot
      un-exclude default paths (see 106-REQ-2.E1).
    - ``spec``: the full combined patterns (defaults + .gitignore + .night-shift).

    Requirements: 106-REQ-2.E1, 106-REQ-6.3
    """

    spec: pathspec.PathSpec  # Combined spec (defaults + gitignore + nightshift)
    defaults_spec: pathspec.PathSpec  # Defaults-only spec (for guaranteed exclusion)

    def is_ignored(self, rel_path: str) -> bool:
        """Test whether a POSIX-relative path is ignored.

        Returns True if the path matches either the defaults spec (which
        cannot be overridden by user negation patterns) or the combined spec.

        Requirements: 106-REQ-2.E1, 106-REQ-6.2, 106-REQ-6.3
        """
        return self.defaults_spec.match_file(rel_path) or self.spec.match_file(rel_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compile_defaults() -> pathspec.PathSpec:
    """Compile a PathSpec from DEFAULT_EXCLUSIONS patterns only."""
    return pathspec.PathSpec.from_lines("gitignore", DEFAULT_EXCLUSIONS)


def _read_lines_safe(path: Path, label: str) -> list[str]:
    """Read lines from a file, logging a warning on failure.

    Returns an empty list on any error so callers can proceed with defaults.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception:
        logger.warning(
            "Failed to read %s at %s; its patterns will not be applied",
            label,
            path,
            exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_ignore_spec(project_root: Path) -> NightShiftIgnoreSpec:
    """Load and compile the combined ignore spec.

    Reads ``.night-shift`` and ``.gitignore`` from *project_root*, prepends
    ``DEFAULT_EXCLUSIONS``, and returns a compiled ``NightShiftIgnoreSpec``.

    Never raises — returns a defaults-only spec on any error (missing file,
    permission error, encoding error, empty file).

    Requirements: 106-REQ-1.1, 106-REQ-1.2, 106-REQ-1.3, 106-REQ-1.4,
                  106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-2.1, 106-REQ-3.3
    """
    defaults_spec = _compile_defaults()

    # Start with defaults; user patterns are appended after.
    all_patterns: list[str] = list(DEFAULT_EXCLUSIONS)

    # Load .gitignore patterns (additive with .night-shift, 106-REQ-3.3).
    gitignore_path = project_root / ".gitignore"
    if gitignore_path.is_file():
        all_patterns.extend(_read_lines_safe(gitignore_path, ".gitignore"))

    # Load .night-shift patterns (106-REQ-1.1, 106-REQ-1.2).
    nightshift_path = project_root / NIGHTSHIFT_IGNORE_FILENAME
    if nightshift_path.is_file():
        all_patterns.extend(_read_lines_safe(nightshift_path, NIGHTSHIFT_IGNORE_FILENAME))

    try:
        combined_spec = pathspec.PathSpec.from_lines("gitignore", all_patterns)
    except Exception:
        # If pattern compilation fails (e.g., an invalid gitignore pattern),
        # fall back gracefully to a defaults-only combined spec.
        logger.warning(
            "Failed to compile ignore patterns; falling back to default exclusions only",
            exc_info=True,
        )
        combined_spec = defaults_spec

    return NightShiftIgnoreSpec(spec=combined_spec, defaults_spec=defaults_spec)


def filter_findings(
    findings: list[Finding],
    spec: NightShiftIgnoreSpec,
) -> list[Finding]:
    """Filter findings by removing ignored ``affected_files`` entries.

    - Removes ignored paths from each finding's ``affected_files``.
    - Drops findings whose ``affected_files`` become empty after filtering.
    - Findings with no ``affected_files`` (empty list) are kept as-is.

    Requirements: 106-REQ-3.2
    """
    result: list[Finding] = []
    for finding in findings:
        if not finding.affected_files:
            # Findings with no files are always preserved (106-REQ-3.2).
            result.append(finding)
            continue

        kept_files = [f for f in finding.affected_files if not spec.is_ignored(f)]
        if kept_files:
            # Create a new frozen Finding with only the non-ignored files.
            result.append(replace(finding, affected_files=kept_files))
        # If all files were ignored, drop this finding entirely.

    return result
