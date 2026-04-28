"""Property tests for context rendering and convergence equivalence.

Test Spec: TS-27-P3, TS-27-P4, TS-27-P7
Requirements: 27-REQ-5.1, 27-REQ-5.3, 27-REQ-5.E1, 27-REQ-6.1, 27-REQ-6.2,
              27-REQ-10.1
"""

from __future__ import annotations

import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
)
from agent_fox.session.convergence import (
    Finding,
    converge_skeptic,
    converge_skeptic_records,
)
from agent_fox.session.prompt import render_review_context
from tests.unit.knowledge.conftest import create_schema

VALID_SEVERITIES = ("critical", "major", "minor", "observation")

# Only these severities are persisted by insert_findings() (issue #553).
ACTIONABLE_SEVERITIES = ("critical", "major")


@st.composite
def review_finding_list(draw: st.DrawFn) -> list[ReviewFinding]:
    """Generate a list of ReviewFinding objects with actionable severities.

    Restricted to critical/major because insert_findings() drops minor and
    observation findings (issue #553). The rendering properties tested here
    are about what appears in the output given the DB state — non-actionable
    findings are never in the DB and thus never appear in renders.
    """
    n = draw(st.integers(min_value=1, max_value=10))
    session_id = f"session-{draw(st.uuids())}"
    return [
        ReviewFinding(
            id=str(uuid.uuid4()),
            severity=draw(st.sampled_from(list(ACTIONABLE_SEVERITIES))),
            description=draw(
                st.text(
                    min_size=1,
                    max_size=80,
                    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
                )
            ),
            requirement_ref=None,
            spec_name="prop_test_spec",
            task_group="1",
            session_id=session_id,
        )
        for _ in range(n)
    ]


class TestContextRenderingDeterminism:
    """TS-27-P3: Property 3 -- Context Rendering Structural Consistency.

    For any set of active findings, render_review_context produces
    structurally consistent output on repeated calls with the same DB state.

    Note: nonce-tagged boundaries (from sanitize_prompt_content) make
    exact string equality across calls impossible by design. The invariant
    is that all finding descriptions appear in both outputs.
    """

    @given(findings=review_finding_list())
    @settings(max_examples=20)
    def test_render_determinism(self, findings: list[ReviewFinding]) -> None:
        """Two calls to render_review_context include the same descriptions."""
        conn = duckdb.connect(":memory:")
        create_schema(conn)
        insert_findings(conn, findings)

        md1 = render_review_context(conn, "prop_test_spec")
        md2 = render_review_context(conn, "prop_test_spec")

        # Both renders must be non-None (same findings -> same non-empty result)
        assert (md1 is None) == (md2 is None)
        if md1 is None or md2 is None:
            conn.close()
            return

        # Every finding description must appear in both renders
        for finding in findings:
            assert finding.description in md1, f"Description '{finding.description}' missing from first render"
            assert finding.description in md2, f"Description '{finding.description}' missing from second render"

        # Structural markers must be present in both renders
        assert "## Skeptic Review" in md1
        assert "## Skeptic Review" in md2
        assert "Summary:" in md1
        assert "Summary:" in md2

        conn.close()


class TestConvergenceEquivalence:
    """TS-27-P4: Property 4 -- Convergence Equivalence.

    converge_skeptic_records produces the same blocking decision as
    converge_skeptic for equivalent input data.
    """

    @given(
        instance_count=st.integers(min_value=2, max_value=4),
        severity=st.sampled_from(list(VALID_SEVERITIES)),
        desc=st.text(
            min_size=1,
            max_size=40,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        threshold=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=30)
    def test_convergence_equivalence(
        self,
        instance_count: int,
        severity: str,
        desc: str,
        threshold: int,
    ) -> None:
        """Old and new convergence agree on blocking decision."""
        # Build identical input for both old and new convergence
        old_instances: list[list[Finding]] = []
        new_instances: list[list[ReviewFinding]] = []

        for i in range(instance_count):
            old_instances.append([Finding(severity=severity, description=desc)])
            new_instances.append(
                [
                    ReviewFinding(
                        id=str(uuid.uuid4()),
                        severity=severity,
                        description=desc,
                        requirement_ref=None,
                        spec_name="test",
                        task_group="1",
                        session_id=f"s{i}",
                    )
                ]
            )

        old_merged, old_blocked = converge_skeptic(old_instances, threshold)
        new_merged, new_blocked = converge_skeptic_records(new_instances, threshold)

        assert old_blocked == new_blocked
        assert len(old_merged) == len(new_merged)


class TestFallbackCorrectness:
    """TS-27-P7: Property 7 -- Fallback Correctness.

    Context includes review content when available from DB or file.
    Updated for spec 38: DuckDB is now mandatory, so conn is always provided.
    """

    @given(
        has_db_findings=st.booleans(),
        has_file=st.booleans(),
    )
    @settings(max_examples=10)
    def test_fallback_correctness(
        self,
        has_db_findings: bool,
        has_file: bool,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Context contains review content when available from either source."""
        from hypothesis import assume

        from agent_fox.session.prompt import assemble_context

        assume(has_db_findings or has_file)

        tmp_path = tmp_path_factory.mktemp("fallback")
        spec_dir = tmp_path / "test_spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\n")

        # DuckDB is always required (38-REQ-4.1)
        conn = duckdb.connect(":memory:")
        create_schema(conn)

        if has_db_findings:
            finding = ReviewFinding(
                id=str(uuid.uuid4()),
                severity="major",
                description="DB finding",
                requirement_ref=None,
                spec_name="test_spec",
                task_group="1",
                session_id="s1",
            )
            insert_findings(conn, [finding])

        if has_file:
            (spec_dir / "review.md").write_text(
                "# Skeptic Review\n\n## Critical Findings\n- [severity: major] File finding\n"
            )

        result = assemble_context(spec_dir, 1, conn=conn)

        # Review content should appear from one source
        has_review = "Skeptic Review" in result or "review" in result.lower()
        assert has_review

        conn.close()


# Need pytest for tmp_path_factory
import pytest  # noqa: E402
