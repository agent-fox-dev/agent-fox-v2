"""Integration and smoke tests for scope_guard subsystem.

Test Spec: TS-87-SMOKE-1 through TS-87-SMOKE-5

Smoke tests exercise full execution paths from design.md without mocking
the internal components named in those paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    DeliverableStatus,
    FileChange,
    Language,
    OverlapSeverity,
    ScopeGuardSessionOutcome,
    SessionClassification,
    SessionResult,
    SpecGraph,
    TaskGroup,
)
from agent_fox.scope_guard.overlap_detector import detect_overlaps
from agent_fox.scope_guard.preflight_checker import check_scope
from agent_fox.scope_guard.prompt_builder import build_prompt
from agent_fox.scope_guard.session_classifier import classify_session
from agent_fox.scope_guard.telemetry import (
    init_schema,
    record_scope_check,
    record_session_outcome,
)

# ---------------------------------------------------------------------------
# TS-87-SMOKE-1: Overlap detection through warning/error emission
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestSmokeOverlapDetection:
    """Smoke test: full Path 1 — overlap detection → OverlapResult → caller checks.

    Must NOT mock: overlap_detector.detect_overlaps,
    overlap_detector._compare_deliverables, overlap_detector._classify_overlaps.

    Requirements: 87-REQ-3.1, 87-REQ-3.2, 87-REQ-3.3, 87-REQ-3.4
    """

    def test_overlap_with_dependency_produces_warning(self) -> None:
        """TG1 and TG3 overlap on 'validate' and TG3 depends on TG1 → WARNING."""
        spec_graph = SpecGraph(
            spec_number=4,
            task_groups=[
                TaskGroup(
                    number=1,
                    spec_number=4,
                    archetype="test-writing",
                    deliverables=[
                        Deliverable("src/validator.rs", "validate", 1),
                    ],
                    depends_on=[],
                ),
                TaskGroup(
                    number=2,
                    spec_number=4,
                    archetype="implementation",
                    deliverables=[
                        Deliverable("src/engine.rs", "run", 2),
                    ],
                    depends_on=[1],
                ),
                TaskGroup(
                    number=3,
                    spec_number=4,
                    archetype="implementation",
                    deliverables=[
                        Deliverable("src/validator.rs", "validate", 3),
                    ],
                    depends_on=[1],
                ),
            ],
        )

        result = detect_overlaps(spec_graph)

        # There should be exactly one overlap between TG1 and TG3
        assert len(result.overlaps) == 1
        assert set(result.overlaps[0].task_group_numbers) == {1, 3}
        assert "validate" in result.overlaps[0].deliverable_id
        # Dependency exists (TG3 depends on TG1) → warning, not error
        assert result.has_warnings is True
        assert result.has_errors is False
        assert result.overlaps[0].severity == OverlapSeverity.WARNING

    def test_overlap_without_dependency_produces_error(self) -> None:
        """TG2 and TG3 overlap on 'process' with no dependency → ERROR blocks execution."""
        spec_graph = SpecGraph(
            spec_number=5,
            task_groups=[
                TaskGroup(
                    number=1,
                    spec_number=5,
                    archetype="test-writing",
                    deliverables=[
                        Deliverable("src/a.rs", "init", 1),
                    ],
                    depends_on=[],
                ),
                TaskGroup(
                    number=2,
                    spec_number=5,
                    archetype="implementation",
                    deliverables=[
                        Deliverable("src/shared.rs", "process", 2),
                    ],
                    depends_on=[1],
                ),
                TaskGroup(
                    number=3,
                    spec_number=5,
                    archetype="implementation",
                    deliverables=[
                        Deliverable("src/shared.rs", "process", 3),
                    ],
                    depends_on=[1],
                ),
            ],
        )

        result = detect_overlaps(spec_graph)

        # Overlap between TG2 and TG3 with no dependency → error
        assert result.has_errors is True
        error_overlaps = [
            o
            for o in result.overlaps
            if o.severity == OverlapSeverity.ERROR
        ]
        assert len(error_overlaps) == 1
        assert set(error_overlaps[0].task_group_numbers) == {2, 3}

        # Caller would block execution based on has_errors
        assert result.has_errors is True

    def test_no_overlap_clean_graph(self) -> None:
        """Distinct deliverables across all task groups → no overlaps."""
        spec_graph = SpecGraph(
            spec_number=6,
            task_groups=[
                TaskGroup(
                    number=1,
                    spec_number=6,
                    archetype="test-writing",
                    deliverables=[Deliverable("src/a.rs", "init", 1)],
                    depends_on=[],
                ),
                TaskGroup(
                    number=2,
                    spec_number=6,
                    archetype="implementation",
                    deliverables=[Deliverable("src/b.rs", "run", 2)],
                    depends_on=[1],
                ),
            ],
        )

        result = detect_overlaps(spec_graph)

        assert len(result.overlaps) == 0
        assert result.has_errors is False
        assert result.has_warnings is False


# ---------------------------------------------------------------------------
# TS-87-SMOKE-2: Pre-flight skip of fully-implemented task group
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestSmokePreflightSkip:
    """Smoke test: full Path 2 — check_scope → all-implemented → record pre-flight-skip.

    Must NOT mock: preflight_checker.check_scope, source_parser.extract_function_body,
    stub_patterns.is_stub_body, telemetry.record_session_outcome.

    Requirements: 87-REQ-2.1, 87-REQ-2.2, 87-REQ-2.4, 87-REQ-2.5
    """

    def test_fully_implemented_codebase_skips_session(
        self, tmp_path: Path
    ) -> None:
        """All deliverables fully implemented → all-implemented → pre-flight-skip recorded."""
        # Create a codebase with fully implemented functions
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.rs").write_text(
            "fn validate() -> bool {\n"
            "    let x = compute();\n"
            "    x > 0\n"
            "}\n"
        )
        (src / "bar.rs").write_text(
            "fn process() -> i32 {\n"
            "    let result = compute();\n"
            "    result\n"
            "}\n"
        )

        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[
                Deliverable("src/foo.rs", "validate", 2),
                Deliverable("src/bar.rs", "process", 2),
            ],
            depends_on=[1],
        )

        # Run pre-flight scope check (no mocking)
        scope_result = check_scope(task_group, tmp_path)

        # All deliverables should be already-implemented
        assert scope_result.overall == "all-implemented"
        for dr in scope_result.deliverable_results:
            assert dr.status == DeliverableStatus.ALREADY_IMPLEMENTED

        # Record pre-flight-skip in DuckDB (no mocking)
        conn = duckdb.connect(":memory:")
        init_schema(conn)

        outcome = ScopeGuardSessionOutcome(
            session_id="sess-smoke-skip-1",
            spec_number=task_group.spec_number,
            task_group_number=task_group.number,
            classification=SessionClassification.PRE_FLIGHT_SKIP,
            duration_seconds=0.0,
            cost_dollars=0.0,
            timestamp=datetime.now(tz=UTC),
            reason="all deliverables already implemented",
        )
        record_session_outcome(conn, outcome)

        # Also record the scope check result
        record_scope_check(conn, scope_result)

        # Verify the DuckDB row
        rows = conn.execute(
            "SELECT classification, cost_dollars, duration_seconds "
            "FROM session_outcomes WHERE session_id = 'sess-smoke-skip-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "pre-flight-skip"
        assert rows[0][1] == 0.0
        assert rows[0][2] == 0.0

        # Verify scope check telemetry
        sc_rows = conn.execute(
            "SELECT deliverable_count, check_duration_ms "
            "FROM scope_check_results WHERE task_group_number = 2"
        ).fetchall()
        assert len(sc_rows) == 1
        assert sc_rows[0][0] == 2  # two deliverables checked
        assert sc_rows[0][1] >= 0  # non-negative duration

        conn.close()


# ---------------------------------------------------------------------------
# TS-87-SMOKE-3: Reduced scope prompt for partially-implemented task group
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestSmokeReducedScopePrompt:
    """Smoke test: full Path 3 — check_scope → partially-implemented → build_prompt.

    Must NOT mock: preflight_checker.check_scope, prompt_builder.build_prompt,
    prompt_builder._filter_pending_deliverables.

    Requirements: 87-REQ-2.3, 87-REQ-5.1
    """

    def test_partial_scope_produces_reduced_prompt(
        self, tmp_path: Path
    ) -> None:
        """One stub, one implemented → prompt lists only stub as work item."""
        # Create a mixed codebase
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.rs").write_text(
            "fn validate() -> bool {\n    todo!()\n}\n"
        )
        (src / "bar.rs").write_text(
            "fn process() -> i32 {\n"
            "    let result = compute();\n"
            "    result\n"
            "}\n"
        )

        task_group = TaskGroup(
            number=2,
            spec_number=4,
            archetype="implementation",
            deliverables=[
                Deliverable("src/foo.rs", "validate", 2),
                Deliverable("src/bar.rs", "process", 2),
            ],
            depends_on=[1],
        )

        # Run pre-flight scope check (no mocking)
        scope_result = check_scope(task_group, tmp_path)
        assert scope_result.overall == "partially-implemented"

        # Build prompt with reduced scope (no mocking)
        prompt = build_prompt(task_group, scope_result)

        # validate should be in the work items section
        assert "## Work Items" in prompt
        assert "validate" in prompt

        # process should be in the context section
        assert "Already Implemented" in prompt
        assert "process" in prompt

        # Verify structural separation: validate in work section, process in context
        work_start = prompt.index("## Work Items")
        context_start = prompt.index("## Already Implemented")
        validate_pos = prompt.index("validate")
        process_pos = prompt.index("process", context_start)

        assert work_start < validate_pos < context_start
        assert context_start < process_pos

    def test_test_writing_partial_scope_includes_stub_directive(
        self, tmp_path: Path
    ) -> None:
        """Test-writing archetype with partial scope → stub directive injected."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.rs").write_text(
            "fn validate() -> bool {\n    todo!()\n}\n"
        )
        (src / "bar.rs").write_text(
            "fn process() -> i32 {\n"
            "    let result = compute();\n"
            "    result\n"
            "}\n"
        )

        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[
                Deliverable("src/foo.rs", "validate", 1),
                Deliverable("src/bar.rs", "process", 1),
            ],
            depends_on=[],
        )

        scope_result = check_scope(task_group, tmp_path)
        prompt = build_prompt(task_group, scope_result)

        # Must have stub directive since it's test-writing
        assert "<!-- SCOPE_GUARD:STUB_ONLY -->" in prompt
        assert "<!-- /SCOPE_GUARD:STUB_ONLY -->" in prompt


