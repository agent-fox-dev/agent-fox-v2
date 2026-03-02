"""Prompt builder: construct system and task prompts for coding sessions.

Loads rich templates from agent_fox/_templates/prompts/ with placeholder
interpolation and frontmatter stripping.

Requirements: 03-REQ-5.1, 03-REQ-5.2,
              15-REQ-2.1 through 15-REQ-5.E1
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.core.errors import ConfigError

# ---------------------------------------------------------------------------
# 3.1 — Template loading and frontmatter stripping
# Requirements: 15-REQ-2.1, 15-REQ-4.1, 15-REQ-4.2, 15-REQ-2.E1
# ---------------------------------------------------------------------------

# Template directory relative to this file (package-relative resolution)
_TEMPLATE_DIR: Path = (
    Path(__file__).resolve().parent.parent / "_templates" / "prompts"
)

# Role-to-template mapping
_ROLE_TEMPLATES: dict[str, list[str]] = {
    "coding": ["coding.md", "git-flow.md"],
    "coordinator": ["coordinator.md"],
}

# Regex to match YAML frontmatter at the very start of a file
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter from template content.

    Removes content between leading ``---`` delimiters.
    Returns content unchanged if no frontmatter is present.

    Requirement: 15-REQ-4.1, 15-REQ-4.2
    """
    return _FRONTMATTER_RE.sub("", content, count=1)


def _load_template(name: str) -> str:
    """Load a template file from the templates directory.

    Strips frontmatter and returns the template content.

    Raises:
        ConfigError: If the template file does not exist.

    Requirement: 15-REQ-2.1, 15-REQ-2.E1
    """
    path = _TEMPLATE_DIR / name
    if not path.exists():
        raise ConfigError(
            f"Template file not found: {path}",
            template_name=name,
            template_dir=str(_TEMPLATE_DIR),
        )
    content = path.read_text(encoding="utf-8")
    return _strip_frontmatter(content)


# ---------------------------------------------------------------------------
# 3.2 — Placeholder interpolation
# Requirements: 15-REQ-3.1, 15-REQ-3.2, 15-REQ-3.E1
# ---------------------------------------------------------------------------

# Only replace these known placeholders — leave everything else untouched.
_KNOWN_KEYS = ("spec_name", "task_group", "number", "specification")

# Pattern: match {key} for each known key only
_INTERPOLATION_RE = re.compile(
    r"\{(" + "|".join(re.escape(k) for k in _KNOWN_KEYS) + r")\}"
)


def _interpolate(template: str, variables: dict[str, str]) -> str:
    """Interpolate known placeholders in template content.

    Uses regex replacement targeting only known keys so that literal
    braces (e.g. in JSON examples) are preserved without error.

    Requirement: 15-REQ-3.1, 15-REQ-3.2, 15-REQ-3.E1
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return _INTERPOLATION_RE.sub(_replace, template)


# ---------------------------------------------------------------------------
# 3.3 — build_system_prompt rewrite
# Requirements: 15-REQ-2.2 through 15-REQ-2.E2
# ---------------------------------------------------------------------------


def build_system_prompt(
    context: str,
    task_group: int,
    spec_name: str,
    role: str = "coding",
) -> str:
    """Build the system prompt from templates and context.

    Args:
        context: Assembled spec documents and memory facts.
        task_group: The target task group number.
        spec_name: The specification name (e.g. ``03_session_and_workspace``).
        role: Prompt role — ``"coding"`` or ``"coordinator"``.

    Returns:
        Complete system prompt string.

    Raises:
        ValueError: If *role* is not recognized.
        ConfigError: If a template file is missing.

    Requirement: 15-REQ-2.2, 15-REQ-2.3, 15-REQ-2.4, 15-REQ-2.5, 15-REQ-2.E2
    """
    if role not in _ROLE_TEMPLATES:
        valid = ", ".join(sorted(_ROLE_TEMPLATES))
        raise ValueError(
            f"Unknown prompt role {role!r}. Valid roles: {valid}"
        )

    # Derive number and specification from spec_name (e.g. "03_session")
    parts = spec_name.split("_", 1)
    number = parts[0] if len(parts) > 1 else spec_name
    specification = parts[1] if len(parts) > 1 else spec_name

    variables: dict[str, str] = {
        "spec_name": spec_name,
        "task_group": str(task_group),
        "number": number,
        "specification": specification,
    }

    # Load and compose templates for the role
    template_names = _ROLE_TEMPLATES[role]
    sections: list[str] = []
    for name in template_names:
        raw = _load_template(name)
        interpolated = _interpolate(raw, variables)
        sections.append(interpolated)

    # Join template sections, then append context
    composed = "\n\n".join(sections)

    return f"{composed}\n\n## Context\n\n{context}\n"


# ---------------------------------------------------------------------------
# 3.4 — build_task_prompt rewrite
# Requirements: 15-REQ-5.1 through 15-REQ-5.E1
# ---------------------------------------------------------------------------


def build_task_prompt(
    task_group: int,
    spec_name: str,
) -> str:
    """Build an enriched task prompt.

    Includes spec name, task group, instructions to update checkbox states,
    commit on the feature branch, and run quality gates.

    Raises:
        ValueError: If *task_group* < 1.

    Requirement: 15-REQ-5.1, 15-REQ-5.2, 15-REQ-5.3, 15-REQ-5.E1
    """
    if task_group < 1:
        raise ValueError(
            f"task_group must be >= 1, got {task_group}"
        )

    return (
        f"Implement task group {task_group} from specification "
        f"`{spec_name}`.\n"
        f"\n"
        f"Refer to the tasks.md subtask list in the context above for the "
        f"detailed breakdown of work items. Complete all subtasks in group "
        f"{task_group}.\n"
        f"\n"
        f"When you finish each subtask, update the checkbox state in "
        f"tasks.md (change `- [ ]` to `- [x]` for completed items).\n"
        f"\n"
        f"After implementation, commit your changes on the current feature "
        f"branch with a conventional commit message.\n"
        f"\n"
        f"Before committing, run the relevant test suite and linter to "
        f"ensure quality gates pass. Fix any failures before finalizing "
        f"the commit.\n"
    )
