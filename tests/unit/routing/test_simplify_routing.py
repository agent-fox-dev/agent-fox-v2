"""Tests for spec 89: Simplify Model Routing.

Verifies that the prediction pipeline is removed, escalation ladders are
always created from archetype defaults, and no regressions are introduced.

Requirements: 89-REQ-1.*, 89-REQ-2.*, 89-REQ-3.*, 89-REQ-4.*,
              89-REQ-5.*, 89-REQ-6.*, 89-REQ-7.*

Test spec entries: TS-89-1 through TS-89-13, TS-89-E1,
                   TS-89-P1 through TS-89-P5
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

from agent_fox.core.models import ModelTier

# ---------------------------------------------------------------------------
# TS-89-1: AssessmentManager creates ladder from archetype default
# Requirement: 89-REQ-1.1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ladder_from_archetype_default() -> None:
    """assess_node() creates an EscalationLadder at the coder default tier."""
    from agent_fox.engine.assessment import AssessmentManager

    # Simplified constructor: only retries_before_escalation (no pipeline param)
    manager = AssessmentManager(retries_before_escalation=1)
    await manager.assess_node("some_spec:1", "coder")

    ladder = manager.ladders["some_spec:1"]
    assert ladder.current_tier == ModelTier.STANDARD


# ---------------------------------------------------------------------------
# TS-89-2: Ladder tier ceiling is ADVANCED
# Requirement: 89-REQ-1.2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ladder_ceiling_advanced() -> None:
    """Escalation ladder tier_ceiling is always ADVANCED."""
    from agent_fox.engine.assessment import AssessmentManager

    manager = AssessmentManager(retries_before_escalation=1)
    await manager.assess_node("some_spec:1", "oracle")

    ladder = manager.ladders["some_spec:1"]
    assert ladder._tier_ceiling == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-89-3: assess_node always creates ladder (no pipeline dependency)
# Requirement: 89-REQ-1.3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ladder_created_without_pipeline() -> None:
    """assess_node() creates a ladder even when no pipeline exists."""
    from agent_fox.engine.assessment import AssessmentManager

    manager = AssessmentManager(retries_before_escalation=2)
    await manager.assess_node("spec:2", "skeptic")

    assert "spec:2" in manager.ladders
    # skeptic default tier is ADVANCED
    assert manager.ladders["spec:2"].current_tier == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-89-4: Prediction pipeline modules deleted
# Requirement: 89-REQ-2.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path",
    [
        "agent_fox.routing.assessor",
        "agent_fox.routing.features",
        "agent_fox.routing.calibration",
        "agent_fox.routing.duration",
        "agent_fox.routing.core",
    ],
)
def test_pipeline_modules_deleted(module_path: str) -> None:
    """Importing removed prediction pipeline modules raises ImportError."""
    with pytest.raises(ImportError):
        importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# TS-89-7: No AssessmentPipeline in run.py
# Requirement: 89-REQ-2.3
# ---------------------------------------------------------------------------


def test_no_assessment_pipeline_in_run() -> None:
    """run.py does not import or reference AssessmentPipeline."""
    source = Path("agent_fox/engine/run.py").read_text()
    assert "AssessmentPipeline" not in source, "agent_fox/engine/run.py must not reference AssessmentPipeline"


# ---------------------------------------------------------------------------
# TS-89-8: No record_node_outcome in result handler
# Requirement: 89-REQ-3.1
# ---------------------------------------------------------------------------


def test_no_record_node_outcome() -> None:
    """SessionResultHandler has no record_node_outcome method."""
    from agent_fox.engine.result_handler import SessionResultHandler

    assert not hasattr(SessionResultHandler, "record_node_outcome"), (
        "SessionResultHandler must not have record_node_outcome method"
    )


# ---------------------------------------------------------------------------
# TS-89-9: No routing_pipeline in SessionResultHandler.__init__
# Requirement: 89-REQ-3.2
# ---------------------------------------------------------------------------


def test_routing_pipeline_param_present() -> None:
    """SessionResultHandler.__init__ accepts routing_pipeline (added in #325)."""
    from agent_fox.engine.result_handler import SessionResultHandler

    sig = inspect.signature(SessionResultHandler.__init__)
    assert "routing_pipeline" in sig.parameters, "SessionResultHandler.__init__ must have routing_pipeline parameter"


# ---------------------------------------------------------------------------
# TS-89-10: Prediction-only config fields removed
# Requirements: 89-REQ-4.1, 89-REQ-4.2
# ---------------------------------------------------------------------------


def test_prediction_config_fields_removed() -> None:
    """RoutingConfig does not have training_threshold, accuracy_threshold, retrain_interval."""
    from agent_fox.core.config import RoutingConfig

    fields = RoutingConfig.model_fields
    assert "training_threshold" not in fields, "RoutingConfig.training_threshold must be removed"
    assert "accuracy_threshold" not in fields, "RoutingConfig.accuracy_threshold must be removed"
    assert "retrain_interval" not in fields, "RoutingConfig.retrain_interval must be removed"


def test_retries_config_retained() -> None:
    """RoutingConfig retains retries_before_escalation."""
    from agent_fox.core.config import RoutingConfig

    fields = RoutingConfig.model_fields
    assert "retries_before_escalation" in fields, "RoutingConfig.retries_before_escalation must be retained"


# ---------------------------------------------------------------------------
# TS-89-11: Prediction pipeline test files deleted
# Requirement: 89-REQ-5.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "test_path",
    [
        "tests/test_routing/test_assessor.py",
        "tests/test_routing/test_features.py",
        "tests/test_routing/test_calibration.py",
        "tests/test_routing/test_storage.py",
        "tests/test_routing/test_integration.py",
    ],
)
def test_pipeline_test_files_deleted(test_path: str) -> None:
    """Test files for removed prediction pipeline modules do not exist."""
    assert not Path(test_path).exists(), f"{test_path} must be deleted (prediction pipeline test)"