# ---------------------------------------------------------------------------
# TS-87-SMOKE-4: Stub enforcement validates test-writing session output
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestSmokeStubEnforcement:
    """Smoke test: full Path 4 — classify_session → test-writing → validate_stubs → violations.

    Must NOT mock: session_classifier.classify_session, stub_validator.validate_stubs,
    source_parser.extract_modified_functions, stub_patterns.is_stub_body,
    telemetry.record_session_outcome.

    Requirements: 87-REQ-1.2, 87-REQ-1.3
    """

    def test_test_writing_session_with_non_stub_produces_violation(
        self,
    ) -> None:
        """Test-writing session producing full implementation → stub_violation=True."""
        session = SessionResult(
            session_id="sess-smoke-stub-1",
            spec_number=4,
            task_group_number=1,
            branch_name="feature/04/1",
            base_branch="develop",
            exit_status="success",
            duration_seconds=120.0,
            cost_dollars=3.50,
            modified_files=[
                FileChange(
                    file_path="src/validator.rs",
                    language=Language.RUST,
                    diff_text=(
                        "fn validate() -> bool {\n"
                        "    let x = compute();\n"
                        "    x > 0\n"
                        "}\n"
                    ),
                ),
            ],
            commit_count=2,
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[
                Deliverable("src/validator.rs", "validate", 1),
            ],
            depends_on=[],
        )

        # Classify session (no mocking) — should detect stub violation
        outcome = classify_session(session, task_group)

        assert outcome.classification == SessionClassification.SUCCESS
        assert outcome.stub_violation is True
        assert len(outcome.violation_details) >= 1
        assert any(
            v.function_id == "validate" for v in outcome.violation_details
        )

        # Record in DuckDB (no mocking)
        conn = duckdb.connect(":memory:")
        init_schema(conn)
        record_session_outcome(conn, outcome)

        rows = conn.execute(
            "SELECT classification, stub_violation "
            "FROM session_outcomes WHERE session_id = 'sess-smoke-stub-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "success"
        assert rows[0][1] is True

        conn.close()

    def test_test_writing_session_with_stubs_passes(self) -> None:
        """Test-writing session producing only stubs → stub_violation=False."""
        session = SessionResult(
            session_id="sess-smoke-stub-2",
            spec_number=4,
            task_group_number=1,
            branch_name="feature/04/1",
            base_branch="develop",
            exit_status="success",
            duration_seconds=90.0,
            cost_dollars=2.00,
            modified_files=[
                FileChange(
                    file_path="src/validator.rs",
                    language=Language.RUST,
                    diff_text="fn validate() -> bool {\n    todo!()\n}\n",
                ),
            ],
            commit_count=1,
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[
                Deliverable("src/validator.rs", "validate", 1),
            ],
            depends_on=[],
        )

        outcome = classify_session(session, task_group)

        assert outcome.classification == SessionClassification.SUCCESS
        assert outcome.stub_violation is False
        assert len(outcome.violation_details) == 0


# ---------------------------------------------------------------------------
# TS-87-SMOKE-5: No-op and failure classification with telemetry recording
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestSmokeNoOpAndFailure:
    """Smoke test: Paths 5 and 6 — classify_session for no-op and failure.

    Must NOT mock: session_classifier.classify_session,
    telemetry.record_session_outcome.

    Requirements: 87-REQ-4.1, 87-REQ-4.E3
    """

    def test_zero_commits_normal_exit_is_noop(self) -> None:
        """Zero commits + normal exit → no-op, recorded in DuckDB."""
        session = SessionResult(
            session_id="sess-smoke-noop-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="success",
            duration_seconds=106.0,
            cost_dollars=3.50,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )

        # Classify (no mocking)
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.NO_OP

        # Record in DuckDB (no mocking)
        conn = duckdb.connect(":memory:")
        init_schema(conn)
        record_session_outcome(conn, outcome)

        rows = conn.execute(
            "SELECT classification, duration_seconds, cost_dollars "
            "FROM session_outcomes WHERE session_id = 'sess-smoke-noop-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "no-op"
        assert rows[0][1] == 106.0
        assert rows[0][2] == 3.50

        conn.close()

    def test_zero_commits_error_exit_is_failure(self) -> None:
        """Zero commits + error exit → failure (not no-op), recorded in DuckDB."""
        session = SessionResult(
            session_id="sess-smoke-fail-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="error",
            duration_seconds=45.0,
            cost_dollars=1.50,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )

        # Classify (no mocking)
        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.FAILURE

        # Record in DuckDB (no mocking)
        conn = duckdb.connect(":memory:")
        init_schema(conn)
        record_session_outcome(conn, outcome)

        rows = conn.execute(
            "SELECT classification "
            "FROM session_outcomes WHERE session_id = 'sess-smoke-fail-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "failure"

        conn.close()

    def test_harvest_error_classified_correctly(self) -> None:
        """Harvest error exit → harvest-error (not no-op or failure)."""
        session = SessionResult(
            session_id="sess-smoke-harv-1",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="harvest-error",
            duration_seconds=30.0,
            cost_dollars=1.00,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )

        outcome = classify_session(session, task_group)
        assert outcome.classification == SessionClassification.HARVEST_ERROR

        # Record and verify in DuckDB
        conn = duckdb.connect(":memory:")
        init_schema(conn)
        record_session_outcome(conn, outcome)

        rows = conn.execute(
            "SELECT classification "
            "FROM session_outcomes WHERE session_id = 'sess-smoke-harv-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "harvest-error"

        conn.close()

    def test_noop_and_failure_both_recorded_distinct(self) -> None:
        """No-op and failure sessions stored distinctly in the same DuckDB."""
        noop_session = SessionResult(
            session_id="sess-smoke-both-noop",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="success",
            duration_seconds=100.0,
            cost_dollars=3.00,
            modified_files=[],
            commit_count=0,
        )
        fail_session = SessionResult(
            session_id="sess-smoke-both-fail",
            spec_number=4,
            task_group_number=3,
            branch_name="feature/04/3",
            base_branch="develop",
            exit_status="timeout",
            duration_seconds=300.0,
            cost_dollars=10.00,
            modified_files=[],
            commit_count=0,
        )
        task_group = TaskGroup(
            number=3,
            spec_number=4,
            archetype="implementation",
            deliverables=[],
            depends_on=[1],
        )

        noop_outcome = classify_session(noop_session, task_group)
        fail_outcome = classify_session(fail_session, task_group)

        assert noop_outcome.classification == SessionClassification.NO_OP
        assert fail_outcome.classification == SessionClassification.FAILURE

        # Store both in same DuckDB
        conn = duckdb.connect(":memory:")
        init_schema(conn)
        record_session_outcome(conn, noop_outcome)
        record_session_outcome(conn, fail_outcome)

        rows = conn.execute(
            "SELECT session_id, classification FROM session_outcomes "
            "ORDER BY session_id"
        ).fetchall()
        assert len(rows) == 2
        classifications = {r[0]: r[1] for r in rows}
        assert classifications["sess-smoke-both-fail"] == "failure"
        assert classifications["sess-smoke-both-noop"] == "no-op"

        conn.close()
