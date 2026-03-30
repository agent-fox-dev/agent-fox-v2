"""Post-session quality gate execution and result recording.

Runs a configurable shell command after each coder session and records the
result as an informational audit event.

Requirements: 54-REQ-1.1, 54-REQ-1.2, 54-REQ-1.3, 54-REQ-1.E1, 54-REQ-1.E2,
              54-REQ-2.1, 54-REQ-2.2, 54-REQ-2.3, 54-REQ-2.E1
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from agent_fox.core.config import OrchestratorConfig

logger = logging.getLogger(__name__)

_MAX_OUTPUT_LINES = 50


@dataclass(frozen=True)
class QualityGateResult:
    """Result of a quality gate command execution.

    Requirements: 54-REQ-2.1
    """

    exit_code: int  # -1 for timeout, -2 for command not found
    stdout_tail: str  # last 50 lines of stdout
    stderr_tail: str  # last 50 lines of stderr
    duration_ms: int
    passed: bool  # True iff exit_code == 0


def _tail_lines(text: str, n: int = _MAX_OUTPUT_LINES) -> str:
    """Return the last *n* lines of *text*.

    Requirements: 54-REQ-1.E2
    """
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return "\n".join(lines[-n:])


def run_quality_gate(
    config: OrchestratorConfig,
    *,
    project_root: str = ".",
) -> QualityGateResult | None:
    """Execute the quality gate command and return the result.

    Returns None when quality_gate is not configured (empty string).
    On timeout: records exit_code=-1.
    On FileNotFoundError: records exit_code=-2 and logs a warning.

    Requirements: 54-REQ-1.1, 54-REQ-1.2, 54-REQ-1.3, 54-REQ-1.E1, 54-REQ-1.E2
    """
    command = config.quality_gate
    if not command:
        # 54-REQ-1.3: skip entirely when not configured
        return None

    timeout = config.quality_gate_timeout
    start = time.monotonic()

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout_tail = _tail_lines(proc.stdout or "")
        stderr_tail = _tail_lines(proc.stderr or "")
        exit_code = proc.returncode
        passed = exit_code == 0
        return QualityGateResult(
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            duration_ms=duration_ms,
            passed=passed,
        )

    except subprocess.TimeoutExpired:
        # 54-REQ-1.2: timeout → exit_code=-1
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Quality gate command timed out after %ds: %s", timeout, command)
        return QualityGateResult(
            exit_code=-1,
            stdout_tail="",
            stderr_tail="",
            duration_ms=duration_ms,
            passed=False,
        )

    except FileNotFoundError:
        # 54-REQ-1.E1: command not found → exit_code=-2
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Quality gate command not found: %s", command)
        return QualityGateResult(
            exit_code=-2,
            stdout_tail="",
            stderr_tail="",
            duration_ms=duration_ms,
            passed=False,
        )


def build_gate_audit_payload(
    result: QualityGateResult,
    *,
    command: str,
) -> dict[str, Any]:
    """Build the payload for a quality_gate.result audit event.

    Requirements: 54-REQ-2.1
    """
    return {
        "exit_code": result.exit_code,
        "stdout_tail": result.stdout_tail,
        "stderr_tail": result.stderr_tail,
        "duration_ms": result.duration_ms,
        "passed": result.passed,
        "command": command,
    }


def emit_gate_result(
    *,
    result: QualityGateResult,
    command: str,
    sink_dispatcher: Any | None,
    run_id: str,
    node_id: str,
) -> None:
    """Log the quality gate result and optionally emit an audit event.

    When sink_dispatcher is None or run_id is empty, the result is logged
    at info level but no audit event is emitted.

    Requirements: 54-REQ-2.1, 54-REQ-2.E1
    """
    status_word = "passed" if result.passed else "FAILED"
    logger.info(
        "Quality gate %s (exit_code=%d, duration=%dms): %s",
        status_word,
        result.exit_code,
        result.duration_ms,
        command,
    )

    if sink_dispatcher is None or not run_id:
        # 54-REQ-2.E1: no audit event when sink is absent or run_id is empty
        return

    from agent_fox.knowledge.audit import AuditEvent, AuditEventType, AuditSeverity

    payload = build_gate_audit_payload(result, command=command)
    event = AuditEvent(
        run_id=run_id,
        event_type=AuditEventType.QUALITY_GATE_RESULT,
        severity=AuditSeverity.INFO if result.passed else AuditSeverity.WARNING,
        node_id=node_id,
        payload=payload,
    )
    try:
        sink_dispatcher.emit_audit_event(event)
    except Exception:
        logger.warning("Failed to emit quality_gate.result audit event", exc_info=True)


def gate_session_status(result: QualityGateResult) -> str:
    """Return the session status string based on the quality gate result.

    Returns "completed" on success, "completed_with_gate_failure" on failure.

    Requirements: 54-REQ-2.2
    """
    return "completed" if result.passed else "completed_with_gate_failure"
