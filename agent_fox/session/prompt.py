"""Session preparation: context assembly and prompt building.

Gathers spec documents and memory facts for session context, loads
rich templates from agent_fox/_templates/prompts/ with placeholder
interpolation and frontmatter stripping.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 03-REQ-5.1, 03-REQ-5.2,
              13-REQ-7.1, 13-REQ-7.2, 15-REQ-1.1, 15-REQ-1.2,
              15-REQ-1.E1, 15-REQ-2.1 through 15-REQ-5.E1,
              27-REQ-5.1, 27-REQ-5.2, 27-REQ-5.3, 27-REQ-5.E1, 27-REQ-5.E2,
              27-REQ-10.1, 27-REQ-10.2
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import duckdb

from agent_fox.core.errors import ConfigError
from agent_fox.knowledge.causal import traverse_causal_chain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context assembly (merged from context.py)
# ---------------------------------------------------------------------------

# Core spec files — always expected to exist for every spec.
_CORE_SPEC_FILES: list[tuple[str, str]] = [
    ("requirements.md", "## Requirements"),
    ("design.md", "## Design"),
    ("test_spec.md", "## Test Specification"),
    ("tasks.md", "## Tasks"),
]

# Archetype-produced files — only present after the corresponding archetype
# (Skeptic / Verifier) has run.  Included silently when they exist on disk,
# skipped silently when they don't.
_ARCHETYPE_SPEC_FILES: list[tuple[str, str]] = [
    ("review.md", "## Skeptic Review"),
    ("verification.md", "## Verification Report"),
]


def render_drift_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active drift findings as a markdown section.

    Returns None if no findings exist (32-REQ-8.E1).

    Requirements: 32-REQ-8.1, 32-REQ-8.2
    """
    from agent_fox.knowledge.review_store import (
        query_active_drift_findings,
    )

    findings = query_active_drift_findings(conn, spec_name)
    if not findings:
        return None

    severity_groups = {
        "critical": "### Critical Findings",
        "major": "### Major Findings",
        "minor": "### Minor Findings",
        "observation": "### Observations",
    }

    lines = ["## Oracle Drift Report", ""]
    counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "observation": 0}

    for sev, header in severity_groups.items():
        sev_findings = [f for f in findings if f.severity == sev]
        counts[sev] = len(sev_findings)
        if sev_findings:
            lines.append(header)
            for f in sev_findings:
                desc = f.description
                refs = []
                if f.spec_ref:
                    refs.append(f"spec: {f.spec_ref}")
                if f.artifact_ref:
                    refs.append(f"artifact: {f.artifact_ref}")
                if refs:
                    desc += f" ({', '.join(refs)})"
                lines.append(f"- {desc}")
            lines.append("")

    lines.append(
        f"Summary: {counts['critical']} critical, {counts['major']} major, "
        f"{counts['minor']} minor, {counts['observation']} observations."
    )

    return "\n".join(lines)


