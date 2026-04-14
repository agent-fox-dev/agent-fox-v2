"""Archetype profile loading for 3-layer prompt assembly.

Profiles are markdown files that define archetype behavioral guidance
(identity, rules, focus areas, output format). They are loaded from:
  1. Project-level: <project_dir>/.agent-fox/profiles/<archetype>.md
  2. Package default: agent_fox/_templates/profiles/<archetype>.md

Requirements: 99-REQ-5.1, 99-REQ-5.2, 99-REQ-5.3, 99-REQ-5.E1,
              99-REQ-1.E2, 99-REQ-4.1
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Profile directory in the package (package-relative resolution, mirrors
# the pattern used in session/prompt.py for _TEMPLATE_DIR).
_DEFAULT_PROFILES_DIR: Path = Path(__file__).resolve().parent.parent / "_templates" / "profiles"

# Regex to match YAML frontmatter at the very start of a file.
# Replicates the pattern from session/prompt.py to avoid cross-module coupling.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter block from profile content.

    Removes the leading ``---`` … ``---`` block if present.
    Returns content unchanged when no frontmatter is found.

    Requirement: 99-REQ-5.3
    """
    return _FRONTMATTER_RE.sub("", content, count=1)


def load_profile(
    archetype: str,
    project_dir: Path | None = None,
) -> str:
    """Load an archetype profile, checking project dir then package default.

    Resolution order:
    1. ``<project_dir>/.agent-fox/profiles/<archetype>.md`` (when *project_dir*
       is provided and the file exists).
    2. Package-embedded default profile from ``_templates/profiles/``.

    The returned content has YAML frontmatter stripped.  Returns an empty
    string and logs a WARNING if no profile is found in either location.

    Args:
        archetype: Archetype name (e.g. ``"coder"``, ``"reviewer"``).
        project_dir: Root of the project directory.  Pass ``None`` to use only
            the package default (useful when no project is open).

    Returns:
        Profile content as a plain string (frontmatter removed).

    Requirements: 99-REQ-5.1, 99-REQ-5.2, 99-REQ-5.3, 99-REQ-5.E1,
                  99-REQ-1.E2
    """
    # --- Layer 1: project-level profile ---
    if project_dir is not None:
        project_profile = project_dir / ".agent-fox" / "profiles" / f"{archetype}.md"
        if project_profile.exists():
            logger.debug(
                "Loading profile for %r from project: %s",
                archetype,
                project_profile,
            )
            content = project_profile.read_text(encoding="utf-8")
            return _strip_frontmatter(content)

    # --- Layer 2: package-embedded default ---
    default_profile = _DEFAULT_PROFILES_DIR / f"{archetype}.md"
    if default_profile.exists():
        logger.debug(
            "Loading default profile for %r from package: %s",
            archetype,
            default_profile,
        )
        content = default_profile.read_text(encoding="utf-8")
        return _strip_frontmatter(content)

    # --- No profile found ---
    logger.warning(
        "No profile found for archetype %r (checked project dir and package defaults). Using empty profile.",
        archetype,
    )
    return ""


def has_custom_profile(name: str, project_dir: Path) -> bool:
    """Return True if a custom profile exists in the project for *name*.

    A custom profile is any file at
    ``<project_dir>/.agent-fox/profiles/<name>.md``, regardless of whether
    *name* is a built-in archetype.

    Requirement: 99-REQ-4.1
    """
    profile_path = project_dir / ".agent-fox" / "profiles" / f"{name}.md"
    return profile_path.exists()
