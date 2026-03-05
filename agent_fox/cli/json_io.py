"""JSON I/O helpers for the global --json flag.

Provides functions for emitting JSON output to stdout (single objects,
JSONL lines, error envelopes) and reading JSON input from stdin.

Requirements: 23-REQ-6.1, 23-REQ-7.1, 23-REQ-7.3
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click


def emit(data: dict[str, Any]) -> None:
    """Write a single JSON object to stdout, followed by newline.

    Uses indented (pretty-printed) format for readability.
    Non-serializable values are converted via ``str()``.

    Args:
        data: Dictionary to serialize as JSON.
    """
    click.echo(json.dumps(data, indent=2, default=str))


def emit_line(data: dict[str, Any]) -> None:
    """Write a compact JSON object to stdout (JSONL mode, no indent).

    Each call produces exactly one line of output, suitable for
    streaming / JSONL consumers.

    Args:
        data: Dictionary to serialize as JSON.
    """
    click.echo(json.dumps(data, default=str))


def emit_error(message: str) -> None:
    """Write an error envelope ``{"error": "<message>"}`` to stdout.

    Args:
        message: Human-readable error description.
    """
    click.echo(json.dumps({"error": message}))


def read_stdin() -> dict[str, Any]:
    """Read a JSON object from stdin if input is piped (not a TTY).

    Returns an empty dict when stdin is a TTY (interactive terminal)
    or when piped input is empty, so callers never block.

    Returns:
        Parsed JSON dict, or ``{}`` if no input is available.

    Raises:
        json.JSONDecodeError: If stdin contains invalid JSON.
    """
    if sys.stdin.isatty():
        return {}
    text = sys.stdin.read().strip()
    if not text:
        return {}
    return json.loads(text)  # type: ignore[no-any-return]
