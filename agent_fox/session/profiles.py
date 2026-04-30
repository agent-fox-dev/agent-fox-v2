"""Archetype profile loading for 3-layer prompt assembly.

Profiles are markdown files that define archetype behavioral guidance
(identity, rules, focus areas, output format). They are loaded from:
  1. Project-level: <project_dir>/.agent-fox/profiles/<archetype>_<mode>.md
  2. Package default: agent_fox/_templates/profiles/<archetype>_<mode>.md
  3. Project-level: <project_dir>/.agent-fox/profiles/<archetype>.md
  4. Package default: agent_fox/_templates/profiles/<archetype>.md

Requirements: 99-REQ-5.1, 99-REQ-5.2, 99-REQ-5.3, 99-REQ-5.E1,
              99-REQ-1.E2, 99-REQ-4.1
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Profile directory in the package (package-relative resolution).
_DEFAULT_PROFILES_DIR: Path = Path(__file__).resolve().parent.parent / "_templates" / "profiles"

# Regex to match YAML frontmatter at the very start of a file.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

# Regex that allowlists safe profile name characters (alphanumeric, hyphens, underscores).
# Rejects path separators, dots, and other characters that could enable path traversal.
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_profile_name(name: str, param: str) -> None:
    """Raise ValueError if *name* contains characters unsafe for filesystem paths.

    Accepts only alphanumeric characters, hyphens, and underscores.  Rejects
    anything else (dots, slashes, etc.) to prevent CWE-22 path traversal.

    Args:
        name: The value to validate.
        param: The parameter name used in the error message.

    Raises:
        ValueError: If *name* contains unsafe characters.
    """
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid {param}: {name!r}")


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
    mode: str | None = None,
) -> str:
    """Load an archetype profile, with mode-aware resolution.

    Resolution order (first match wins):
    1. ``<project_dir>/.agent-fox/profiles/<archetype>_<mode>.md``
    2. ``_templates/profiles/<archetype>_<mode>.md``
    3. ``<project_dir>/.agent-fox/profiles/<archetype>.md``
    4. ``_templates/profiles/<archetype>.md``

    Steps 1-2 are skipped when *mode* is ``None``.
    Steps 1 and 3 are skipped when *project_dir* is ``None``.

    The returned content has YAML frontmatter stripped.  Returns an empty
    string and logs a WARNING if no profile is found in any location.

    Args:
        archetype: Archetype name (e.g. ``"coder"``, ``"reviewer"``).
        project_dir: Root of the project directory.  Pass ``None`` to use only
            the package default (useful when no project is open).
        mode: Optional mode variant (e.g. ``"fix"``).  When provided,
            mode-specific profiles are checked before the base profile.

    Returns:
        Profile content as a plain string (frontmatter removed).

    Requirements: 99-REQ-5.1, 99-REQ-5.2, 99-REQ-5.3, 99-REQ-5.E1,
                  99-REQ-1.E2
    """
    # Validate inputs before constructing any filesystem paths (CWE-22).
    _validate_profile_name(archetype, "archetype")
    if mode is not None:
        _validate_profile_name(mode, "mode")

    # Build candidate filenames in priority order.
    candidates: list[Path] = []

    if mode is not None:
        mode_filename = f"{archetype}_{mode}.md"
        # Priority 1: project-level mode-specific profile
        if project_dir is not None:
            candidates.append(project_dir / ".agent-fox" / "profiles" / mode_filename)
        # Priority 2: package-embedded mode-specific profile
        candidates.append(_DEFAULT_PROFILES_DIR / mode_filename)

    base_filename = f"{archetype}.md"
    # Priority 3: project-level base profile
    if project_dir is not None:
        candidates.append(project_dir / ".agent-fox" / "profiles" / base_filename)
    # Priority 4: package-embedded base profile
    candidates.append(_DEFAULT_PROFILES_DIR / base_filename)

    for candidate in candidates:
        # Security: reject symlinks to prevent content injection (CWE-59)
        if candidate.is_symlink():
            logger.warning("Skipping symlink profile candidate: %s", candidate)
            continue
        if candidate.exists():
            logger.debug(
                "Loading profile for %r (mode=%r) from: %s",
                archetype,
                mode,
                candidate,
            )
            content = candidate.read_text(encoding="utf-8")
            return _strip_frontmatter(content)

    # --- No profile found ---
    logger.warning(
        "No profile found for archetype %r (mode=%r). Using empty profile.",
        archetype,
        mode,
    )
    return ""


def has_custom_profile(name: str, project_dir: Path) -> bool:
    """Return True if a custom profile exists in the project for *name*.

    A custom profile is any file at
    ``<project_dir>/.agent-fox/profiles/<name>.md``, regardless of whether
    *name* is a built-in archetype.

    Requirement: 99-REQ-4.1
    """
    # Validate before constructing any filesystem path (CWE-22).
    _validate_profile_name(name, "name")
    profile_path = project_dir / ".agent-fox" / "profiles" / f"{name}.md"
    return profile_path.exists()
