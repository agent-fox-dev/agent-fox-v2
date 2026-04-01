"""Archetype tag fixers: invalid and malformed archetype tags.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.spec._patterns import (
    MALFORMED_ARCHETYPE_TAG as _MALFORMED_ARCHETYPE_TAG,
)
from agent_fox.spec.parser import (
    _ARCHETYPE_TAG,
    _KNOWN_ARCHETYPES,
)

from .types import FixResult


def _fix_archetype_tags_in_file(
    spec_name: str,
    tasks_path: Path,
    *,
    mode: str,
) -> list[FixResult]:
    """Shared fixer for archetype tag issues.

    Args:
        mode: ``"invalid"`` to remove unknown tags, ``"malformed"`` to
            normalize syntax and remove duplicates.
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    results: list[FixResult] = []

    for i, line in enumerate(lines):
        if not re.match(r"^- \[.\]", line):
            continue

        if mode == "invalid":
            match = _ARCHETYPE_TAG.search(line)
            if match and match.group(1) not in _KNOWN_ARCHETYPES:
                old_tag = match.group()
                lines[i] = line.replace(old_tag, "").rstrip()
                lines[i] = re.sub(r"  +", " ", lines[i]).rstrip()
                results.append(
                    FixResult(
                        rule="invalid-archetype-tag",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(
                            f"Removed unknown archetype tag '{old_tag}' "
                            f"from line {i + 1} (defaults to coder)"
                        ),
                    )
                )

        elif mode == "malformed":
            # Handle duplicate well-formed tags: keep first, remove rest
            all_good = list(_ARCHETYPE_TAG.finditer(line))
            if len(all_good) > 1:
                new_line = line
                for m in reversed(all_good[1:]):
                    new_line = new_line[: m.start()] + new_line[m.end() :]
                lines[i] = re.sub(r"  +", " ", new_line).rstrip()
                results.append(
                    FixResult(
                        rule="malformed-archetype-tag",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(
                            f"Removed duplicate archetype tags "
                            f"on line {i + 1}, kept first"
                        ),
                    )
                )
                continue

            # Skip lines that already have a well-formed tag
            if _ARCHETYPE_TAG.search(line):
                continue

            # Try to normalize malformed tags
            bad_match = _MALFORMED_ARCHETYPE_TAG.search(line)
            if bad_match:
                bad_tag = bad_match.group()
                name_match = re.search(r"(\w+)\]$", bad_tag)
                if name_match:
                    name = name_match.group(1).lower()
                    normalized = f"[archetype: {name}]"
                    lines[i] = line.replace(bad_tag, normalized)
                    results.append(
                        FixResult(
                            rule="malformed-archetype-tag",
                            spec_name=spec_name,
                            file=str(tasks_path),
                            description=(
                                f"Normalized '{bad_tag}' to "
                                f"'{normalized}' on line {i + 1}"
                            ),
                        )
                    )

    if results:
        tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def fix_invalid_archetype_tag(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Remove archetype tags that reference unknown archetype names."""
    return _fix_archetype_tags_in_file(spec_name, tasks_path, mode="invalid")


def fix_malformed_archetype_tag(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Normalize malformed archetype tags to [archetype: name] format."""
    return _fix_archetype_tags_in_file(spec_name, tasks_path, mode="malformed")