def render_review_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active findings as a markdown section.

    Returns None if no findings exist (27-REQ-5.E2).

    Requirements: 27-REQ-5.1, 27-REQ-5.3
    """
    from agent_fox.knowledge.review_store import (
        query_active_findings,
    )

    findings = query_active_findings(conn, spec_name)
    if not findings:
        return None

    severity_groups = {
        "critical": "### Critical Findings",
        "major": "### Major Findings",
        "minor": "### Minor Findings",
        "observation": "### Observations",
    }

    lines = ["## Skeptic Review", ""]
    counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "observation": 0}

    for sev, header in severity_groups.items():
        sev_findings = [f for f in findings if f.severity == sev]
        counts[sev] = len(sev_findings)
        lines.append(header)
        if sev_findings:
            for f in sev_findings:
                lines.append(f"- [severity: {f.severity}] {f.description}")
        else:
            lines.append("(none)")
        lines.append("")

    lines.append(
        f"Summary: {counts['critical']} critical, {counts['major']} major, "
        f"{counts['minor']} minor, {counts['observation']} observations."
    )

    return "\n".join(lines)


def render_verification_context(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
) -> str | None:
    """Render active verdicts as a markdown section.

    Returns None if no verdicts exist (27-REQ-5.E2).

    Requirements: 27-REQ-5.2, 27-REQ-5.3
    """
    from agent_fox.knowledge.review_store import (
        query_active_verdicts,
    )

    verdicts = query_active_verdicts(conn, spec_name)
    if not verdicts:
        return None

    lines = [
        "## Verification Report",
        "",
        "| Requirement | Status | Notes |",
        "|-------------|--------|-------|",
    ]

    has_fail = False
    for v in verdicts:
        notes = v.evidence or ""
        lines.append(f"| {v.requirement_id} | {v.verdict} | {notes} |")
        if v.verdict == "FAIL":
            has_fail = True

    lines.append("")
    overall = "FAIL" if has_fail else "PASS"
    lines.append(f"Verdict: {overall}")

    return "\n".join(lines)


def _migrate_legacy_files(
    conn: duckdb.DuckDBPyConnection,
    spec_dir: Path,
    spec_name: str,
) -> None:
    """Migrate legacy review.md/verification.md files to DB records.

    Only runs when no DB records exist for the spec. On parse failure,
    logs a warning and skips (27-REQ-10.E1).

    Requirements: 27-REQ-10.1, 27-REQ-10.2, 27-REQ-10.E1
    """
    from agent_fox.knowledge.review_store import (
        insert_findings,
        insert_verdicts,
        query_active_findings,
        query_active_verdicts,
    )
    from agent_fox.session.review_parser import (
        parse_legacy_review_md,
        parse_legacy_verification_md,
    )

    # Migrate review.md if no DB records exist
    review_path = spec_dir / "review.md"
    if review_path.exists() and not query_active_findings(conn, spec_name):
        try:
            content = review_path.read_text(encoding="utf-8")
            findings = parse_legacy_review_md(
                content, spec_name, "legacy", "legacy-migration"
            )
            if findings:
                insert_findings(conn, findings)
                logger.info("Migrated %d findings from %s", len(findings), review_path)
        except Exception:
            logger.warning(
                "Failed to migrate legacy review file %s, skipping",
                review_path,
                exc_info=True,
            )

    # Migrate verification.md if no DB records exist
    verification_path = spec_dir / "verification.md"
    if verification_path.exists() and not query_active_verdicts(conn, spec_name):
        try:
            content = verification_path.read_text(encoding="utf-8")
            verdicts = parse_legacy_verification_md(
                content, spec_name, "legacy", "legacy-migration"
            )
            if verdicts:
                insert_verdicts(conn, verdicts)
                logger.info(
                    "Migrated %d verdicts from %s",
                    len(verdicts),
                    verification_path,
                )
        except Exception:
            logger.warning(
                "Failed to migrate legacy verification file %s, skipping",
                verification_path,
                exc_info=True,
            )


def assemble_context(
    spec_dir: Path,
    task_group: int,
    memory_facts: list[str] | None = None,
    conn: duckdb.DuckDBPyConnection = None,  # type: ignore[assignment]
) -> str:
    """Assemble task-specific context for a coding session.

    Reads the following files from spec_dir (if they exist):
    - requirements.md
    - design.md
    - test_spec.md
    - tasks.md

    Renders review/verification/drift sections from DuckDB
    (27-REQ-5.1, 27-REQ-5.2, 38-REQ-4.1, 38-REQ-4.2).
    DB errors propagate — no file-based fallback (38-REQ-3.E1).

    Appends relevant memory facts (if provided).

    Returns a formatted string with section headers.

    Logs a warning for any missing spec file but does not raise.
    """
    sections: list[str] = []

    # Derive spec_name from directory name
    spec_name = spec_dir.name

    # Determine which files to skip if DB rendering succeeds
    db_rendered_files: set[str] = set()

    if conn is not None:
        # DB-backed rendering — errors propagate (38-REQ-3.E1, 38-REQ-4.2)
        # Attempt legacy file migration first (27-REQ-10.1, 27-REQ-10.2)
        _migrate_legacy_files(conn, spec_dir, spec_name)

        # DB-backed rendering (27-REQ-5.1, 27-REQ-5.2, 38-REQ-4.3)
        review_md = render_review_context(conn, spec_name)
        if review_md is not None:
            sections.append(review_md)
            db_rendered_files.add("review.md")

        verification_md = render_verification_context(conn, spec_name)
        if verification_md is not None:
            sections.append(verification_md)
            db_rendered_files.add("verification.md")

        # Render oracle drift report (32-REQ-8.1)
        drift_md = render_drift_context(conn, spec_name)
        if drift_md is not None:
            sections.append(drift_md)

    # 03-REQ-4.1: Read spec documents
    file_sections: list[str] = []
    for filename, header in _CORE_SPEC_FILES:
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
        file_sections.append(f"{header}\n\n{content}")

    # Include archetype-produced files (review.md, verification.md) only
    # when they exist on disk and weren't already rendered from the DB.
    for filename, header in _ARCHETYPE_SPEC_FILES:
        if filename in db_rendered_files:
            continue
        filepath = spec_dir / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        file_sections.append(f"{header}\n\n{content}")

    # Insert file sections before DB-rendered sections
    sections = file_sections + sections

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
    "skeptic": "skeptic",
    "verifier": "verifier",
    "librarian": "librarian",
    "cartographer": "cartographer",
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
            raise ValueError(f"Unknown prompt role {role!r}. Valid roles: {valid}")
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
    archetype: str = "coder",
) -> str:
    """Build an enriched task prompt.

    For coder archetypes: includes spec name, task group, instructions to
    update checkbox states, commit on the feature branch, and run quality
    gates.

    For non-coder archetypes (skeptic, verifier, etc.): returns a concise
    prompt that defers to the system prompt template for detailed
    instructions.

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
