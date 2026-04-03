"""Property tests for feature vector enrichment and quality gate.

Test Spec: TS-54-P1 through TS-54-P8
Correctness Properties: Properties 1-8 from design.md
"""

from __future__ import annotations

import json
import statistics
import uuid
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import duckdb
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.models import ModelTier
from agent_fox.routing.assessor import heuristic_assess
from agent_fox.routing.core import FeatureVector

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_RECOGNIZED_EXTENSIONS = [
    ".py",
    ".ts",
    ".js",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".proto",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
]

_spec_name_st = st.from_regex(r"[0-9]{2}_[a-z_]{3,15}", fullmatch=True)

_file_path_st = st.from_regex(
    r"[a-zA-Z_]{1,10}(/[a-zA-Z_]{1,10}){0,3}\.[a-zA-Z]{1,5}",
    fullmatch=True,
)


# ---------------------------------------------------------------------------
# TS-54-P1: Quality gate only when configured
# ---------------------------------------------------------------------------


class TestPropertyGateOnlyWhenConfigured:
    """TS-54-P1: No subprocess spawned when quality_gate is empty.

    Property: Property 1 from design.md
    Validates: 54-REQ-1.3
    """

    @given(gate=st.sampled_from(["", None]))
    @settings(max_examples=10)
    def test_p1_no_subprocess_when_unconfigured(self, gate: str | None) -> None:
        from agent_fox.core.config import OrchestratorConfig
        from agent_fox.engine.quality_gate import run_quality_gate

        kwargs = {}
        if gate is not None:
            kwargs["quality_gate"] = gate
        config = OrchestratorConfig(**kwargs)

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is None
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# TS-54-P2: Timeout enforcement
# ---------------------------------------------------------------------------


class TestPropertyTimeoutEnforcement:
    """TS-54-P2: Timed-out gates always record exit_code=-1.

    Property: Property 2 from design.md
    Validates: 54-REQ-1.2
    """

    @given(timeout=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10)
    def test_p2_timeout_always_minus_one(self, timeout: int) -> None:
        import subprocess

        from agent_fox.core.config import OrchestratorConfig
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(
            quality_gate="some_command",
            quality_gate_timeout=timeout,
        )

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="some_command", timeout=timeout)
            result = run_quality_gate(config, project_root="/tmp/project")

        assert result is not None
        assert result.exit_code == -1
        assert result.passed is False


# ---------------------------------------------------------------------------
# TS-54-P3: Gate failure does not block
# ---------------------------------------------------------------------------