# ---------------------------------------------------------------------------
# TS-89-12: No duration imports in engine or CLI
# Requirement: 89-REQ-6.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source_path",
    [
        "agent_fox/engine/engine.py",
        "agent_fox/cli/status.py",
    ],
)
def test_no_duration_imports(source_path: str) -> None:
    """engine.py and status.py do not import from routing.duration."""
    source = Path(source_path).read_text()
    assert "routing.duration" not in source, f"{source_path} must not import from agent_fox.routing.duration"


# ---------------------------------------------------------------------------
# TS-89-13: Superseded specs have deprecation banners
# Requirement: 89-REQ-7.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec_dir",
    [
        ".specs/archive/30_adaptive_model_routing",
        ".specs/archive/57_archetype_model_tiers",
    ],
)
def test_superseded_specs_have_banners(spec_dir: str) -> None:
    """Archived specs 30 and 57 have SUPERSEDED deprecation banners."""
    spec_path = Path(spec_dir)
    md_files = list(spec_path.glob("*.md"))
    assert md_files, f"No .md files found in {spec_dir}"

    for md_file in md_files:
        lines = md_file.read_text().splitlines()
        first_five = "\n".join(lines[:5])
        assert "SUPERSEDED" in first_five, f"{md_file} must have a SUPERSEDED deprecation banner in the first 5 lines"


# ---------------------------------------------------------------------------
# TS-89-E1: Unknown archetype defaults to coder
# Requirement: 89-REQ-1.E1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_archetype_defaults_to_coder() -> None:
    """assess_node with unknown archetype creates ladder at STANDARD (coder fallback)."""
    from agent_fox.engine.assessment import AssessmentManager

    manager = AssessmentManager(retries_before_escalation=1)
    await manager.assess_node("spec:1", "nonexistent_archetype")

    ladder = manager.ladders["spec:1"]
    # Coder default is STANDARD
    assert ladder.current_tier == ModelTier.STANDARD


# ---------------------------------------------------------------------------
# TS-89-P1: Archetype tier always becomes ladder starting tier (property)
# Validates: 89-REQ-1.1, 89-REQ-1.2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prop_archetype_tier_becomes_ladder() -> None:
    """For any archetype in the registry, assess_node creates a ladder at the default tier."""
    from agent_fox.archetypes import ARCHETYPE_REGISTRY
    from agent_fox.engine.assessment import AssessmentManager

    for archetype_name, entry in ARCHETYPE_REGISTRY.items():
        manager = AssessmentManager(retries_before_escalation=1)
        node_id = "test_spec:1"
        await manager.assess_node(node_id, archetype_name)

        ladder = manager.ladders[node_id]
        expected = ModelTier(entry.default_model_tier)
        assert ladder.current_tier == expected, (
            f"Archetype '{archetype_name}': expected tier {expected}, got {ladder.current_tier}"
        )


# ---------------------------------------------------------------------------
# TS-89-P2: Prediction pipeline modules not importable (property)
# Validates: 89-REQ-2.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path",
    [
        "agent_fox.routing.assessor",
        "agent_fox.routing.features",
        "agent_fox.routing.calibration",
        "agent_fox.routing.duration",
    ],
)
def test_prop_pipeline_modules_not_importable(module_path: str) -> None:
    """All removed prediction pipeline modules raise ImportError when imported."""
    with pytest.raises(ImportError):
        importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# TS-89-P4: Escalation behavior preserved (property)
# Validates: 89-REQ-1.1, 89-REQ-1.2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("retries", [0, 1, 2, 3])
@pytest.mark.parametrize("start", [ModelTier.SIMPLE, ModelTier.STANDARD])
def test_prop_escalation_preserved(retries: int, start: ModelTier) -> None:
    """After retries_before_escalation + 1 failures, tier escalates."""
    from agent_fox.routing.escalation import EscalationLadder

    ladder = EscalationLadder(
        starting_tier=start,
        tier_ceiling=ModelTier.ADVANCED,
        retries_before_escalation=retries,
    )

    # Record enough failures to trigger escalation
    for _ in range(retries + 1):
        ladder.record_failure()

    # Tier should have escalated past start
    tier_order = [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]
    assert tier_order.index(ladder.current_tier) > tier_order.index(start), (
        f"Ladder starting at {start} with {retries} retries should escalate "
        f"after {retries + 1} failures; current tier is {ladder.current_tier}"
    )


# ---------------------------------------------------------------------------
# TS-89-P5: Unknown archetype always falls back to coder (property)
# Validates: 89-REQ-1.E1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["xyz", "unknown", "foo_bar", "not_in_registry_at_all"],
)
def test_prop_unknown_archetype_fallback(name: str) -> None:
    """Any archetype name not in the registry yields coder defaults (STANDARD)."""
    from agent_fox.archetypes import ARCHETYPE_REGISTRY
    from agent_fox.session.archetypes import get_archetype

    assert name not in ARCHETYPE_REGISTRY, f"'{name}' must not be in registry for this test"
    entry = get_archetype(name)
    assert entry.default_model_tier == "STANDARD", (
        f"Unknown archetype '{name}' should fall back to STANDARD (coder default), got {entry.default_model_tier!r}"
    )
