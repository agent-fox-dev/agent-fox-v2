"""Feature vector extraction from spec content.

Extracts numeric and categorical attributes from a task group's spec files
for use by the heuristic and statistical assessors.

Requirements: 30-REQ-1.2, 30-REQ-1.E3
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent_fox.routing.types import FeatureVector

logger = logging.getLogger(__name__)


def extract_features(
    spec_dir: Path,
    task_group: int,
    archetype: str,
) -> FeatureVector:
    """Extract feature vector from spec content for the given task group.

    On any parse error (missing files, bad content), returns default values
    with zeros for numeric fields and the passed-in archetype string.

    Requirements: 30-REQ-1.2, 30-REQ-1.E3
    """
    try:
        subtask_count = _count_subtasks(spec_dir, task_group)
        spec_word_count = _count_spec_words(spec_dir)
        has_property_tests = _detect_property_tests(spec_dir)
        edge_case_count = _count_edge_cases(spec_dir)
        dependency_count = _count_dependencies(spec_dir)
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
        )

    return FeatureVector(
        subtask_count=subtask_count,
        spec_word_count=spec_word_count,
        has_property_tests=has_property_tests,
        edge_case_count=edge_case_count,
        dependency_count=dependency_count,
        archetype=archetype,
    )


def _read_file(spec_dir: Path, filename: str) -> str:
    """Read a spec file, returning empty string if not found."""
    path = spec_dir / filename
    if path.exists():
        return path.read_text()
    return ""


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
