"""Tests for assessment pipeline.

Test Spec: TS-30-2, TS-30-3, TS-30-4, TS-30-5, TS-30-E1, TS-30-E2,
           TS-30-P6, TS-30-P7
Requirements: 30-REQ-1.1 through 30-REQ-1.6, 30-REQ-1.E1, 30-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.models import ModelTier
from agent_fox.routing.assessor import AssessmentPipeline, heuristic_assess
from agent_fox.routing.types import FeatureVector, RoutingConfig


class TestAssessmentProduction:
    """TS-30-2: Complexity assessment production."""

    @pytest.mark.asyncio
    async def test_assessment_production(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-2: Verify assessment has all required fields.

        Requirement: 30-REQ-1.1
        """
        config = RoutingConfig()
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:2",
            spec_name="test_spec",
            task_group=2,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )

        assert result.id is not None
        assert len(result.id) > 0
        assert result.node_id == "test_spec:2"
        valid_tiers = [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]
        assert result.predicted_tier in valid_tiers
        assert 0.0 <= result.confidence <= 1.0
        assert result.assessment_method == "heuristic"
        assert result.feature_vector is not None
        assert result.tier_ceiling == ModelTier.ADVANCED


class TestHeuristicOnZeroHistory:
    """TS-30-3: Heuristic-only assessment on zero history."""

    @pytest.mark.asyncio
    async def test_heuristic_on_zero_history(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-3: Verify heuristic when no historical data.

        Requirement: 30-REQ-1.3
        """
        config = RoutingConfig(training_threshold=20)
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result.assessment_method == "heuristic"


class TestStatisticalPreferred:
    """TS-30-4: Statistical model preferred when accurate."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_statistical_preferred(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-4: Verify statistical method when accuracy exceeds threshold.

        Requirement: 30-REQ-1.4
        """
        # Populate DB with 30 consistent outcomes for training
        from tests.test_routing.helpers import populate_consistent_outcomes

        populate_consistent_outcomes(routing_db, count=30)

        config = RoutingConfig(training_threshold=20, accuracy_threshold=0.75)
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result.assessment_method == "statistical"


class TestHybridAssessment:
    """TS-30-5: Hybrid assessment when statistical below threshold."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hybrid_assessment(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-5: Verify hybrid when accuracy below threshold.

        Requirement: 30-REQ-1.5
        """
        # Populate DB with noisy outcomes (low accuracy)
        from tests.test_routing.helpers import populate_noisy_outcomes

        populate_noisy_outcomes(routing_db, count=25)

        config = RoutingConfig(training_threshold=20, accuracy_threshold=0.75)
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result.assessment_method == "hybrid"


class TestLlmFailureFallback:
    """TS-30-E1: LLM assessment failure fallback."""

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-E1: LLM call failure falls back to heuristic.

        Requirement: 30-REQ-1.E1
        """
        # Populate enough data to trigger hybrid mode
        from tests.test_routing.helpers import populate_noisy_outcomes

        populate_noisy_outcomes(routing_db, count=25)

        config = RoutingConfig(training_threshold=20, accuracy_threshold=0.75)
        pipeline = AssessmentPipeline(config=config, db=routing_db)

        # Mock the LLM assessor to fail
        with patch(
            "agent_fox.routing.assessor.llm_assess",
            side_effect=TimeoutError("LLM timeout"),
        ):
            result = await pipeline.assess(
                node_id="test_spec:1",
                spec_name="test_spec",
                task_group=1,
                spec_dir=spec_dir,
                archetype="coder",
                tier_ceiling=ModelTier.ADVANCED,
            )

        assert result.assessment_method == "heuristic"


class TestNoDbAssessment:
    """TS-30-E2: DuckDB unavailable during assessment.

    Updated for spec 38: DuckDB is now mandatory. This test verifies
    the heuristic fallback works with a real (empty) DB connection.
    """

    @pytest.mark.asyncio
    async def test_no_db_assessment(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-E2: Assessment works with empty DuckDB (heuristic).

        Requirement: 30-REQ-1.E2
        """
        config = RoutingConfig()
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result.assessment_method == "heuristic"
        assert result.confidence == 0.6  # heuristic default confidence


class TestHeuristicAssessor:
    """Unit tests for the heuristic assessment function."""

    def test_simple_task(self) -> None:
        """Small task with few subtasks → SIMPLE."""
        features = FeatureVector(
            subtask_count=2,
            spec_word_count=300,
            has_property_tests=False,
            edge_case_count=1,
            dependency_count=0,
            archetype="coder",
        )
        tier, confidence = heuristic_assess(features)
        assert tier == ModelTier.SIMPLE
        assert confidence == 0.6

    def test_advanced_task(self) -> None:
        """Complex task with many subtasks → ADVANCED."""
        features = FeatureVector(
            subtask_count=8,
            spec_word_count=2000,
            has_property_tests=True,
            edge_case_count=5,
            dependency_count=4,
            archetype="coder",
        )
        tier, confidence = heuristic_assess(features)
        assert tier == ModelTier.ADVANCED
        assert confidence == 0.6

    def test_standard_task(self) -> None:
        """Mid-complexity task → STANDARD."""
        features = FeatureVector(
            subtask_count=4,
            spec_word_count=800,
            has_property_tests=False,
            edge_case_count=2,
            dependency_count=2,
            archetype="coder",
        )
        tier, confidence = heuristic_assess(features)
        assert tier == ModelTier.STANDARD
        assert confidence == 0.6


class TestP6MethodSelection:
    """TS-30-P6: Method selection consistency."""

    @pytest.mark.property
    @given(
        outcome_count=st.integers(min_value=0, max_value=100),
        accuracy=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        training_threshold=st.integers(min_value=5, max_value=100),
        accuracy_threshold=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_p6_method_selection(
        self,
        outcome_count: int,
        accuracy: float,
        training_threshold: int,
        accuracy_threshold: float,
    ) -> None:
        """TS-30-P6: Assessment method follows deterministic rules.

        Requirement: 30-REQ-1.3, 30-REQ-1.4, 30-REQ-1.5
        """
        from agent_fox.routing.assessor import select_method

        method = select_method(
            outcome_count, accuracy, training_threshold, accuracy_threshold
        )

        if outcome_count < training_threshold:
            assert method == "heuristic"
        elif accuracy >= accuracy_threshold:
            assert method == "statistical"
        else:
            assert method == "hybrid"


class TestP7GracefulDegradation:
    """TS-30-P7: Assessment pipeline always returns a valid result."""

    @pytest.mark.asyncio
    async def test_p7_graceful_degradation_no_db(
        self, spec_dir: Path, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Assessment pipeline with empty DB returns valid result.

        Requirement: 30-REQ-1.E2, 30-REQ-7.E1
        """
        config = RoutingConfig()
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result is not None
        valid_tiers = [
            ModelTier.SIMPLE,
            ModelTier.STANDARD,
            ModelTier.ADVANCED,
        ]
        assert result.predicted_tier in valid_tiers

    @pytest.mark.asyncio
    async def test_p7_graceful_degradation_bad_dir(
        self, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Assessment pipeline with bad spec dir still returns valid result.

        Requirement: 30-REQ-1.E3, 30-REQ-7.E1
        """
        config = RoutingConfig()
        pipeline = AssessmentPipeline(config=config, db=routing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=Path("/nonexistent"),
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result is not None
        valid_tiers = [
            ModelTier.SIMPLE,
            ModelTier.STANDARD,
            ModelTier.ADVANCED,
        ]
        assert result.predicted_tier in valid_tiers

    @pytest.mark.asyncio
    async def test_p7_graceful_degradation_db_error(self, spec_dir: Path) -> None:
        """Assessment pipeline with failing DB still returns valid result.

        Requirement: 30-REQ-1.E2, 30-REQ-7.E1
        """
        failing_db = MagicMock()
        failing_db.execute.side_effect = RuntimeError("DB down")

        config = RoutingConfig()
        pipeline = AssessmentPipeline(config=config, db=failing_db)
        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        assert result is not None
        valid_tiers = [
            ModelTier.SIMPLE,
            ModelTier.STANDARD,
            ModelTier.ADVANCED,
        ]
        assert result.predicted_tier in valid_tiers
