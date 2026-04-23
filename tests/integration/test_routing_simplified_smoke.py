"""Integration smoke tests for spec 89: Simplify Model Routing.

Verifies that the full orchestrator dispatch path creates an escalation
ladder from archetype defaults without importing any removed prediction
pipeline modules.

Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-2.1,
              89-REQ-5.3

Test spec: TS-89-SMOKE-1
"""

from __future__ import annotations

import sys

import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import ModelTier

# ---------------------------------------------------------------------------
# TS-89-SMOKE-1: Orchestrator dispatch creates ladder without pipeline
# Execution Path 1 from design.md
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_dispatch_creates_ladder_without_pipeline() -> None:
    """Dispatching a node creates an EscalationLadder at the config-resolved tier.

    Uses a real AssessmentManager and EscalationLadder (not mocked).
    Verifies that no removed prediction pipeline modules are imported
    during the dispatch.

    Requirements: 89-REQ-1.1, 89-REQ-1.2, 89-REQ-1.3, 89-REQ-2.1
    """
    from agent_fox.engine.engine import AssessmentManager

    config = AgentFoxConfig()
    manager = AssessmentManager(retries_before_escalation=1, config=config)

    # Dispatch a node with archetype "coder" (config default: ADVANCED)
    await manager.assess_node("test_spec:1", "coder")

    # Verify: ladder exists and was created at config-resolved tier
    assert "test_spec:1" in manager.ladders, (
        "assess_node() must create an escalation ladder without a prediction pipeline"
    )

    ladder = manager.ladders["test_spec:1"]

    # 89-REQ-1.1: starting tier is config-resolved (ADVANCED for coder with default config)
    assert ladder.current_tier == ModelTier.ADVANCED, f"Expected ADVANCED (config default), got {ladder.current_tier}"

    # 89-REQ-1.2: tier ceiling is always ADVANCED
    assert ladder._tier_ceiling == ModelTier.ADVANCED, f"Expected ADVANCED ceiling, got {ladder._tier_ceiling}"

    # 89-REQ-2.1: no removed modules were imported during execution
    removed_modules = [
        "agent_fox.routing.assessor",
        "agent_fox.routing.features",
        "agent_fox.routing.calibration",
        "agent_fox.routing.duration",
    ]
    for module_name in removed_modules:
        assert module_name not in sys.modules, f"Removed module '{module_name}' was imported during dispatch"


@pytest.mark.asyncio
async def test_ladder_escalates_on_repeated_failure() -> None:
    """After repeated failures, the ladder escalates tiers as expected.

    Verifies that the escalation ladder behavior (Property 4 from design.md)
    is preserved after the prediction pipeline is removed.

    Requirements: 89-REQ-1.1, 89-REQ-1.2
    """
    from agent_fox.engine.engine import AssessmentManager

    # Use reviewer (no config mapping, starts at STANDARD) to test escalation
    config = AgentFoxConfig()
    manager = AssessmentManager(retries_before_escalation=0, config=config)
    await manager.assess_node("test_spec:1", "reviewer")

    ladder = manager.ladders["test_spec:1"]
    assert ladder.current_tier == ModelTier.STANDARD

    # One failure should escalate from STANDARD to ADVANCED (with retries=0)
    ladder.record_failure()
    assert ladder.current_tier == ModelTier.ADVANCED, (
        "After 1 failure with retries_before_escalation=0, should escalate to ADVANCED"
    )

    # Another failure at ADVANCED should exhaust the ladder
    ladder.record_failure()
    assert ladder.is_exhausted, "After exhausting ADVANCED tier, ladder should be exhausted"


@pytest.mark.asyncio
async def test_no_pipeline_modules_imported_after_assess() -> None:
    """Calling assess_node does not cause any prediction pipeline module to be imported.

    Requirements: 89-REQ-2.1
    """
    # Record which modules were loaded before the call
    before = set(sys.modules.keys())

    from agent_fox.engine.engine import AssessmentManager

    config = AgentFoxConfig()
    manager = AssessmentManager(retries_before_escalation=1, config=config)
    await manager.assess_node("some_spec:2", "oracle")

    after = set(sys.modules.keys())
    new_modules = after - before

    pipeline_modules = {
        "agent_fox.routing.assessor",
        "agent_fox.routing.features",
        "agent_fox.routing.calibration",
        "agent_fox.routing.duration",
    }
    imported_pipeline_modules = new_modules & pipeline_modules
    assert not imported_pipeline_modules, (
        f"Prediction pipeline modules were imported during assess_node(): {imported_pipeline_modules}"
    )