class TestPropertyGateDoesNotBlock:
    """TS-54-P3: Gate failure never prevents the next session.

    Property: Property 3 from design.md
    Validates: 54-REQ-2.3
    """

    @given(exit_code=st.integers(min_value=1, max_value=255))
    @settings(max_examples=20)
    def test_p3_failure_returns_result(self, exit_code: int) -> None:
        import subprocess

        from agent_fox.core.config import OrchestratorConfig
        from agent_fox.engine.quality_gate import run_quality_gate

        config = OrchestratorConfig(quality_gate="cmd")

        with patch("agent_fox.engine.quality_gate.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args="cmd", returncode=exit_code, stdout="", stderr="")
            result = run_quality_gate(config, project_root="/tmp/project")

        # Function returns a result, never raises — engine can proceed
        assert result is not None
        assert result.passed is False
        assert result.exit_code == exit_code


# ---------------------------------------------------------------------------
# TS-54-P4: Feature vector serialization
# ---------------------------------------------------------------------------


class TestPropertyFeatureVectorSerialization:
    """TS-54-P4: All 10 fields present in JSON serialization.

    Property: Property 4 from design.md
    Validates: 54-REQ-7.2
    """

    @given(
        subtask_count=st.integers(min_value=0, max_value=20),
        spec_word_count=st.integers(min_value=0, max_value=10000),
        has_property_tests=st.booleans(),
        edge_case_count=st.integers(min_value=0, max_value=20),
        dependency_count=st.integers(min_value=0, max_value=10),
        archetype=st.sampled_from(["coder", "skeptic", "verifier"]),
        file_count_estimate=st.integers(min_value=0, max_value=50),
        cross_spec_integration=st.booleans(),
        language_count=st.integers(min_value=1, max_value=13),
        historical_median_duration_ms=st.one_of(st.none(), st.integers(min_value=1, max_value=1000000)),
    )
    @settings(max_examples=50)
    def test_p4_all_fields_in_json(
        self,
        subtask_count: int,
        spec_word_count: int,
        has_property_tests: bool,
        edge_case_count: int,
        dependency_count: int,
        archetype: str,
        file_count_estimate: int,
        cross_spec_integration: bool,
        language_count: int,
        historical_median_duration_ms: int | None,
    ) -> None:
        fv = FeatureVector(
            subtask_count=subtask_count,
            spec_word_count=spec_word_count,
            has_property_tests=has_property_tests,
            edge_case_count=edge_case_count,
            dependency_count=dependency_count,
            archetype=archetype,
            file_count_estimate=file_count_estimate,
            cross_spec_integration=cross_spec_integration,
            language_count=language_count,
            historical_median_duration_ms=historical_median_duration_ms,
        )
        j = json.loads(json.dumps(asdict(fv)))
        assert len(j) == 10
        assert "file_count_estimate" in j
        assert "cross_spec_integration" in j
        assert "language_count" in j
        assert "historical_median_duration_ms" in j


# ---------------------------------------------------------------------------
# TS-54-P5: File count accuracy
# ---------------------------------------------------------------------------


class TestPropertyFileCountAccuracy:
    """TS-54-P5: file_count_estimate matches distinct file paths.

    Property: Property 5 from design.md
    Validates: 54-REQ-3.1, 54-REQ-3.2
    """

    @given(
        paths=st.lists(
            _file_path_st,
            min_size=0,
            max_size=10,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_p5_file_count_matches_distinct_paths(self, paths: list[str], tmp_path: Path) -> None:
        from agent_fox.routing.features import _count_file_paths

        # Build a tasks.md with those paths in task group 2
        task_lines = ["- [ ] 2.1 Work on " + " and ".join(paths)] if paths else ["- [ ] 2.1 Do some work"]
        tasks_md = "# Tasks\n\n## Task Group 2\n\n" + "\n".join(task_lines) + "\n"
        sd = tmp_path / ".specs" / "test"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "tasks.md").write_text(tasks_md)

        count = _count_file_paths(sd, task_group=2)
        # Count should match the number of distinct paths
        assert count == len(set(paths))


# ---------------------------------------------------------------------------
# TS-54-P6: Cross-spec detection
# ---------------------------------------------------------------------------


class TestPropertyCrossSpecDetection:
    """TS-54-P6: cross_spec_integration is True iff other spec names present.

    Property: Property 6 from design.md
    Validates: 54-REQ-4.1, 54-REQ-4.2
    """

    @given(
        own_spec=_spec_name_st,
        other_specs=st.lists(_spec_name_st, min_size=0, max_size=5),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_p6_cross_spec_detection(self, own_spec: str, other_specs: list[str], tmp_path: Path) -> None:
        from agent_fox.routing.features import _detect_cross_spec

        all_specs = [own_spec] + other_specs
        task_text = "- [ ] 2.1 Work on " + " and ".join(all_specs)
        tasks_md = f"# Tasks\n\n## Task Group 2\n\n{task_text}\n"

        sd = tmp_path / ".specs" / "test"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "tasks.md").write_text(tasks_md)

        result = _detect_cross_spec(sd, task_group=2, own_spec=own_spec)
        other_present = any(s != own_spec for s in other_specs)
        assert result == other_present


# ---------------------------------------------------------------------------
# TS-54-P7: Historical median correctness
# ---------------------------------------------------------------------------


def _make_db_with_outcomes(durations: list[int], spec_name: str = "test") -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DB and insert outcomes with given durations."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE complexity_assessments (
            id VARCHAR PRIMARY KEY, node_id VARCHAR, spec_name VARCHAR,
            task_group INTEGER, predicted_tier VARCHAR, confidence FLOAT,
            assessment_method VARCHAR, feature_vector JSON,
            tier_ceiling VARCHAR, created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
    conn.execute("""
        CREATE TABLE execution_outcomes (
            id VARCHAR PRIMARY KEY, assessment_id VARCHAR,
            actual_tier VARCHAR, total_tokens INTEGER, total_cost FLOAT,
            duration_ms INTEGER, attempt_count INTEGER, escalation_count INTEGER,
            outcome VARCHAR, files_touched_count INTEGER,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
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
    for dur in durations:
        aid = str(uuid.uuid4())
        oid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO complexity_assessments
               (id, node_id, spec_name, task_group, predicted_tier,
                confidence, assessment_method, feature_vector, tier_ceiling)
               VALUES (?, ?, ?, 1, 'STANDARD', 0.6, 'heuristic', ?, 'ADVANCED')""",
            [aid, f"{spec_name}:1", spec_name, fv_json],
        )
        conn.execute(
            """INSERT INTO execution_outcomes
               (id, assessment_id, actual_tier, total_tokens, total_cost,
                duration_ms, attempt_count, escalation_count, outcome,
                files_touched_count)
               VALUES (?, ?, 'STANDARD', 1000, 0.01, ?, 1, 0, 'completed', 3)""",
            [oid, aid, dur],
        )
    return conn


class TestPropertyHistoricalMedian:
    """TS-54-P7: Median equals statistics.median of prior durations.

    Property: Property 7 from design.md
    Validates: 54-REQ-6.1, 54-REQ-6.2, 54-REQ-6.E1
    """

    @given(
        durations=st.lists(
            st.integers(min_value=1, max_value=1000000),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_p7_median_correctness(self, durations: list[int]) -> None:
        from agent_fox.routing.features import _get_historical_median_duration

        conn = _make_db_with_outcomes(durations, spec_name="test")
        try:
            result = _get_historical_median_duration(conn, "test")
            if len(durations) == 0:
                assert result is None
            else:
                expected = int(statistics.median(durations))
                assert result == expected
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TS-54-P8: Heuristic ADVANCED threshold
# ---------------------------------------------------------------------------


class TestPropertyHeuristicThreshold:
    """TS-54-P8: ADVANCED predicted when cross_spec or file_count >= 8.

    Property: Property 8 from design.md
    Validates: 54-REQ-7.1
    """

    @given(
        cross_spec=st.booleans(),
        file_count=st.integers(min_value=0, max_value=20),
        subtask_count=st.integers(min_value=0, max_value=5),
        spec_word_count=st.integers(min_value=0, max_value=499),
        dependency_count=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=100)
    def test_p8_advanced_threshold(
        self,
        cross_spec: bool,
        file_count: int,
        subtask_count: int,
        spec_word_count: int,
        dependency_count: int,
    ) -> None:
        fv = FeatureVector(
            subtask_count=subtask_count,
            spec_word_count=spec_word_count,
            has_property_tests=False,
            edge_case_count=0,
            dependency_count=dependency_count,
            archetype="coder",
            cross_spec_integration=cross_spec,
            file_count_estimate=file_count,
            language_count=1,
            historical_median_duration_ms=None,
        )
        tier, confidence = heuristic_assess(fv)

        if cross_spec or file_count >= 8:
            assert tier == ModelTier.ADVANCED
            # Confidence should be 0.7 for the new signals
            # (existing signals like subtask_count >= 6 use 0.6)
