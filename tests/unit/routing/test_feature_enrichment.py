"""Unit tests for feature vector enrichment (4 new fields).

Test Spec: TS-54-7, TS-54-8, TS-54-9, TS-54-10, TS-54-12, TS-54-13,
           TS-54-E2, TS-54-E3, TS-54-E4, TS-54-E5, TS-54-E6
Requirements: 54-REQ-3.1, 54-REQ-3.2, 54-REQ-4.1, 54-REQ-4.2,
              54-REQ-5.1, 54-REQ-5.2, 54-REQ-6.1, 54-REQ-6.2, 54-REQ-6.E1,
              54-REQ-7.1, 54-REQ-7.2, 54-REQ-7.E1
"""

from __future__ import annotations

import json
import textwrap
import uuid
from collections.abc import Generator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from agent_fox.core.models import ModelTier
from agent_fox.routing.assessor import heuristic_assess
from agent_fox.routing.core import FeatureVector
from agent_fox.routing.features import extract_features

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enrichment_spec_dir(tmp_path: Path) -> Path:
    """Spec directory with file paths, cross-spec refs, and multi-language mentions."""
    sd = tmp_path / ".specs" / "05_auth"
    sd.mkdir(parents=True)

    tasks_md = textwrap.dedent("""\
    # Tasks

    ## Task Group 1

    - [ ] 1.1 Setup

    ## Task Group 2

    - [ ] 2.1 Modify app.py and config.py and test_app.py
    - [ ] 2.2 Update schema.proto and fix client.ts
    - [ ] 2.3 Also touch 03_api_routes for integration
    """)
    (sd / "tasks.md").write_text(tasks_md)

    requirements_md = textwrap.dedent("""\
    # Requirements

    ## Requirement 1

    Some text describing requirements for the auth feature.
    """)
    (sd / "requirements.md").write_text(requirements_md)

    design_md = textwrap.dedent("""\
    # Design

    ## Architecture

    Simple design document.
    """)
    (sd / "design.md").write_text(design_md)

    test_spec_md = textwrap.dedent("""\
    # Test Specification

    ## Test Cases

    ### TS-1: Basic test

    **Type:** unit
    """)
    (sd / "test_spec.md").write_text(test_spec_md)

    return sd


@pytest.fixture
def no_paths_spec_dir(tmp_path: Path) -> Path:
    """Spec dir with task text containing no file paths."""
    sd = tmp_path / ".specs" / "10_refactor"
    sd.mkdir(parents=True)

    tasks_md = textwrap.dedent("""\
    # Tasks

    ## Task Group 2

    - [ ] 2.1 Refactor the module structure
    - [ ] 2.2 Update the configuration
    """)
    (sd / "tasks.md").write_text(tasks_md)
    (sd / "requirements.md").write_text("# Requirements\n\nSome text.\n")
    (sd / "design.md").write_text("# Design\n\nSome text.\n")
    (sd / "test_spec.md").write_text("# Test Spec\n")

    return sd


