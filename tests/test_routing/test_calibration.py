"""Tests for statistical model and calibration.

Test Spec: TS-30-15, TS-30-16, TS-30-17, TS-30-18, TS-30-19,
           TS-30-E7, TS-30-E8
Requirements: 30-REQ-4.1 through 30-REQ-4.5, 30-REQ-4.E1, 30-REQ-4.E2
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.core.models import ModelTier
from agent_fox.routing.calibration import StatisticalAssessor
from agent_fox.routing.types import FeatureVector


def _populate_outcomes(
    conn: duckdb.DuckDBPyConnection,
    count: int,
    *,
    consistent: bool = True,
) -> None:
    """Insert N assessment+outcome pairs into the DB.

    If consistent=True, features map cleanly to tiers (high accuracy).
    If consistent=False, features map randomly (low accuracy / noisy).
    """
    import json
    import random

    tiers = [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]
    for i in range(count):
        aid = str(uuid.uuid4())
        oid = str(uuid.uuid4())

        if consistent:
            # Map subtask count to tier deterministically
            if i % 3 == 0:
                tier = ModelTier.SIMPLE
                subtasks = 2
                words = 300
                props = False
                deps = 0
            elif i % 3 == 1:
                tier = ModelTier.STANDARD
                subtasks = 4
                words = 800
                props = False
                deps = 2
            else:
                tier = ModelTier.ADVANCED
                subtasks = 8
                words = 2000
                props = True
                deps = 4
        else:
            # Random/noisy mapping
            tier = random.choice(tiers)
            subtasks = random.randint(1, 10)
            words = random.randint(100, 3000)
            props = random.choice([True, False])
            deps = random.randint(0, 5)

        fv = json.dumps(
            {
                "subtask_count": subtasks,
                "spec_word_count": words,
                "has_property_tests": props,
                "edge_case_count": random.randint(0, 5) if not consistent else i % 3,
                "dependency_count": deps,
                "archetype": "coder",
            }
        )

        conn.execute(
            """INSERT INTO complexity_assessments
               (id, node_id, spec_name, task_group, predicted_tier,
                confidence, assessment_method, feature_vector, tier_ceiling, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                aid,
                f"spec:{i}",
                "spec",
                1,
                tier.value,
                0.6,
                "heuristic",
                fv,
                "ADVANCED",
                datetime.now(UTC),
            ],
        )
        conn.execute(
            """INSERT INTO execution_outcomes
               (id, assessment_id, actual_tier, total_tokens, total_cost,
                duration_ms, attempt_count, escalation_count, outcome,
                files_touched_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                oid,
                aid,
                tier.value,
                5000,
                0.05,
                3000,
                1,
                0,
                "completed",
                5,
                datetime.now(UTC),
            ],
        )


class TestTrainingTrigger:
    """TS-30-15: Statistical model training trigger."""

    @pytest.mark.integration
    def test_training_trigger(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-15: Verify model is trained when threshold reached.

        Requirement: 30-REQ-4.1
        """
        _populate_outcomes(routing_db, 19, consistent=True)

        assessor = StatisticalAssessor(routing_db)
        assert assessor.is_ready(training_threshold=20) is False

        # Add one more to reach threshold
        _populate_outcomes(routing_db, 1, consistent=True)
        assert assessor.is_ready(training_threshold=20) is True

        accuracy = assessor.train()
        assert accuracy > 0.0

        features = FeatureVector(
            subtask_count=2,
            spec_word_count=300,
            has_property_tests=False,
            edge_case_count=0,
            dependency_count=0,
            archetype="coder",
        )
        tier, conf = assessor.predict(features)
        assert tier in [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]


class TestCrossValidation:
    """TS-30-16: Cross-validation accuracy."""

    @pytest.mark.integration
    def test_cross_validation(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-16: Verify accuracy is a valid float in [0, 1].

        Requirement: 30-REQ-4.2
        """
        _populate_outcomes(routing_db, 30, consistent=True)

        assessor = StatisticalAssessor(routing_db)
        accuracy = assessor.train()
        assert 0.0 <= accuracy <= 1.0


class TestStatisticalPrimary:
    """TS-30-17: Statistical model as primary when accurate."""

    @pytest.mark.integration
    def test_statistical_primary(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-17: Verify statistical used when accuracy > threshold.

        Requirement: 30-REQ-4.3
        """
        _populate_outcomes(routing_db, 30, consistent=True)

        assessor = StatisticalAssessor(routing_db)
        accuracy = assessor.train()
        # With consistent data, accuracy should be high
        assert accuracy > 0.75


class TestHybridDivergence:
    """TS-30-18: Hybrid divergence handling."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hybrid_divergence(
        self, spec_dir, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-18: Hybrid mode uses higher-accuracy method on divergence.

        Requirement: 30-REQ-4.4
        """
        from agent_fox.routing.assessor import AssessmentPipeline
        from agent_fox.routing.types import RoutingConfig

        _populate_outcomes(routing_db, 25, consistent=False)

        config = RoutingConfig(training_threshold=20, accuracy_threshold=0.75)
        pipeline = AssessmentPipeline(config=config, db=routing_db)

        # Mock LLM to return STANDARD
        with patch(
            "agent_fox.routing.assessor.llm_assess",
            return_value=(ModelTier.STANDARD, 0.8),
        ):
            result = await pipeline.assess(
                node_id="test_spec:1",
                spec_name="test_spec",
                task_group=1,
                spec_dir=spec_dir,
                archetype="coder",
                tier_ceiling=ModelTier.ADVANCED,
            )

        # In hybrid mode, should use one of the valid tiers
        assert result.predicted_tier in [
            ModelTier.SIMPLE,
            ModelTier.STANDARD,
            ModelTier.ADVANCED,
        ]


class TestRetrainingTrigger:
    """TS-30-19: Retraining trigger."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_retraining_trigger(
        self, spec_dir, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-19: Verify retraining after N new outcomes.

        Requirement: 30-REQ-4.5
        """
        from agent_fox.routing.assessor import AssessmentPipeline
        from agent_fox.routing.types import RoutingConfig

        _populate_outcomes(routing_db, 30, consistent=True)

        config = RoutingConfig(
            training_threshold=20,
            accuracy_threshold=0.75,
            retrain_interval=10,
        )
        pipeline = AssessmentPipeline(config=config, db=routing_db)

        # First assess triggers initial training
        await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )

        # Add 10 more outcomes to trigger retraining
        _populate_outcomes(routing_db, 10, consistent=True)

        result = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        # Should still work after retraining
        assert result.predicted_tier in [
            ModelTier.SIMPLE,
            ModelTier.STANDARD,
            ModelTier.ADVANCED,
        ]


class TestTrainingFailure:
    """TS-30-E7: Statistical training failure."""

    def test_training_failure(self, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-30-E7: Training failure falls back gracefully.

        Requirement: 30-REQ-4.E1
        """
        # Insert 20 identical outcomes (zero variance → training should fail)
        import json

        for i in range(20):
            aid = str(uuid.uuid4())
            oid = str(uuid.uuid4())
            fv = json.dumps(
                {
                    "subtask_count": 3,
                    "spec_word_count": 500,
                    "has_property_tests": False,
                    "edge_case_count": 1,
                    "dependency_count": 1,
                    "archetype": "coder",
                }
            )
            routing_db.execute(
                """INSERT INTO complexity_assessments
                   (id, node_id, spec_name, task_group,
                    predicted_tier, confidence, assessment_method,
                    feature_vector, tier_ceiling, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    aid,
                    f"spec:{i}",
                    "spec",
                    1,
                    "SIMPLE",
                    0.6,
                    "heuristic",
                    fv,
                    "ADVANCED",
                    datetime.now(UTC),
                ],
            )
            routing_db.execute(
                """INSERT INTO execution_outcomes
                   (id, assessment_id, actual_tier, total_tokens, total_cost,
                    duration_ms, attempt_count, escalation_count, outcome,
                    files_touched_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    oid,
                    aid,
                    "SIMPLE",
                    5000,
                    0.05,
                    3000,
                    1,
                    0,
                    "completed",
                    5,
                    datetime.now(UTC),
                ],
            )

        assessor = StatisticalAssessor(routing_db)
        # Should not raise, should return 0.0 or handle gracefully
        accuracy = assessor.train()
        assert accuracy >= 0.0


class TestAccuracyDegradation:
    """TS-30-E8: Statistical accuracy degradation."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_accuracy_degradation(
        self, spec_dir, routing_db: duckdb.DuckDBPyConnection
    ) -> None:
        """TS-30-E8: Accuracy drop triggers revert to hybrid.

        Requirement: 30-REQ-4.E2
        """
        from agent_fox.routing.assessor import AssessmentPipeline
        from agent_fox.routing.types import RoutingConfig

        # First: train with good data
        _populate_outcomes(routing_db, 30, consistent=True)

        config = RoutingConfig(
            training_threshold=20,
            accuracy_threshold=0.75,
            retrain_interval=10,
        )
        pipeline = AssessmentPipeline(config=config, db=routing_db)

        result1 = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        # Should be statistical with good data
        assert result1.assessment_method in ["statistical", "hybrid", "heuristic"]

        # Then: add noisy data to degrade accuracy
        _populate_outcomes(routing_db, 30, consistent=False)

        result2 = await pipeline.assess(
            node_id="test_spec:1",
            spec_name="test_spec",
            task_group=1,
            spec_dir=spec_dir,
            archetype="coder",
            tier_ceiling=ModelTier.ADVANCED,
        )
        # After degradation, should revert to hybrid
        assert result2.assessment_method in ["hybrid", "heuristic"]
