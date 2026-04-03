"""Complexity assessment and escalation ladder management.

Extracted from engine.py to reduce the Orchestrator class size.
Manages the adaptive routing state: assessing node complexity before
dispatch and creating escalation ladders for retry logic.

Requirements: 30-REQ-7.1, 30-REQ-7.E1, 57-REQ-2.1, 57-REQ-2.E1
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_fox.core.models import ModelTier
from agent_fox.core.node_id import parse_node_id
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.session.archetypes import get_archetype

logger = logging.getLogger(__name__)


class AssessmentManager:
    """Manages complexity assessment and escalation ladders for nodes.

    Encapsulates the adaptive routing state and assessment logic that
    was previously embedded in the Orchestrator class.

    Requirements: 30-REQ-7.1, 30-REQ-7.E1, 57-REQ-2.1
    """

    def __init__(
        self,
        routing_config: Any,
        pipeline: Any | None,
        retries_before_escalation: int,
    ) -> None:
        self.config = routing_config
        self.pipeline = pipeline
        self.ladders: dict[str, Any] = {}
        self.assessments: dict[str, Any] = {}
        self.retries_before_escalation = retries_before_escalation

    async def assess_node(
        self,
        node_id: str,
        archetype: str,
        *,
        emit_audit: Callable[..., None] | None = None,
    ) -> None:
        """Run complexity assessment for a node and create an escalation ladder.

        The assessment pipeline is called before the first dispatch of a node.
        On any failure, falls back to the archetype default tier (30-REQ-7.E1).

        When no assessment pipeline is configured, no ladder is created and
        the orchestrator falls back to legacy retry behaviour.

        Requirements: 30-REQ-7.1, 30-REQ-7.E1
        """
        if node_id in self.ladders:
            return  # Already assessed

        if self.pipeline is None:
            return

        from agent_fox.routing.escalation import EscalationLadder

        # 57-REQ-2.1: Tier ceiling is always ADVANCED regardless of archetype default
        tier_ceiling = ModelTier.ADVANCED

        # Determine archetype default tier for use as fallback
        try:
            entry = get_archetype(archetype)
            archetype_default_tier = ModelTier(entry.default_model_tier)
        except Exception:
            archetype_default_tier = ModelTier.STANDARD

        # 30-REQ-7.1: Run assessment before session creation
        predicted_tier = archetype_default_tier  # fallback (57-REQ-2.E1)
        try:
            parsed = parse_node_id(node_id)
            spec_name = parsed.spec_name
            task_group = parsed.group_number or 1
            spec_dir = Path(".specs") / spec_name

            assessment = await self.pipeline.assess(
                node_id=node_id,
                spec_name=spec_name,
                task_group=task_group,
                spec_dir=spec_dir,
                archetype=archetype,
                tier_ceiling=tier_ceiling,
            )
            predicted_tier = assessment.predicted_tier
            self.assessments[node_id] = assessment

            logger.info(
                "Adaptive routing for %s: predicted_tier=%s confidence=%.2f method=%s ceiling=%s",
                node_id,
                predicted_tier,
                assessment.confidence,
                assessment.assessment_method,
                tier_ceiling,
            )
            # 40-REQ-10.2: Emit model.assessment audit event
            if emit_audit is not None:
                emit_audit(
                    AuditEventType.MODEL_ASSESSMENT,
                    node_id=node_id,
                    payload={
                        "predicted_tier": predicted_tier.value,
                        "confidence": assessment.confidence,
                        "method": assessment.assessment_method,
                    },
                )
        except Exception:
            # 30-REQ-7.E1 / 57-REQ-2.E1: Fall back to archetype default tier
            logger.error(
                "Assessment pipeline failed for %s, falling back to archetype default tier %s",
                node_id,
                archetype_default_tier,
                exc_info=True,
            )
            predicted_tier = archetype_default_tier

        # Create escalation ladder
        ladder = EscalationLadder(
            starting_tier=predicted_tier,
            tier_ceiling=tier_ceiling,
            retries_before_escalation=self.retries_before_escalation,
        )
        self.ladders[node_id] = ladder
