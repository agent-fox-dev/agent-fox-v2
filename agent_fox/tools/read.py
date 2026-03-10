"""Line-range file reading with content hashes.

Reads specific line ranges from a file, annotating each line with its
1-based line number and xxh3_64 content hash.

Requirements: 29-REQ-2.1, 29-REQ-2.2, 29-REQ-2.3,
              29-REQ-2.E1, 29-REQ-2.E2, 29-REQ-2.E3
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.tools.hashing import hash_line
from agent_fox.tools.types import HashedLine, ReadResult


def fox_read(file_path: str, ranges: list[tuple[int, int]]) -> ReadResult | str:
    """Read line ranges from a file with content hashes.

    Args:
        file_path: Absolute path to the file.
        ranges: List of (start, end) line ranges (1-based, inclusive).

    Returns:
        ReadResult on success, or an error string on failure.
    """
    path = Path(file_path)

    # Check existence and readability
    if not path.exists():
        return f"Error: file not found: {file_path}"
    if not path.is_file():
        return f"Error: not a file: {file_path}"

    # Validate ranges
    for start, end in ranges:
        if start > end:
            return f"Error: invalid range [{start}, {end}] — start > end"

    # Read file
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
        except Exception as e:
            return f"Error: cannot read {file_path}: {e}"
    except OSError as e:
        return f"Error: cannot read {file_path}: {e}"

    file_lines = text.splitlines(keepends=True)
    total_lines = len(file_lines)

    # Sort ranges by start line
    sorted_ranges = sorted(ranges, key=lambda r: r[0])

    # Collect lines and warnings
    result_lines: list[HashedLine] = []
    warnings: list[str] = []

    for start, end in sorted_ranges:
        actual_end = min(end, total_lines)
        if end > total_lines:
            warnings.append(
                f"Range [{start}, {end}] truncated at line {total_lines}"
            )
        for line_num in range(start, actual_end + 1):
            line_content = file_lines[line_num - 1]  # 0-based index
            line_hash = hash_line(line_content.encode("utf-8"))
            result_lines.append(
                HashedLine(
                    line_number=line_num,
                    content=line_content,
                    hash=line_hash,
                )
            )

    return ReadResult(lines=result_lines, warnings=warnings)
