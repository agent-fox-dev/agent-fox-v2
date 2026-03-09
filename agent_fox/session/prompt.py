"""Session preparation: context assembly and prompt building.

Gathers spec documents and memory facts for session context, loads
rich templates from agent_fox/_templates/prompts/ with placeholder
interpolation and frontmatter stripping.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 03-REQ-5.1, 03-REQ-5.2,
              13-REQ-7.1, 13-REQ-7.2, 15-REQ-1.1, 15-REQ-1.2,
              15-REQ-1.E1, 15-REQ-2.1 through 15-REQ-5.E1
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import duckdb  # noqa: F401

from agent_fox.core.errors import ConfigError
from agent_fox.knowledge.causal import traverse_causal_chain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context assembly (merged from context.py)
# ---------------------------------------------------------------------------

# Spec files to read, in order, with their section headers.
_SPEC_FILES: list[tuple[str, str]] = [
    ("requirements.md", "## Requirements"),
    ("design.md", "## Design"),
    ("test_spec.md", "## Test Specification"),
    ("tasks.md", "## Tasks"),
]


def assemble_context(
    spec_dir: Path,
    task_group: int,
    memory_facts: list[str] | None = None,
) -> str:
    """Assemble task-specific context for a coding session.

    Reads the following files from spec_dir (if they exist):
    - requirements.md
    - design.md
    - test_spec.md
    - tasks.md

    Appends relevant memory facts (if provided).

    Returns a formatted string with section headers.

    Logs a warning for any missing spec file but does not raise.
    """
    sections: list[str] = []

    # 03-REQ-4.1: Read spec documents
    for filename, header in _SPEC_FILES:
        filepath = spec_dir / filename
        if not filepath.exists():
            # 03-REQ-4.E1: Skip missing files with a warning
            logger.warning(
                "Spec file '%s' not found in %s, skipping",
                filename,
                spec_dir,
            )
            continue
        content = filepath.read_text(encoding="utf-8")
        sections.append(f"{header}\n\n{content}")

    # 03-REQ-4.2: Include memory facts
    if memory_facts:
        facts_text = "\n".join(f"- {fact}" for fact in memory_facts)
        sections.append(f"## Memory Facts\n\n{facts_text}")

    # 03-REQ-4.3: Return formatted string with section headers
    return "\n\n---\n\n".join(sections)


def select_context_with_causal(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    touched_files: list[str],
    *,
    keyword_facts: list[dict],
    max_facts: int = 50,
    causal_budget: int = 10,
) -> list[dict]:
    """Select session context facts with causal enhancement.

    1. Start with keyword_facts from the existing selection (REQ-061).
    2. For each keyword fact, query the causal graph for linked facts.
    3. Also query for facts causally linked to the current spec_name.
    4. Deduplicate and rank: keyword matches first, then causal links
       ordered by proximity (depth).
    5. Trim to max_facts total.

    The causal_budget controls how many of the max_facts slots are
    reserved for causally-linked facts (default: 10 of 50).
    """
    # 1. Start with keyword facts, trimmed to fit within max_facts
    keyword_budget = max_facts - causal_budget
    if keyword_budget < 0:
        keyword_budget = 0
    selected_keywords = keyword_facts[:keyword_budget]

    # Track seen IDs for deduplication
    seen_ids: set[str] = {f["id"] for f in selected_keywords}
    result: list[dict] = list(selected_keywords)

    # 2. For each keyword fact, traverse causal graph for linked facts
    causal_candidates: list[tuple[int, dict]] = []  # (abs_depth, fact_dict)
    for kw_fact in selected_keywords:
        fact_id = kw_fact["id"]
        try:
            chain = traverse_causal_chain(conn, fact_id, max_depth=3)
        except Exception:
            logger.debug("Failed to traverse causal chain for fact %s", fact_id)
            continue
        for cf in chain:
            if cf.fact_id not in seen_ids:
                causal_candidates.append(
                    (
                        abs(cf.depth),
                        {
                            "id": cf.fact_id,
                            "content": cf.content,
                            "spec_name": cf.spec_name,
                            "session_id": cf.session_id,
                            "commit_sha": cf.commit_sha,
                        },
                    )
                )

    # 3. Also query for facts linked to the current spec_name
    try:
        rows = conn.execute(
            "SELECT CAST(id AS VARCHAR), content, spec_name, session_id, "
            "commit_sha FROM memory_facts WHERE spec_name = ?",
            [spec_name],
        ).fetchall()
        for row in rows:
            fid = row[0]
            if fid not in seen_ids:
                try:
                    chain = traverse_causal_chain(conn, fid, max_depth=2)
                except Exception:
                    continue
                for cf in chain:
                    if cf.fact_id not in seen_ids:
                        causal_candidates.append(
                            (
                                abs(cf.depth),
                                {
                                    "id": cf.fact_id,
                                    "content": cf.content,
                                    "spec_name": cf.spec_name,
                                    "session_id": cf.session_id,
                                    "commit_sha": cf.commit_sha,
                                },
                            )
                        )
    except Exception:
        logger.debug("Failed to query facts for spec_name %s", spec_name)

    # 4. Deduplicate and rank causal candidates by proximity (depth)
    causal_candidates.sort(key=lambda x: x[0])

    # 5. Add causal facts up to the budget and max_facts limit
    remaining_budget = min(causal_budget, max_facts - len(result))
    for _depth, fact_dict in causal_candidates:
        if remaining_budget <= 0:
            break
        if fact_dict["id"] not in seen_ids:
            seen_ids.add(fact_dict["id"])
            result.append(fact_dict)
            remaining_budget -= 1

    # Final trim to ensure budget compliance
    return result[:max_facts]

# ---------------------------------------------------------------------------
# 3.1 — Template loading and frontmatter stripping
# Requirements: 15-REQ-2.1, 15-REQ-4.1, 15-REQ-4.2, 15-REQ-2.E1
# ---------------------------------------------------------------------------

# Template directory relative to this file (package-relative resolution)
_TEMPLATE_DIR: Path = Path(__file__).resolve().parent.parent / "_templates" / "prompts"

# Legacy role-to-archetype mapping (backward compatibility)
_ROLE_TO_ARCHETYPE: dict[str, str] = {
    "coding": "coder",
    "coordinator": "coordinator",
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
    role: str | None = None,
    archetype: str | None = None,
) -> str:
    """Build the system prompt from templates and context.

    Args:
        context: Assembled spec documents and memory facts.
        task_group: The target task group number.
        spec_name: The specification name (e.g. ``03_session_and_workspace``).
        role: **Deprecated.** Legacy prompt role (``"coding"`` or
            ``"coordinator"``). Mapped to archetype internally.
        archetype: Archetype name for template resolution via registry.
            Takes precedence over *role* when both are provided.

    Returns:
        Complete system prompt string.

    Raises:
        ValueError: If neither *role* nor *archetype* resolves to a valid
            archetype entry.
        ConfigError: If a template file is missing.

    Requirement: 15-REQ-2.2, 15-REQ-2.3, 15-REQ-2.4, 15-REQ-2.5, 15-REQ-2.E2,
                 26-REQ-3.5
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
            raise ValueError(
                f"Unknown prompt role {role!r}. Valid roles: {valid}"
            )
        resolved = mapped
    else:
        resolved = "coder"

    entry = get_archetype(resolved)

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

    # Load and compose templates from the archetype registry
    template_names = entry.templates
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
