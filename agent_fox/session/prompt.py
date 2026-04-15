"""Prompt building: system prompt assembly and task prompt construction.

Assembles a 3-layer system prompt from project context (CLAUDE.md),
archetype profile, and task context.

Requirements: 15-REQ-2.2, 15-REQ-5.1 through 15-REQ-5.E1,
              99-REQ-1.1, 99-REQ-1.E1, 99-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path

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
# build_system_prompt
# Requirements: 15-REQ-2.2 through 15-REQ-2.E2, 99-REQ-1.1
# ---------------------------------------------------------------------------


def build_system_prompt(
    context: str,
    task_group: int = 0,
    spec_name: str = "",
    archetype: str | None = None,
    mode: str | None = None,
    project_dir: Path | None = None,
) -> str:
    """Build the system prompt using 3-layer assembly.

    Assembles a prompt from:
      - Layer 1: Project context from ``CLAUDE.md`` (omitted if missing or
        *project_dir* is ``None``).
      - Layer 2: Archetype profile loaded via :func:`load_profile`, with
        mode-aware resolution.
      - Layer 3: Task context (the *context* argument).

    Args:
        context: Assembled spec documents and memory facts (task context).
        task_group: The target task group number (retained for API compat).
        spec_name: The specification name (retained for API compat).
        archetype: Archetype name for profile resolution.  Defaults to
            ``"coder"`` when ``None``.
        mode: Optional archetype mode variant for mode-specific profile
            resolution (e.g. ``"fix"`` loads ``coder_fix.md``).
        project_dir: Root of the project directory.  When provided, enables
            Layer 1 (CLAUDE.md) and project-level profile overrides.

    Returns:
        Complete system prompt string.

    Requirement: 15-REQ-2.2, 99-REQ-1.1, 99-REQ-1.E1, 99-REQ-1.E2
    """
    resolved = archetype if archetype is not None else "coder"

    layers: list[str] = []

    # Layer 1: project context (CLAUDE.md) — omit if missing (99-REQ-1.E1)
    if project_dir is not None:
        claude_md = project_dir / "CLAUDE.md"
        if claude_md.exists():
            layers.append(claude_md.read_text(encoding="utf-8"))

    # Layer 2: archetype profile — empty string if not found (99-REQ-1.E2)
    profile = load_profile(resolved, project_dir=project_dir, mode=mode)
    if profile:
        layers.append(profile)

    # Layer 3: task context
    layers.append(f"## Context\n\n{context}\n")

    return "\n\n".join(layers)


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
    prompt that defers to the system prompt profile for detailed
    instructions.

    Args:
        task_group: The target task group number.
        spec_name: The specification name.
        archetype: Archetype name (defaults to ``"coder"``).
        mode: Optional archetype mode variant (97-REQ-5.3). Used for
            mode-specific profile resolution.

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
