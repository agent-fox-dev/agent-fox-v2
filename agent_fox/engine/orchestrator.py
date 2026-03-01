"""Orchestrator: deterministic execution engine. Zero LLM calls.

Stub module -- implementation in task group 3.
Requirements: 04-REQ-1.1 through 04-REQ-1.4, 04-REQ-2.1 through 04-REQ-2.3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.state import ExecutionState


class Orchestrator:
    """Deterministic execution engine. Zero LLM calls."""

    def __init__(
        self,
        config: OrchestratorConfig,
        plan_path: Path,
        state_path: Path,
        session_runner_factory: Any,
    ) -> None:
        raise NotImplementedError

    async def run(self) -> ExecutionState:
        raise NotImplementedError
