"""JSONL sink: raw audit trail (debug-only), preserves v1 behavior.

Requirements: 11-REQ-6.1, 11-REQ-6.2, 11-REQ-6.3
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import IO
from uuid import UUID

from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError

logger = logging.getLogger("agent_fox.knowledge.jsonl_sink")


def _json_default(obj: object) -> str:
    """JSON serializer for UUID and datetime objects."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class JsonlSink:
    """SessionSink implementation that appends JSON lines to a file.

    Preserves the v1 debug audit trail behavior. All events are written
    as JSON objects, one per line. The file is opened on first write and
    closed when close() is called.
    """

    def __init__(self, directory: Path, session_id: str = "") -> None:
        self._directory = directory
        self._session_id = session_id
        self._file_handle: IO[str] | None = None
        self._path: Path | None = None

    def _ensure_file(self) -> Path:
        """Create the JSONL file on first write. Returns the file path."""
        if self._path is not None:
            return self._path
        self._directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._session_id}.jsonl"
        self._path = self._directory / filename
        self._file_handle = open(self._path, "a")  # noqa: SIM115
        return self._path

    def _write_event(self, event_type: str, data: dict) -> None:
        """Write a single JSON line to the audit file."""
        try:
            self._ensure_file()
            record = {"event_type": event_type, **data}
            line = json.dumps(record, default=_json_default)
            assert self._file_handle is not None  # guaranteed by _ensure_file
            self._file_handle.write(line + "\n")
            self._file_handle.flush()
        except Exception:
            logger.warning(
                "Failed to write %s event to JSONL",
                event_type,
                exc_info=True,
            )

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """Write session outcome as a JSON line."""
        self._write_event(
            "session_outcome",
            {
                "id": outcome.id,
                "spec_name": outcome.spec_name,
                "task_group": outcome.task_group,
                "node_id": outcome.node_id,
                "touched_paths": outcome.touched_paths,
                "status": outcome.status,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
                "duration_ms": outcome.duration_ms,
                "created_at": outcome.created_at,
            },
        )

    def record_tool_call(self, call: ToolCall) -> None:
        """Write tool call as a JSON line."""
        self._write_event(
            "tool_call",
            {
                "id": call.id,
                "session_id": call.session_id,
                "node_id": call.node_id,
                "tool_name": call.tool_name,
                "called_at": call.called_at,
            },
        )

    def record_tool_error(self, error: ToolError) -> None:
        """Write tool error as a JSON line."""
        self._write_event(
            "tool_error",
            {
                "id": error.id,
                "session_id": error.session_id,
                "node_id": error.node_id,
                "tool_name": error.tool_name,
                "failed_at": error.failed_at,
            },
        )

    def close(self) -> None:
        """Flush and close the JSONL file handle."""
        if self._file_handle is not None:
            try:
                self._file_handle.flush()
                self._file_handle.close()
            except Exception:
                logger.warning(
                    "Failed to close JSONL file",
                    exc_info=True,
                )
            finally:
                self._file_handle = None
