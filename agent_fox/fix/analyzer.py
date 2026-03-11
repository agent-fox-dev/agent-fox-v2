"""Analyzer module for Phase 2 auto-improve.

Builds analyzer prompts, parses structured JSON responses, filters
improvements by confidence and tier priority, and queries the oracle
for project knowledge context.

Requirements: 31-REQ-3.*, 31-REQ-4.*
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)

# Tier priority order: lower value = higher priority
_TIER_PRIORITY: dict[str, int] = {
    "quick_win": 0,
    "structural": 1,
    "design_level": 2,
}

# Required fields for the analyzer JSON response
_REQUIRED_RESPONSE_FIELDS = {"improvements", "summary", "diminishing_returns"}
_REQUIRED_IMPROVEMENT_FIELDS = {
    "id",
    "tier",
    "title",
    "description",
    "files",
    "impact",
    "confidence",
}

# Convention file names to search for, in priority order
_CONVENTION_FILES = ("CLAUDE.md", "AGENTS.md", "README.md")

# Seed question for oracle context enrichment (31-REQ-4.1)
_ORACLE_SEED_QUESTION = (
    "What are the established patterns, conventions, "
    "and architectural decisions in this project?"
)


@dataclass(frozen=True)
class Improvement:
    """A single improvement suggestion from the analyzer."""

    id: str
    tier: str  # "quick_win" | "structural" | "design_level"
    title: str
    description: str
    files: list[str]
    impact: str  # "low" | "medium" | "high"
    confidence: str  # "high" | "medium" | "low"


@dataclass
class AnalyzerResult:
    """Parsed output from the analyzer session."""

    improvements: list[Improvement]
    summary: str
    diminishing_returns: bool
    raw_response: str = ""  # for debugging


def build_analyzer_prompt(
    project_root: Path,
    config: AgentFoxConfig,
    *,
    oracle_context: str = "",
    review_context: str = "",
    phase1_diff: str = "",
    previous_pass_result: str = "",
) -> tuple[str, str]:
    """Build the system prompt and task prompt for the analyzer.

    Returns (system_prompt, task_prompt).

    The system prompt includes:
    - Role: codebase improvement analyst
    - Project conventions (from CLAUDE.md / AGENTS.md / README.md)
    - Simplifier guardrails (what NOT to change)
    - Oracle context (## Project Knowledge section, if available)
    - Review findings from DuckDB (if any)

    The task prompt includes:
    - Analysis scope: entire repository
    - Project file tree
    - Phase 1 diff (if any changes were made during repair)
    - Previous pass results (if not the first pass)
    - Required output format (structured JSON)

    Requirements: 31-REQ-3.1, 31-REQ-3.2
    """
    # -- System prompt --
    system_parts: list[str] = [
        "You are a senior software architect analyzing a codebase for improvement "
        "opportunities. Your goal is to identify concrete, actionable improvements "
        "that make the code simpler, clearer, and more maintainable.",
        "",
        "## Guardrails",
        "",
        "- NEVER refactor test code for DRYness — test readability trumps DRY",
        "- NEVER change public APIs "
        "(function signatures, class interfaces, CLI options)",
        "- NEVER remove \"why\" comments — only remove \"what\" comments "
        "that restate code",
        "- NEVER remove or weaken error handling or logging",
        "- NEVER introduce new dependencies",
        "- Favor deletion over addition — removing dead code is always a win",
        "- Preserve git-blame-ability — prefer surgical edits over wholesale rewrites",
    ]

    # Project conventions
    conventions = _load_conventions(project_root)
    if conventions:
        system_parts.extend(["", "## Project Conventions", "", conventions])

    # Oracle context (31-REQ-4.2)
    if oracle_context:
        system_parts.extend(["", "## Project Knowledge", "", oracle_context])

    # Review findings
    if review_context:
        system_parts.extend(
            ["", "## Prior Review Findings", "", review_context]
        )

    system_prompt = "\n".join(system_parts)

    # -- Task prompt --
    file_tree = _build_file_tree(project_root)

    task_parts: list[str] = [
        "Analyze the following codebase for improvement opportunities.",
        "",
        "## Scope",
        "",
        "Analyze the entire repository. The project structure is:",
        "",
        file_tree,
        "",
        "## Recent Changes",
        "",
        phase1_diff if phase1_diff else "No recent changes.",
        "",
        "## Previous Pass",
        "",
        previous_pass_result
        if previous_pass_result
        else "This is the first improvement pass.",
        "",
        "## Instructions",
        "",
        "1. Examine the codebase for: redundancy, unnecessary complexity, dead code,",
        "   stale patterns, consolidation opportunities, and readability issues.",
        "2. Prioritize improvements by tier: quick_win (safe, mechanical), structural",
        "   (module reorganization, consolidation), design_level (pattern changes).",
        "3. For each improvement, assess confidence (high/medium/low) and impact",
        "   (high/medium/low).",
        "4. Set diminishing_returns to true if remaining opportunities are too minor",
        "   or risky to justify a coding session.",
        "",
        "Respond with ONLY valid JSON in this exact format:",
        "",
        """{
  "improvements": [
    {
      "id": "IMP-1",
      "tier": "quick_win",
      "title": "Short title",
      "description": "What to change and why",
      "files": ["path/to/file.py"],
      "impact": "low",
      "confidence": "high"
    }
  ],
  "summary": "Human-readable summary",
  "diminishing_returns": false
}""",
    ]

    task_prompt = "\n".join(task_parts)

    return system_prompt, task_prompt


def parse_analyzer_response(response: str) -> AnalyzerResult:
    """Parse the analyzer's JSON response into an AnalyzerResult.

    Validates required fields and structure. Raises ValueError if the
    response cannot be parsed.

    Requirements: 31-REQ-3.3, 31-REQ-3.E1
    """
    # Extract JSON from potential markdown code fences
    cleaned = _extract_json(response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in analyzer response: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Analyzer response must be a JSON object")

    # Validate required top-level fields
    missing = _REQUIRED_RESPONSE_FIELDS - set(data.keys())
    if missing:
        raise ValueError(
            f"Analyzer response missing required fields: {sorted(missing)}"
        )

    # Parse improvements
    raw_improvements = data.get("improvements", [])
    if not isinstance(raw_improvements, list):
        raise ValueError("'improvements' must be a list")

    improvements: list[Improvement] = []
    for i, item in enumerate(raw_improvements):
        improvements.append(_parse_improvement(item, index=i))

    return AnalyzerResult(
        improvements=improvements,
        summary=str(data["summary"]),
        diminishing_returns=bool(data["diminishing_returns"]),
        raw_response=response,
    )


def filter_improvements(
    improvements: list[Improvement],
) -> list[Improvement]:
    """Filter out low-confidence improvements and sort by tier priority.

    Returns improvements with confidence 'high' or 'medium', sorted:
    quick_win first, structural second, design_level third.

    Requirements: 31-REQ-3.4, 31-REQ-3.5
    """
    # Exclude low-confidence items (31-REQ-3.4)
    filtered = [i for i in improvements if i.confidence != "low"]

    # Sort by tier priority (31-REQ-3.5)
    filtered.sort(key=lambda imp: _TIER_PRIORITY.get(imp.tier, 99))

    return filtered


def query_oracle_context(config: AgentFoxConfig) -> str:
    """Query the oracle for project knowledge context.

    Runs the oracle RAG pipeline with the seed question about patterns,
    conventions, and architectural decisions. Returns formatted context
    string. DuckDB errors propagate to the caller (38-REQ-3.1).

    Requirements: 31-REQ-4.1, 31-REQ-4.2, 31-REQ-4.3, 31-REQ-4.E1
    """
    results = _query_oracle_facts(config)

    if not results:
        return ""

    # Format results with provenance (31-REQ-4.2)
    parts: list[str] = []
    for i, result in enumerate(results, 1):
        # Build provenance from available metadata
        provenance_parts: list[str] = []
        metadata = getattr(result, "metadata", {}) or {}
        if isinstance(metadata, dict):
            if metadata.get("spec"):
                provenance_parts.append(f"spec: {metadata['spec']}")
            if metadata.get("adr"):
                provenance_parts.append(f"ADR: {metadata['adr']}")
            if metadata.get("commit_sha"):
                provenance_parts.append(f"commit: {metadata['commit_sha']}")

        # Also check direct attributes (SearchResult)
        spec_name = getattr(result, "spec_name", None)
        if spec_name and not provenance_parts:
            provenance_parts.append(f"spec: {spec_name}")
        commit_sha = getattr(result, "commit_sha", None)
        if commit_sha and "commit:" not in str(provenance_parts):
            provenance_parts.append(f"commit: {commit_sha}")

        provenance = (
            f" ({', '.join(provenance_parts)})" if provenance_parts else ""
        )
        content = getattr(result, "content", str(result))
        parts.append(f"- {content}{provenance}")

    return "\n".join(parts)


def load_review_context(project_root: Path) -> str:
    """Load existing skeptic/verifier findings from DuckDB.

    Returns a formatted context string, or empty string if no findings
    exist. DuckDB errors propagate to the caller (38-REQ-3.1).

    Requirements: 31-REQ-3.2
    """
    from agent_fox.knowledge.db import KnowledgeDB
    from agent_fox.knowledge.review_store import (
        query_active_findings,
    )

    config = AgentFoxConfig()
    db = KnowledgeDB(config.knowledge)
    db.open()
    conn = db.connection

    findings = query_active_findings(conn, spec_name="")
    if not findings:
        db.close()
        return ""

    parts: list[str] = []
    for f in findings:
        parts.append(
            f"- [{f.severity}] {f.description} "
            f"(spec: {f.spec_name}, task: {f.task_group})"
        )

    db.close()
    return "\n".join(parts)


def _query_oracle_facts(config: AgentFoxConfig) -> list[Any]:
    """Query oracle for project knowledge facts.

    This is a separate function to allow easy mocking in tests.
    Raises on failure (caller handles gracefully).
    """
    from agent_fox.knowledge.db import KnowledgeDB
    from agent_fox.knowledge.embeddings import EmbeddingGenerator
    from agent_fox.knowledge.query import Oracle
    from agent_fox.knowledge.search import VectorSearch

    db = KnowledgeDB(config.knowledge)
    db.open()

    embedder = EmbeddingGenerator(config.knowledge)
    search = VectorSearch(db.connection, config.knowledge)
    oracle = Oracle(embedder, search, config.knowledge)

    answer = oracle.ask(_ORACLE_SEED_QUESTION)
    db.close()

    return answer.sources[:10]  # top-k = 10 (31-REQ-4.2)


def _load_conventions(project_root: Path) -> str:
    """Load project conventions from CLAUDE.md, AGENTS.md, or README.md."""
    for filename in _CONVENTION_FILES:
        path = project_root / filename
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""


def _build_file_tree(project_root: Path) -> str:
    """Build a project file tree string using git ls-files or os.walk.

    Uses git ls-files if in a git repo, otherwise falls back to a simple
    directory listing.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Group by top-level directory for readability
            lines = result.stdout.strip().split("\n")
            # Limit output for very large repos
            if len(lines) > 200:
                return "\n".join(lines[:200]) + f"\n... ({len(lines)} files total)"
            return "\n".join(lines)
    except (subprocess.SubprocessError, OSError):
        pass

    # Fallback: simple walk
    parts: list[str] = []
    for path in sorted(project_root.rglob("*.py")):
        try:
            rel = path.relative_to(project_root)
            parts.append(str(rel))
        except ValueError:
            continue
    if len(parts) > 200:
        return "\n".join(parts[:200]) + f"\n... ({len(parts)} files total)"
    return "\n".join(parts) if parts else "(empty project)"


def _extract_json(text: str) -> str:
    """Extract JSON from text that may be wrapped in markdown code fences."""
    stripped = text.strip()

    # Try to extract from ```json ... ``` or ``` ... ```
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    return stripped


def _parse_improvement(data: Any, *, index: int) -> Improvement:
    """Parse a single improvement dict into an Improvement dataclass."""
    if not isinstance(data, dict):
        raise ValueError(f"Improvement at index {index} must be an object")

    missing = _REQUIRED_IMPROVEMENT_FIELDS - set(data.keys())
    if missing:
        raise ValueError(
            f"Improvement at index {index} missing fields: {sorted(missing)}"
        )

    files = data["files"]
    if not isinstance(files, list):
        files = [str(files)]

    return Improvement(
        id=str(data["id"]),
        tier=str(data["tier"]),
        title=str(data["title"]),
        description=str(data["description"]),
        files=[str(f) for f in files],
        impact=str(data["impact"]),
        confidence=str(data["confidence"]),
    )
