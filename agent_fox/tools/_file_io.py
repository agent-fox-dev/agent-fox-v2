"""Shared file validation and reading for fox tools.

Extracts the duplicated file-existence, is-file, and encoding-fallback
logic used by fox_read, fox_search, and fox_edit.
"""

from __future__ import annotations

from pathlib import Path


def validate_file(path: Path, *, writable: bool = False) -> str | None:
    """Check that *path* exists and is a regular file.

    When *writable* is True also checks write permission.

    Returns an error string on failure, or ``None`` on success.
    """
    if not path.exists():
        return f"Error: file not found: {path}"
    if not path.is_file():
        return f"Error: not a file: {path}"
    if writable:
        import os

        if not os.access(path, os.W_OK):
            return f"Error: file not writable: {path}"
    return None


def read_text_lossy(path: Path) -> tuple[str, str | None]:
    """Read a text file with UTF-8, falling back to latin-1.

    Returns ``(text, error)``.  On success *error* is ``None``.
    On failure *text* is empty and *error* contains the message.
    """
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1"), None
        except Exception as e:
            return "", f"Error: cannot read {path}: {e}"
    except OSError as e:
        return "", f"Error: cannot read {path}: {e}"
