"""Agent conversation trace sink: writes JSONL event log per orchestrator run.

Each debug run produces a file at audit_dir/agent_{run_id}.jsonl containing
one JSON object per line, recording the full agent–model conversation:
session.init, assistant.message, tool.use, tool.error, and session.result.

Requirements: 103-REQ-1.1 through 103-REQ-8.2
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.knowledge.audit import AuditEvent
    from agent_fox.knowledge.sink import SessionOutcome, ToolCall, ToolError

logger = logging.getLogger("agent_fox.knowledge.agent_trace")


def reconstruct_transcript(
    audit_dir: Path,
    run_id: str,
    node_id: str,
) -> str:
    """Read the agent trace JSONL file and reconstruct the full conversation
    transcript for a given node_id.

    Filters events to event_type == 'assistant.message' and matching node_id.
    Returns concatenated content strings separated by double newlines.
    Returns empty string if the file does not exist or contains no matching
    events.

    Requirements: 113-REQ-1.1, 113-REQ-1.E1, 113-REQ-1.E2
    """
    jsonl_path = audit_dir / f"agent_{run_id}.jsonl"
    if not jsonl_path.exists():
        logger.warning(
            "Agent trace file not found: %s, falling back to alternative transcript source",
            jsonl_path,
        )
        return ""

    messages: list[str] = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    event.get("event_type") == "assistant.message"
                    and event.get("node_id") == node_id
                ):
                    content = event.get("content", "")
                    if content:
                        messages.append(content)
    except OSError:
        logger.warning(
            "Failed to read agent trace file: %s",
            jsonl_path,
            exc_info=True,
        )
        return ""

    if not messages:
        logger.debug(
            "No assistant messages found for node_id=%s in %s",
            node_id,
            jsonl_path,
        )
        return ""

    return "\n\n".join(messages)


def truncate_tool_input(
    tool_input: dict[str, Any],
    max_len: int = 10_000,
) -> dict[str, Any]:
    """Return a shallow copy with string values truncated to max_len chars.

    String values exceeding max_len are shortened to exactly max_len characters
    with ' [truncated]' appended. Non-string values are preserved unchanged.
    All keys are preserved.

    Requirements: 103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1
    """
    result: dict[str, Any] = {}
    for key, value in tool_input.items():
        if isinstance(value, str) and len(value) > max_len:
            result[key] = value[:max_len] + " [truncated]"
        else:
            result[key] = value
    return result


class AgentTraceSink:
    """SessionSink that writes conversation-level trace events to JSONL.

    Creates audit_dir/agent_{run_id}.jsonl on first write, creating the
    directory if it does not exist. I/O errors are caught and logged as
    warnings so that session execution is never interrupted.

    Requirements: 103-REQ-1.2, 103-REQ-1.3, 103-REQ-1.E1, 103-REQ-1.E2
    """

    def __init__(self, audit_dir: Path, run_id: str) -> None:
        self._audit_dir = audit_dir
        self._run_id = run_id
        self._file_handle: IO[str] | None = None
        self._path: Path | None = None

    # -- Internal helpers -----------------------------------------------------

    def _ensure_file(self, run_id: str) -> bool:
        """Open the trace file on first write, creating the directory if needed.

        Uses the method-level run_id for the filename, falling back to the
        constructor run_id if the method-level one is empty.

        Returns True if the file handle is ready, False on failure.

        Requirements: 103-REQ-1.E1, 103-REQ-1.E2
        """
        if self._file_handle is not None:
            return True
        effective_run_id = run_id or self._run_id
        try:
            self._audit_dir.mkdir(parents=True, exist_ok=True)
            self._path = self._audit_dir / f"agent_{effective_run_id}.jsonl"
            self._file_handle = open(self._path, "a")  # noqa: SIM115
            return True
        except Exception:
            logger.warning("Failed to create agent trace file", exc_info=True)
            return False

    def _write_event(self, event_type: str, run_id: str, data: dict[str, Any]) -> None:
        """Serialize and write a single JSON line to the trace file.

        Flushes after every write. Catches and logs any I/O error without
        re-raising so the session can continue.

        Requirements: 103-REQ-1.3, 103-REQ-1.E2
        """
        try:
            if not self._ensure_file(run_id):
                return
            timestamp = datetime.now(UTC).isoformat()
            record: dict[str, Any] = {
                "event_type": event_type,
                "run_id": run_id,
                "timestamp": timestamp,
                **data,
            }
            line = json.dumps(record)
            assert self._file_handle is not None  # guaranteed by _ensure_file
            self._file_handle.write(line + "\n")
            self._file_handle.flush()
        except Exception:
            logger.warning(
                "Failed to write %s trace event",
                event_type,
                exc_info=True,
            )

    # -- Trace-specific methods -----------------------------------------------

    def record_session_init(
        self,
        *,
        run_id: str,
        node_id: str,
        model_id: str,
        archetype: str,
        system_prompt: str,
        task_prompt: str,
    ) -> None:
        """Emit a session.init event before backend execution begins.

        Captures the full system and task prompts verbatim (no truncation).

        Requirements: 103-REQ-2.1, 103-REQ-2.2
        """
        self._write_event(
            "session.init",
            run_id,
            {
                "node_id": node_id,
                "model_id": model_id,
                "archetype": archetype,
                "system_prompt": system_prompt,
                "task_prompt": task_prompt,
            },
        )

    def record_assistant_message(
        self,
        *,
        run_id: str,
        node_id: str,
        content: str,
    ) -> None:
        """Emit an assistant.message event for each model response.

        Captures content verbatim, including any [thinking] prefix.

        Requirements: 103-REQ-3.1, 103-REQ-3.2
        """
        self._write_event(
            "assistant.message",
            run_id,
            {
                "node_id": node_id,
                "content": content,
            },
        )

    def record_tool_use(
        self,
        *,
        run_id: str,
        node_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Emit a tool.use event with truncated string input values.

        String values in tool_input exceeding 10,000 characters are truncated.
        Non-string values are passed through unchanged.

        Requirements: 103-REQ-4.1, 103-REQ-4.2, 103-REQ-4.3, 103-REQ-4.E1
        """
        self._write_event(
            "tool.use",
            run_id,
            {
                "node_id": node_id,
                "tool_name": tool_name,
                "tool_input": truncate_tool_input(tool_input),
            },
        )

    def record_tool_error_trace(
        self,
        *,
        run_id: str,
        node_id: str,
        tool_name: str,
        error_message: str,
    ) -> None:
        """Emit a tool.error event when a session ends due to a tool failure.

        Requirements: 103-REQ-5.1
        """
        self._write_event(
            "tool.error",
            run_id,
            {
                "node_id": node_id,
                "tool_name": tool_name,
                "error_message": error_message,
            },
        )

    def record_session_result(
        self,
        *,
        run_id: str,
        node_id: str,
        status: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int,
        cache_creation_input_tokens: int,
        duration_ms: int,
        is_error: bool,
        error_message: str | None,
    ) -> None:
        """Emit a session.result event with terminal metrics.

        Requirements: 103-REQ-6.1
        """
        self._write_event(
            "session.result",
            run_id,
            {
                "node_id": node_id,
                "status": status,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "duration_ms": duration_ms,
                "is_error": is_error,
                "error_message": error_message,
            },
        )

    # -- SessionSink protocol no-ops ------------------------------------------

    def record_session_outcome(self, outcome: SessionOutcome) -> None:
        """No-op — session telemetry handled by DuckDBSink."""

    def record_tool_call(self, call: ToolCall) -> None:
        """No-op — tool telemetry handled by DuckDBSink."""

    def record_tool_error(self, error: ToolError) -> None:
        """No-op — tool errors handled by DuckDBSink."""

    def emit_audit_event(self, event: AuditEvent) -> None:
        """No-op — audit events handled by AuditJsonlSink and DuckDBSink."""

    def close(self) -> None:
        """Flush and close the trace file handle.

        Requirements: 103-REQ-1.3
        """
        if self._file_handle is not None:
            try:
                self._file_handle.flush()
                self._file_handle.close()
            except Exception:
                logger.warning("Failed to close agent trace file", exc_info=True)
            finally:
                self._file_handle = None