@pytest.fixture
def routing_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with routing tables including execution_outcomes."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complexity_assessments (
            id              VARCHAR PRIMARY KEY,
            node_id         VARCHAR NOT NULL,
            spec_name       VARCHAR NOT NULL,
            task_group      INTEGER NOT NULL,
            predicted_tier  VARCHAR NOT NULL,
            confidence      FLOAT NOT NULL,
            assessment_method VARCHAR NOT NULL,
            feature_vector  JSON NOT NULL,
            tier_ceiling    VARCHAR NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_outcomes (
            id                  VARCHAR PRIMARY KEY,
            assessment_id       VARCHAR NOT NULL REFERENCES complexity_assessments(id),
            actual_tier         VARCHAR NOT NULL,
            total_tokens        INTEGER NOT NULL,
            total_cost          FLOAT NOT NULL,
            duration_ms         INTEGER NOT NULL,
            attempt_count       INTEGER NOT NULL,
            escalation_count    INTEGER NOT NULL,
            outcome             VARCHAR NOT NULL,
            files_touched_count INTEGER NOT NULL,
            created_at          TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
    """)
    yield conn
    conn.close()


def _insert_outcome(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    duration_ms: int,
    outcome: str = "completed",
) -> None:
    """Insert a fake assessment + outcome pair for testing historical median."""
    aid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    fv_json = json.dumps(
        {
            "subtask_count": 1,
            "spec_word_count": 100,
            "has_property_tests": False,
            "edge_case_count": 0,
            "dependency_count": 0,
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
            f"{spec_name}:1",
            spec_name,
            1,
            "STANDARD",
            0.6,
            "heuristic",
            fv_json,
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
            "STANDARD",
            1000,
            0.01,
            duration_ms,
            1,
            0,
            outcome,
            3,
            datetime.now(UTC),
        ],
    )


# ---------------------------------------------------------------------------
# TS-54-7: File count estimate extraction
# ---------------------------------------------------------------------------


class TestFileCountEstimate:
    """TS-54-7: Count distinct file paths in task group description."""

    def test_file_count_multiple_paths(self, enrichment_spec_dir: Path) -> None:
        """TS-54-7: Three distinct file paths → file_count_estimate=3 (or more).

        Requirement: 54-REQ-3.1
        """
        fv = extract_features(enrichment_spec_dir, task_group=2, archetype="coder")
        # Task group 2 mentions: app.py, config.py, test_app.py, schema.proto, client.ts
        assert fv.file_count_estimate >= 3


# ---------------------------------------------------------------------------
# TS-54-8: Cross-spec detection
# ---------------------------------------------------------------------------


class TestCrossSpecDetection:
    """TS-54-8: References to other spec names are detected."""

    def test_cross_spec_detected(self, enrichment_spec_dir: Path) -> None:
        """TS-54-8: Task mentioning 03_api_routes in spec 05_auth → True.

        Requirement: 54-REQ-4.1
        """
        fv = extract_features(
            enrichment_spec_dir,
            task_group=2,
            archetype="coder",
            spec_name="05_auth",
        )
        assert fv.cross_spec_integration is True


# ---------------------------------------------------------------------------
# TS-54-9: No cross-spec when only own spec
# ---------------------------------------------------------------------------


class TestNoCrossSpecOwnOnly:
    """TS-54-9: Referencing only own spec name does not set cross_spec."""

    def test_own_spec_not_cross(self, tmp_path: Path) -> None:
        """TS-54-9: Only own spec name → cross_spec_integration=False.

        Requirement: 54-REQ-4.2
        """
        sd = tmp_path / ".specs" / "05_auth"
        sd.mkdir(parents=True)

        tasks_md = textwrap.dedent("""\
        # Tasks

        ## Task Group 2

        - [ ] 2.1 Work on 05_auth feature
        """)
        (sd / "tasks.md").write_text(tasks_md)
        (sd / "requirements.md").write_text("# Requirements\n")
        (sd / "design.md").write_text("# Design\n")
        (sd / "test_spec.md").write_text("# Test Spec\n")

        fv = extract_features(sd, task_group=2, archetype="coder", spec_name="05_auth")
        assert fv.cross_spec_integration is False


# ---------------------------------------------------------------------------
# TS-54-10: Language count from extensions
# ---------------------------------------------------------------------------


class TestLanguageCount:
    """TS-54-10: Count distinct language extensions."""

    def test_language_count_multiple(self, enrichment_spec_dir: Path) -> None:
        """TS-54-10: .py, .proto, .ts → language_count=3.

        Requirement: 54-REQ-5.1
        """
        fv = extract_features(enrichment_spec_dir, task_group=2, archetype="coder")
        assert fv.language_count == 3


# ---------------------------------------------------------------------------
# TS-54-12: Heuristic ADVANCED threshold
# ---------------------------------------------------------------------------


class TestHeuristicAdvancedThreshold:
    """TS-54-12: cross_spec or high file count triggers ADVANCED."""

    def test_cross_spec_triggers_advanced(self) -> None:
        """TS-54-12: cross_spec_integration=True → ADVANCED at 0.7.

        Requirement: 54-REQ-7.1
        """
        fv = FeatureVector(
            subtask_count=2,
            spec_word_count=200,
            has_property_tests=False,
            edge_case_count=1,
            dependency_count=0,
            archetype="coder",
            cross_spec_integration=True,
            file_count_estimate=2,
            language_count=1,
            historical_median_duration_ms=None,
        )
        tier, confidence = heuristic_assess(fv)
        assert tier == ModelTier.ADVANCED
        assert confidence == 0.7

    def test_high_file_count_triggers_advanced(self) -> None:
        """TS-54-12: file_count_estimate >= 8 → ADVANCED at 0.7.

        Requirement: 54-REQ-7.1
        """
        fv = FeatureVector(
            subtask_count=2,
            spec_word_count=200,
            has_property_tests=False,
            edge_case_count=1,
            dependency_count=0,
            archetype="coder",
            cross_spec_integration=False,
            file_count_estimate=8,
            language_count=1,
            historical_median_duration_ms=None,
        )
        tier, confidence = heuristic_assess(fv)
        assert tier == ModelTier.ADVANCED
        assert confidence == 0.7


# ---------------------------------------------------------------------------
# TS-54-13: Feature vector JSON serialization
# ---------------------------------------------------------------------------


class TestFeatureVectorSerialization:
    """TS-54-13: All 10 fields present in JSON serialization."""

    def test_json_contains_all_fields(self) -> None:
        """TS-54-13: Serialized JSON has 10 keys.

        Requirement: 54-REQ-7.2
        """
        fv = FeatureVector(
            subtask_count=5,
            spec_word_count=1200,
            has_property_tests=True,
            edge_case_count=3,
            dependency_count=1,
            archetype="coder",
            file_count_estimate=4,
            cross_spec_integration=False,
            language_count=2,
            historical_median_duration_ms=200,
        )
        j = json.loads(json.dumps(asdict(fv)))
        expected_keys = {
            "subtask_count",
            "spec_word_count",
            "has_property_tests",
            "edge_case_count",
            "dependency_count",
            "archetype",
            "file_count_estimate",
            "cross_spec_integration",
            "language_count",
            "historical_median_duration_ms",
        }
        assert set(j.keys()) == expected_keys


# ---------------------------------------------------------------------------
# TS-54-E2: No prior outcomes returns None
# ---------------------------------------------------------------------------


class TestNoPriorOutcomes:
    """TS-54-E2: Historical median is None when no outcomes exist."""

    def test_no_prior_outcomes(self, no_paths_spec_dir: Path, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-54-E2: Empty outcomes → historical_median_duration_ms=None.

        Requirement: 54-REQ-6.2
        """
        fv = extract_features(
            no_paths_spec_dir,
            task_group=2,
            archetype="coder",
            conn=routing_db,
            spec_name="new_spec",
        )
        assert fv.historical_median_duration_ms is None


# ---------------------------------------------------------------------------
# TS-54-E3: Single prior outcome
# ---------------------------------------------------------------------------


class TestSinglePriorOutcome:
    """TS-54-E3: Median of one value equals that value."""

    def test_single_outcome(self, no_paths_spec_dir: Path, routing_db: duckdb.DuckDBPyConnection) -> None:
        """TS-54-E3: One outcome of 500ms → median=500.

        Requirement: 54-REQ-6.E1
        """
        _insert_outcome(routing_db, "03_api", 500)

        fv = extract_features(
            no_paths_spec_dir,
            task_group=2,
            archetype="coder",
            conn=routing_db,
            spec_name="03_api",
        )
        assert fv.historical_median_duration_ms == 500


# ---------------------------------------------------------------------------
# TS-54-E4: No file paths in task
# ---------------------------------------------------------------------------


class TestNoFilePaths:
    """TS-54-E4: file_count_estimate defaults to 0."""

    def test_no_file_paths(self, no_paths_spec_dir: Path) -> None:
        """TS-54-E4: No file paths → file_count_estimate=0.

        Requirement: 54-REQ-3.2
        """
        fv = extract_features(no_paths_spec_dir, task_group=2, archetype="coder")
        assert fv.file_count_estimate == 0


# ---------------------------------------------------------------------------
# TS-54-E5: Language count defaults to 1
# ---------------------------------------------------------------------------


class TestLanguageCountDefault:
    """TS-54-E5: language_count defaults to 1 with no extensions."""

    def test_language_default(self, no_paths_spec_dir: Path) -> None:
        """TS-54-E5: No recognized extensions → language_count=1.

        Requirement: 54-REQ-5.2
        """
        fv = extract_features(no_paths_spec_dir, task_group=2, archetype="coder")
        assert fv.language_count == 1


# ---------------------------------------------------------------------------
# TS-54-E6: Both cross-spec and high file count
# ---------------------------------------------------------------------------


class TestNoDoubleUpgrade:
    """TS-54-E6: No double-upgrade when both conditions met."""

    def test_no_double_upgrade(self) -> None:
        """TS-54-E6: cross_spec=True AND file_count=10 → ADVANCED 0.7 (not higher).

        Requirement: 54-REQ-7.E1
        """
        fv = FeatureVector(
            subtask_count=2,
            spec_word_count=200,
            has_property_tests=False,
            edge_case_count=1,
            dependency_count=0,
            archetype="coder",
            cross_spec_integration=True,
            file_count_estimate=10,
            language_count=1,
            historical_median_duration_ms=None,
        )
        tier, confidence = heuristic_assess(fv)
        assert tier == ModelTier.ADVANCED
        assert confidence == 0.7
