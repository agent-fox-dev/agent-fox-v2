"""Regex file search with context lines and content hashes.

Searches a file by regex pattern, returning matching lines with
surrounding context. All lines include content hashes for use
with the edit tool.

Requirements: 29-REQ-4.1, 29-REQ-4.2, 29-REQ-4.3,
              29-REQ-4.E1, 29-REQ-4.E2, 29-REQ-4.E3
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.tools._file_io import read_text_lossy, validate_file
from agent_fox.tools.hashing import hash_line
from agent_fox.tools.types import HashedLine, SearchMatch, SearchResult


def fox_search(
    file_path: str,
    pattern: str,
    context: int = 0,
) -> SearchResult | str:
    """Search a file by regex pattern with optional context lines.

    Args:
        file_path: Absolute path to the file.
        pattern: Regex pattern to search for.
        context: Number of context lines before and after each match.

    Returns:
        SearchResult on success, or an error string on failure.
    """
    path = Path(file_path)

    err = validate_file(path)
    if err:
        return err

    # Validate regex
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex pattern '{pattern}': {e}"

    text, read_err = read_text_lossy(path)
    if read_err:
        return read_err

    file_lines = text.splitlines(keepends=True)
    total_lines = len(file_lines)

    # Find matching line indices (0-based)
    match_indices: list[int] = []
    for idx, line in enumerate(file_lines):
        if compiled.search(line):
            match_indices.append(idx)

    if not match_indices:
        return SearchResult(matches=[], total_matches=0)

    # Build context ranges (0-based inclusive) and merge overlapping
    raw_ranges: list[tuple[int, int, list[int]]] = []
    for idx in match_indices:
        range_start = max(0, idx - context)
        range_end = min(total_lines - 1, idx + context)
        raw_ranges.append((range_start, range_end, [idx]))

    # Merge overlapping/adjacent ranges
    merged: list[tuple[int, int, list[int]]] = [raw_ranges[0]]
    for start, end, match_idxs in raw_ranges[1:]:
        prev_start, prev_end, prev_matches = merged[-1]
        if start <= prev_end + 1:
            # Overlapping or adjacent — merge
            merged[-1] = (
                prev_start,
                max(prev_end, end),
                prev_matches + match_idxs,
            )
        else:
            merged.append((start, end, match_idxs))

    # Build SearchMatch objects
    matches: list[SearchMatch] = []
    for range_start, range_end, match_idxs in merged:
        lines: list[HashedLine] = []
        for idx in range(range_start, range_end + 1):
            line_content = file_lines[idx]
            line_hash = hash_line(line_content.encode("utf-8"))
            lines.append(
                HashedLine(
                    line_number=idx + 1,  # 1-based
                    content=line_content,
                    hash=line_hash,
                )
            )
        # Match line numbers are 1-based
        match_line_numbers = [idx + 1 for idx in match_idxs]
        matches.append(SearchMatch(lines=lines, match_line_numbers=match_line_numbers))

    return SearchResult(matches=matches, total_matches=len(match_indices))
