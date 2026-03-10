"""Test helpers for populating routing test data."""

from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, datetime

import duckdb

from agent_fox.core.models import ModelTier


def populate_consistent_outcomes(conn: duckdb.DuckDBPyConnection, count: int) -> None:
    """Insert N assessment+outcome pairs with consistent tier mappings.

    Features map deterministically to tiers, enabling high model accuracy.
    """
    for i in range(count):
        aid = str(uuid.uuid4())
        oid = str(uuid.uuid4())

        if i % 3 == 0:
            tier = ModelTier.SIMPLE
            subtasks, words, props, deps = 2, 300, False, 0
        elif i % 3 == 1:
            tier = ModelTier.STANDARD
            subtasks, words, props, deps = 4, 800, False, 2
        else:
            tier = ModelTier.ADVANCED
            subtasks, words, props, deps = 8, 2000, True, 4

        fv = json.dumps(
            {
                "subtask_count": subtasks,
                "spec_word_count": words,
                "has_property_tests": props,
                "edge_case_count": i % 3,
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


def populate_noisy_outcomes(conn: duckdb.DuckDBPyConnection, count: int) -> None:
    """Insert N assessment+outcome pairs with noisy/random tier mappings.

    Features don't correlate with tiers, producing low model accuracy.
    """
    tiers = [ModelTier.SIMPLE, ModelTier.STANDARD, ModelTier.ADVANCED]
    rng = random.Random(42)  # deterministic for reproducibility

    for i in range(count):
        aid = str(uuid.uuid4())
        oid = str(uuid.uuid4())

        tier = rng.choice(tiers)
        subtasks = rng.randint(1, 10)
        words = rng.randint(100, 3000)
        props = rng.choice([True, False])
        deps = rng.randint(0, 5)

        fv = json.dumps(
            {
                "subtask_count": subtasks,
                "spec_word_count": words,
                "has_property_tests": props,
                "edge_case_count": rng.randint(0, 5),
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
