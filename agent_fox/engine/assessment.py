"""Complexity assessment and escalation ladder management.

Extracted from engine.py to reduce the Orchestrator class size.
Manages the adaptive routing state: creating escalation ladders from
archetype default tiers for retry logic.

Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-1.E1
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.archetypes import get_archetype
from agent_fox.core.models import ModelTier

logger = logging.getLogger(__name__)


class AssessmentManager:
    """Manages escalation ladders for nodes based on archetype default tiers.

    Creates an EscalationLadder for each node using the archetype's
    default_model_tier, with tier_ceiling always set to ADVANCED.

    Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-1.E1
    """

    def __init__(
        self,
        retries_before_escalation: int,
    ) -> None:
        self.ladders: dict[str, Any] = {}
        self.retries_before_escalation = retries_before_escalation

    async def assess_node(
        self,
        node_id: str,
        archetype: str,
    ) -> None:
        """Create an escalation ladder from the archetype's default tier.

        Always creates a ladder with starting_tier from the archetype
        registry and tier_ceiling set to ADVANCED.

        Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-1.E1
        """
        if node_id in self.ladders:
            return  # Already assessed

        from agent_fox.routing.escalation import EscalationLadder

        # 89-REQ-1.2: Tier ceiling is always ADVANCED
        tier_ceiling = ModelTier.ADVANCED

        # 89-REQ-1.1: Use archetype default tier as starting tier
        # 89-REQ-1.E1: Fall back to coder (STANDARD) for unknown archetypes
        try:
            entry = get_archetype(archetype)
            starting_tier = ModelTier(entry.default_model_tier)
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
