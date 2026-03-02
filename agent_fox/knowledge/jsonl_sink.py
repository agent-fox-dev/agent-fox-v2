"""JSONL sink: raw audit trail (debug-only), preserves v1 behavior.

Requirements: 11-REQ-6.1, 11-REQ-6.2, 11-REQ-6.3
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError

logger = logging.getLogger("agent_fox.knowledge.jsonl_sink")


class JsonlSink:
    """SessionSink implementation that appends JSON lines to a file.

    Preserves the v1 debug audit trail behavior. All events are written
    as JSON objects, one per line. The file is opened on first write and
    closed when close() is called.
    """

    def __init__(self, directory: Path, session_id: str = "") -> None:
        self._directory = directory
        self._session_id = session_id
        self._file_handle: object | None = None
        self._path: Path | None = None

    def _ensure_file(self) -> Path:
        """Create the JSONL file on first write. Returns the file path."""
        raise NotImplementedError

    def _write_event(self, event_type: str, data: dict) -> None:
        """Write a single JSON line to the audit file."""
        raise NotImplementedError

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Write session outcome as a JSON line."""
        raise NotImplementedError

    def record_tool_call(self, call: ToolCall) -> None:
        """Write tool call as a JSON line."""
        raise NotImplementedError

    def record_tool_error(self, error: ToolError) -> None:
        """Write tool error as a JSON line."""
        raise NotImplementedError

    def close(self) -> None:
        """Flush and close the JSONL file handle."""
        raise NotImplementedError
