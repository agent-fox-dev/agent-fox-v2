"""Escalation ladder management for task nodes.

Requirements: 89-REQ-1, 30-REQ-5.1, 30-REQ-7.1, 30-REQ-7.2
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import ModelTier

logger = logging.getLogger(__name__)


class AssessmentManager:
    """Manages escalation ladders for nodes based on archetype default tiers."""

    def __init__(
        self,
        retries_before_escalation: int,
        config: AgentFoxConfig,
    ) -> None:
        self.ladders: dict[str, Any] = {}
        self.retries_before_escalation = retries_before_escalation
        self._config = config

    async def assess_node(
        self,
        node_id: str,
        archetype: str,
        *,
        mode: str | None = None,
    ) -> None:
        """Create an escalation ladder from the resolved model tier."""
        if node_id in self.ladders:
            return

        from agent_fox.core.escalation import EscalationLadder
        from agent_fox.engine.sdk_params import resolve_model_tier

        tier_ceiling = ModelTier.ADVANCED

        try:
            resolved = resolve_model_tier(self._config, archetype, mode=mode)
            starting_tier = ModelTier(resolved)
        except Exception:
            starting_tier = ModelTier.STANDARD

        ladder = EscalationLadder(
            starting_tier=starting_tier,
            tier_ceiling=tier_ceiling,
            retries_before_escalation=self.retries_before_escalation,
        )
        self.ladders[node_id] = ladder

        logger.debug(
            "Created escalation ladder for %s: starting_tier=%s ceiling=%s",
            node_id,
            starting_tier,
            tier_ceiling,
        )
