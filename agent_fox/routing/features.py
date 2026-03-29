"""Feature vector extraction from spec content.

Extracts numeric and categorical attributes from a task group's spec files
for use by the heuristic and statistical assessors.

Requirements: 30-REQ-1.2, 30-REQ-1.E3,
              54-REQ-3.1, 54-REQ-3.2, 54-REQ-4.1, 54-REQ-4.2,
              54-REQ-5.1, 54-REQ-5.2, 54-REQ-6.1, 54-REQ-6.2
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import duckdb

from agent_fox.routing.core import FeatureVector

logger = logging.getLogger(__name__)

# Recognized programming language extensions (54-REQ-5.1)
_LANGUAGE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".js",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".proto",
        ".sql",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
    }
)


def extract_features(
    spec_dir: Path,
    task_group: int,
    archetype: str,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
    spec_name: str = "",
) -> FeatureVector:
    """Extract feature vector from spec content for the given task group.

    On any parse error (missing files, bad content), returns default values
    with zeros for numeric fields and the passed-in archetype string.

    Requirements: 30-REQ-1.2, 30-REQ-1.E3,
                  54-REQ-3.1, 54-REQ-4.1, 54-REQ-5.1, 54-REQ-6.1
    """
    try:
        subtask_count = _count_subtasks(spec_dir, task_group)
        spec_word_count = _count_spec_words(spec_dir)
        has_property_tests = _detect_property_tests(spec_dir)
        edge_case_count = _count_edge_cases(spec_dir)
        dependency_count = _count_dependencies(spec_dir)
        file_count_estimate = _count_file_paths(spec_dir, task_group)
        cross_spec_integration = _detect_cross_spec(spec_dir, task_group, spec_name)
        language_count = _count_languages(spec_dir, task_group)
        historical_median_duration_ms = _get_historical_median_duration(conn, spec_name)
    except Exception:
        logger.warning(
            "Feature extraction failed for %s task group %d, using defaults",
            spec_dir,
            task_group,
            exc_info=True,
        )
        return FeatureVector(
            subtask_count=0,
            spec_word_count=0,
            has_property_tests=False,
            edge_case_count=0,
            dependency_count=0,
            archetype=archetype,
            file_count_estimate=0,
            cross_spec_integration=False,
            language_count=1,
            historical_median_duration_ms=None,
        )

    return FeatureVector(
        subtask_count=subtask_count,
        spec_word_count=spec_word_count,
        has_property_tests=has_property_tests,
        edge_case_count=edge_case_count,
        dependency_count=dependency_count,
        archetype=archetype,
        file_count_estimate=file_count_estimate,
        cross_spec_integration=cross_spec_integration,
        language_count=language_count,
        historical_median_duration_ms=historical_median_duration_ms,
    )


def _read_file(spec_dir: Path, filename: str) -> str:
    """Read a spec file, returning empty string if not found."""
    path = spec_dir / filename
    if path.exists():
        return path.read_text()
    return ""


def _get_task_group_text(content: str, task_group: int) -> str:
    """Extract the text of a specific task group section from tasks.md content.

    Returns the text between '## Task Group N' and the next '##' header or
    end of file.
    """
    pattern = rf"##\s+Task Group {task_group}\b(.*?)(?=\n##|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def _count_subtasks(spec_dir: Path, task_group: int) -> int:
    """Count subtasks for a specific task group in tasks.md.

    Looks for lines matching `- [ ] N.M ...` or `- [x] N.M ...` or
    `- [-] N.M ...` where N equals the task group number.
    """
    content = _read_file(spec_dir, "tasks.md")
    if not content:
        return 0

    # Match checkbox lines like "- [ ] 2.1 ..." where the leading number
    # matches the task group.
    pattern = rf"^\s*-\s+\[.\]\s+{task_group}\.\d+"
    return len(re.findall(pattern, content, re.MULTILINE))


def _count_spec_words(spec_dir: Path) -> int:
    """Count total words across requirements.md and design.md."""
    total = 0
    for filename in ("requirements.md", "design.md"):
        content = _read_file(spec_dir, filename)
        if content:
            total += len(content.split())
    return total


def _detect_property_tests(spec_dir: Path) -> bool:
    """Detect presence of property tests in test_spec.md.

    Looks for 'property' in the Type field or 'Property Test' headers.
    """
    content = _read_file(spec_dir, "test_spec.md")
    if not content:
        return False

    # Look for property test indicators
    return bool(
        re.search(r"(?i)\bproperty\s+test", content)
        or re.search(r"\*\*Type:\*\*\s*property", content)
    )


def _count_edge_cases(spec_dir: Path) -> int:
    """Count edge cases in requirements.md.

    Looks for numbered edge case entries like `1. [REQ-1.E1]` or
    lines under '### Edge Cases' headers.
    """
    content = _read_file(spec_dir, "requirements.md")
    if not content:
        return 0

    # Match patterns like "1. [REQ-1.E1]" or "[30-REQ-1.E1]"
    matches = re.findall(r"^\s*\d+\.\s+\[[\w-]+\.E\d+\]", content, re.MULTILINE)
    return len(matches)


def _count_dependencies(spec_dir: Path) -> int:
    """Count dependencies from design.md.

    Looks for bullet points under a '## Dependencies' section.
    """
    content = _read_file(spec_dir, "design.md")
    if not content:
        return 0

    # Find the Dependencies section and count bullet items
    dep_match = re.search(
        r"##\s+Dependencies\s*\n(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL,
    )
    if not dep_match:
        return 0

    dep_section = dep_match.group(1)
    # Count lines starting with "- " (bullet points)
    return len(re.findall(r"^\s*-\s+\S", dep_section, re.MULTILINE))


def _count_file_paths(spec_dir: Path, task_group: int) -> int:
    """Count distinct file paths mentioned in the task group's section of tasks.md.

    File paths are detected by the pattern ``[a-zA-Z_/]+\\.\\w{1,5}``.

    Requirements: 54-REQ-3.1, 54-REQ-3.2
    """
    content = _read_file(spec_dir, "tasks.md")
    if not content:
        return 0
    section = _get_task_group_text(content, task_group)
    if not section:
        return 0
    matches = re.findall(r"[a-zA-Z_/]+\.\w{1,5}", section)
    return len(set(matches))


def _detect_cross_spec(spec_dir: Path, task_group: int, own_spec: str) -> bool:
    """Check if task group references spec names other than its own.

    Spec names are detected by the pattern \\d{2}_[a-z_]+ (e.g. 03_api_routes).
    Returns False when own_spec is empty (cannot determine cross-spec without context).

    Requirements: 54-REQ-4.1, 54-REQ-4.2
    """
    if not own_spec:
        return False
    content = _read_file(spec_dir, "tasks.md")
    if not content:
        return False
    section = _get_task_group_text(content, task_group)
    if not section:
        return False
    spec_names = re.findall(r"\d{2}_[a-z_]+", section)
    return any(name != own_spec for name in spec_names)


def _count_languages(spec_dir: Path, task_group: int) -> int:
    """Count distinct programming language file extensions in the task group section.

    Recognized extensions: .py .ts .js .go .rs .java .rb .proto .sql .toml
                           .yaml .yml .json

    Defaults to 1 when no recognized extensions are found (assume primary language).

    Requirements: 54-REQ-5.1, 54-REQ-5.2
    """
    content = _read_file(spec_dir, "tasks.md")
    if not content:
        return 1
    section = _get_task_group_text(content, task_group)
    if not section:
        return 1
    files = re.findall(r"[a-zA-Z_/]+\.\w{1,5}", section)
    extensions = set()
    for f in files:
        # Extract extension: everything after the last dot
        dot_idx = f.rfind(".")
        if dot_idx != -1:
            ext = f[dot_idx:]
            if ext in _LANGUAGE_EXTENSIONS:
                extensions.add(ext)
    return len(extensions) if extensions else 1


def _get_historical_median_duration(
    conn: duckdb.DuckDBPyConnection | None,
    spec_name: str,
) -> int | None:
    """Query median duration_ms of successful outcomes for the given spec.

    Only considers execution outcomes with outcome='completed'.
    Returns None when no connection is provided, spec_name is empty, or
    no successful outcomes exist.

    Requirements: 54-REQ-6.1, 54-REQ-6.2, 54-REQ-6.E1
    """
    if conn is None or not spec_name:
        return None
    try:
        result = conn.execute(
            """SELECT MEDIAN(o.duration_ms)
               FROM execution_outcomes o
               JOIN complexity_assessments a ON o.assessment_id = a.id
               WHERE a.spec_name = ? AND o.outcome = 'completed'""",
            [spec_name],
        ).fetchone()
        if result is None or result[0] is None:
            return None
        return int(result[0])
    except Exception:
        logger.warning(
            "Failed to query historical median duration for spec %s",
            spec_name,
            exc_info=True,
        )
        return None
