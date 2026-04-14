"""Prompt building: template loading, interpolation, system/task prompts.

Loads rich templates from agent_fox/_templates/prompts/ with placeholder
interpolation and frontmatter stripping.

Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.E1, 15-REQ-2.1 through
              15-REQ-5.E1, 99-REQ-1.1, 99-REQ-1.E1, 99-REQ-1.E2
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.core.errors import ConfigError

# Re-export symbols that external code imports from this module.
# These were extracted to session/steering.py and session/context.py
# but many call-sites still reference them via session.prompt.
from agent_fox.session.context import (  # noqa: F401
    PriorFinding,
    assemble_context,
    get_prior_group_findings,
    render_drift_context,
    render_prior_group_findings,
    render_review_context,
    render_verification_context,
    select_context_with_causal,
)
from agent_fox.session.profiles import load_profile
from agent_fox.session.steering import (  # noqa: F401
    STEERING_PLACEHOLDER_SENTINEL,
    load_steering,
)

# ---------------------------------------------------------------------------
# Template loading and frontmatter stripping
# Requirements: 15-REQ-2.1, 15-REQ-4.1, 15-REQ-4.2, 15-REQ-2.E1
# ---------------------------------------------------------------------------

# Template directory relative to this file (package-relative resolution)
_TEMPLATE_DIR: Path = Path(__file__).resolve().parent.parent / "_templates" / "prompts"

# Legacy role-to-archetype mapping (backward compatibility)
_ROLE_TO_ARCHETYPE: dict[str, str] = {
    "coding": "coder",
    "reviewer": "reviewer",
    "verifier": "verifier",
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
# Placeholder interpolation
# Requirements: 15-REQ-3.1, 15-REQ-3.2, 15-REQ-3.E1
# ---------------------------------------------------------------------------

# Only replace these known placeholders — leave everything else untouched.
_KNOWN_KEYS = ("spec_name", "task_group", "number", "specification")

# Pattern: match {key} for each known key only
_INTERPOLATION_RE = re.compile(r"\{(" + "|".join(re.escape(k) for k in _KNOWN_KEYS) + r")\}")


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
# build_system_prompt
# Requirements: 15-REQ-2.2 through 15-REQ-2.E2
# ---------------------------------------------------------------------------


def build_system_prompt(
    context: str,
    task_group: int = 0,
    spec_name: str = "",
    role: str | None = None,
    archetype: str | None = None,
    mode: str | None = None,
    project_dir: Path | None = None,
) -> str:
    """Build the system prompt from templates and context.

    When *project_dir* is provided, assembles a 3-layer prompt:
      - Layer 1: Project context from ``CLAUDE.md`` (omitted if missing).
      - Layer 2: Archetype profile loaded via :func:`load_profile`.
      - Layer 3: Task context (the *context* argument).

    When *project_dir* is ``None``, falls back to the legacy template-based
    approach for backward compatibility.

    Args:
        context: Assembled spec documents and memory facts (task context).
        task_group: The target task group number.
        spec_name: The specification name (e.g. ``03_session_and_workspace``).
        role: **Deprecated.** Legacy prompt role (e.g. ``"coding"``).
            Mapped to archetype internally.
        archetype: Archetype name for template resolution via registry.
            Takes precedence over *role* when both are provided.
        mode: Optional archetype mode variant (97-REQ-5.3). Reserved for
            future per-mode template resolution (spec 98).
        project_dir: Root of the project directory.  When provided, enables
            3-layer prompt assembly (99-REQ-1.1).  Pass ``None`` to use the
            legacy template-based assembly.

    Returns:
        Complete system prompt string.

    Raises:
        ValueError: If neither *role* nor *archetype* resolves to a valid
            archetype entry.
        ConfigError: If a template file is missing (legacy path only).

    Requirement: 15-REQ-2.2, 15-REQ-2.3, 15-REQ-2.4, 15-REQ-2.5, 15-REQ-2.E2,
                 26-REQ-3.5, 99-REQ-1.1, 99-REQ-1.E1, 99-REQ-1.E2
    """
    from agent_fox.session.archetypes import get_archetype

    # Resolve archetype name: archetype param > role param > default "coder"
    resolved: str
    if archetype is not None:
        resolved = archetype
    elif role is not None:
        mapped = _ROLE_TO_ARCHETYPE.get(role)
        if mapped is None:
            valid = ", ".join(sorted(_ROLE_TO_ARCHETYPE))
            raise ValueError(f"Unknown prompt role {role!r}. Valid roles: {valid}")
        resolved = mapped
    else:
        resolved = "coder"

    # --- 3-layer assembly when project_dir is provided ---
    # Requirements: 99-REQ-1.1, 99-REQ-1.E1, 99-REQ-1.E2
    if project_dir is not None:
        layers: list[str] = []

        # Layer 1: project context (CLAUDE.md) — omit if missing (99-REQ-1.E1)
        claude_md = project_dir / "CLAUDE.md"
        if claude_md.exists():
            layers.append(claude_md.read_text(encoding="utf-8"))

        # Layer 2: archetype profile — empty string if not found (99-REQ-1.E2)
        profile = load_profile(resolved, project_dir=project_dir)
        if profile:
            layers.append(profile)

        # Layer 3: task context
        layers.append(f"## Context\n\n{context}\n")

        return "\n\n".join(layers)

    # --- Legacy template-based assembly (no project_dir) ---
    entry = get_archetype(resolved)

    # Apply mode-specific overrides (98-REQ-3.2, 98-REQ-2.2)
    from agent_fox.archetypes import resolve_effective_config

    effective_entry = resolve_effective_config(entry, mode)

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

    # Load and compose templates from the effective (mode-resolved) archetype config
    template_names = effective_entry.templates
    sections: list[str] = []
    for name in template_names:
        raw = _load_template(name)
        interpolated = _interpolate(raw, variables)
        sections.append(interpolated)

    # Join template sections, then append context
    composed = "\n\n".join(sections)

    return f"{composed}\n\n## Context\n\n{context}\n"


# ---------------------------------------------------------------------------
# build_task_prompt
# Requirements: 15-REQ-5.1 through 15-REQ-5.E1
# ---------------------------------------------------------------------------


def build_task_prompt(
    task_group: int,
    spec_name: str,
    archetype: str = "coder",
    mode: str | None = None,
) -> str:
    """Build an enriched task prompt.

    For coder archetypes: includes spec name, task group, instructions to
    update checkbox states, commit on the feature branch, and run quality
    gates.

    For non-coder archetypes (skeptic, verifier, etc.): returns a concise
    prompt that defers to the system prompt template for detailed
    instructions.

    Args:
        task_group: The target task group number.
        spec_name: The specification name.
        archetype: Archetype name (defaults to ``"coder"``).
        mode: Optional archetype mode variant (97-REQ-5.3). Reserved for
            future per-mode prompt customisation (spec 98).

    Raises:
        ValueError: If *task_group* < 1 for coder archetype.

    Requirement: 15-REQ-5.1, 15-REQ-5.2, 15-REQ-5.3, 15-REQ-5.E1
    """
    if archetype != "coder":
        return (
            f"Execute your {archetype} role for specification "
            f"`{spec_name}`. Follow the instructions in the system prompt.\n"
        )

    if task_group < 1:
        raise ValueError(f"task_group must be >= 1, got {task_group}")

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
