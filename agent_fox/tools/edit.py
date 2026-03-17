"""Hash-verified atomic batch editing.

Applies edits to files by verifying content hashes before writing,
processing in reverse line order, and using atomic temp-file writes.

Requirements: 29-REQ-3.1, 29-REQ-3.2, 29-REQ-3.3, 29-REQ-3.4,
              29-REQ-3.E1, 29-REQ-3.E2, 29-REQ-3.E3
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from agent_fox.tools._file_io import read_text_lossy, validate_file
from agent_fox.tools.hashing import hash_line
from agent_fox.tools.types import EditOperation, EditResult


def fox_edit(file_path: str, edits: list[EditOperation]) -> EditResult:
    """Apply hash-verified edits atomically.

    Args:
        file_path: Absolute path to the file.
        edits: List of edit operations with line ranges, hashes, and
            replacement content.

    Returns:
        EditResult indicating success/failure and any errors.
    """
    path = Path(file_path)

    err = validate_file(path, writable=True)
    if err:
        return EditResult(success=False, lines_changed=0, errors=[err])

    if not edits:
        return EditResult(success=True, lines_changed=0)

    # --- Pre-validation: overlapping ranges ---
    overlap_errors = _check_overlaps(edits)
    if overlap_errors:
        return EditResult(success=False, lines_changed=0, errors=overlap_errors)

    # --- Read file ---
    text, read_err = read_text_lossy(path)
    if read_err:
        return EditResult(success=False, lines_changed=0, errors=[read_err])

    file_lines = text.splitlines(keepends=True)

    # --- Hash verification (all edits, before any mutation) ---
    hash_errors = _verify_hashes(file_lines, edits)
    if hash_errors:
        return EditResult(success=False, lines_changed=0, errors=hash_errors)

    # --- Apply edits in reverse line order (29-REQ-3.3) ---
    sorted_edits = sorted(edits, key=lambda e: e.start_line, reverse=True)
    total_changed = 0

    for edit in sorted_edits:
        start_idx = edit.start_line - 1  # convert to 0-based
        end_idx = edit.end_line  # exclusive for list slicing

        old_count = end_idx - start_idx

        if edit.new_content:
            # Split new content into lines, preserving trailing newlines
            new_lines = _split_new_content(edit.new_content)
            file_lines[start_idx:end_idx] = new_lines
            total_changed += max(old_count, len(new_lines))
        else:
            # Empty content = line deletion (29-REQ-3.4)
            del file_lines[start_idx:end_idx]
            total_changed += old_count

    # --- Atomic write via temp file + rename ---
    new_content = "".join(file_lines)
    try:
        dir_path = path.parent
        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), prefix=".fox_edit_")
        try:
            os.write(fd, new_content.encode("utf-8"))
            os.close(fd)
            fd = -1  # mark as closed
            os.replace(tmp_path, str(path))
        except Exception:
            if fd >= 0:
                os.close(fd)
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        return EditResult(
            success=False,
            lines_changed=0,
            errors=[f"Error: cannot write {file_path}: {e}"],
        )

    return EditResult(success=True, lines_changed=total_changed)


def _check_overlaps(edits: list[EditOperation]) -> list[str]:
    """Check for overlapping edit ranges. Returns error messages."""
    errors: list[str] = []
    sorted_edits = sorted(edits, key=lambda e: e.start_line)

    for i in range(len(sorted_edits) - 1):
        current = sorted_edits[i]
        next_edit = sorted_edits[i + 1]
        if current.end_line >= next_edit.start_line:
            errors.append(
                f"Overlap detected: [{current.start_line}, {current.end_line}] "
                f"and [{next_edit.start_line}, {next_edit.end_line}]"
            )

    return errors


def _verify_hashes(file_lines: list[str], edits: list[EditOperation]) -> list[str]:
    """Verify all content hashes match current file. Returns error messages."""
    errors: list[str] = []

    for edit in edits:
        expected_count = edit.end_line - edit.start_line + 1
        if len(edit.hashes) != expected_count:
            errors.append(
                f"Hash count mismatch for range [{edit.start_line}, {edit.end_line}]: "
                f"expected {expected_count}, got {len(edit.hashes)}"
            )
            continue

        for i, line_num in enumerate(range(edit.start_line, edit.end_line + 1)):
            if line_num > len(file_lines):
                errors.append(
                    f"Line {line_num} beyond end of file ({len(file_lines)} lines)"
                )
                continue

            actual_hash = hash_line(file_lines[line_num - 1].encode("utf-8"))
            if actual_hash != edit.hashes[i]:
                errors.append(
                    f"Hash mismatch at line {line_num}: "
                    f"expected {edit.hashes[i]}, actual {actual_hash}"
                )

    return errors


def _split_new_content(content: str) -> list[str]:
    """Split new content into lines suitable for insertion.

    Ensures each line has a trailing newline, matching file_lines format.
    """
    if not content:
        return []

    lines = content.splitlines(keepends=True)

    # If content ends with newline, splitlines(keepends=True) handles it.
    # If not, add trailing newline to last line.
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"

    return lines
