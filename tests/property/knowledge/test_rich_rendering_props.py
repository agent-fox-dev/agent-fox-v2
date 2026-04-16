"""Property-based tests for rich memory rendering.

Test Spec: TS-111-P1 through TS-111-P6
Requirements: 111-REQ-2.2, 111-REQ-3.1, 111-REQ-3.E1, 111-REQ-4.2,
              111-REQ-5.1, 111-REQ-5.2, 111-REQ-7.E1, 111-REQ-7.E2
"""

from __future__ import annotations

import re
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.rendering import (
    Enrichments,
    _format_relative_age,
    _render_fact,
    load_enrichments,
    render_summary,
)

_AGE_PATTERN = re.compile(r"^\d+(d|mo|y) ago$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "A property test fact",
    category: str = "gotcha",
    confidence: float = 0.90,
    created_at: str = "2026-04-10T12:00:00",
) -> Fact:
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category=category,
        spec_name="test_spec",
        keywords=[],
        confidence=confidence,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# TS-111-P1: Age format correctness
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestAgeFormatCorrectness:
    """TS-111-P1: _format_relative_age always returns the correct unit.

    Requirement: 111-REQ-2.2
    """

    @given(days_ago=st.integers(min_value=0, max_value=3650))
    def test_age_format_correctness(self, days_ago: int) -> None:
        """For any valid timestamp, result matches pattern and uses correct unit."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        created_at_dt = now - timedelta(days=days_ago)
        created_at = created_at_dt.strftime("%Y-%m-%dT%H:%M:%S")

        result = _format_relative_age(created_at, now)

        assert result is not None
        assert _AGE_PATTERN.match(result), f"Result {result!r} doesn't match age pattern"

        if days_ago < 60:
            assert result == f"{days_ago}d ago"
        elif days_ago < 365:
            assert result == f"{days_ago // 30}mo ago"
        else:
            assert result == f"{days_ago // 365}y ago"


# ---------------------------------------------------------------------------
# TS-111-P2: Sort stability
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSortStability:
    """TS-111-P2: Facts are sorted by confidence desc, then created_at desc.

    Requirements: 111-REQ-3.1, 111-REQ-3.E1
    """

    @given(
        fact_data=st.lists(
            st.tuples(
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
                st.integers(min_value=0, max_value=3650),
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_sort_order_correctness(self, fact_data: list[tuple[float, int]]) -> None:
        """Higher confidence facts appear before lower confidence in output."""
        base_date = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        facts = [
            _make_fact(
                fact_id=str(uuid.uuid4()),
                content=f"Fact {i} conf={conf:.4f} days={days}",
                category="gotcha",
                confidence=conf,
                created_at=(base_date - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            )
            for i, (conf, days) in enumerate(fact_data)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "memory.md"
            with patch("agent_fox.knowledge.rendering.read_all_facts", return_value=facts):
                render_summary(conn=None, output_path=output_path)
            content = output_path.read_text()

        positions = {fact.content: content.find(fact.content) for fact in facts}

        # Verify ordering within same category
        for i, fact_i in enumerate(facts):
            for fact_j in facts[i + 1 :]:
                pos_i = positions[fact_i.content]
                pos_j = positions[fact_j.content]
                if pos_i == -1 or pos_j == -1:
                    continue
                conf_i = fact_i.confidence
                conf_j = fact_j.confidence
                if conf_i > conf_j + 1e-9:
                    assert pos_i < pos_j, (
                        f"Fact with confidence {conf_i:.4f} should appear before "
                        f"{conf_j:.4f}"
                    )
                elif conf_j > conf_i + 1e-9:
                    assert pos_i > pos_j, (
                        f"Fact with confidence {conf_i:.4f} should appear after "
                        f"{conf_j:.4f}"
                    )

    @given(
        fact_data=st.lists(
            st.tuples(
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
                st.integers(min_value=0, max_value=3650),
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_sort_is_deterministic(self, fact_data: list[tuple[float, int]]) -> None:
        """Sorting the same list twice produces identical output."""
        base_date = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        facts = [
            _make_fact(
                fact_id=str(uuid.uuid4()),
                content=f"Fact {i} conf={conf:.4f}",
                category="gotcha",
                confidence=conf,
                created_at=(base_date - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            )
            for i, (conf, days) in enumerate(fact_data)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            out1 = Path(tmpdir) / "memory_a.md"
            out2 = Path(tmpdir) / "memory_b.md"
            with patch("agent_fox.knowledge.rendering.read_all_facts", return_value=facts):
                render_summary(conn=None, output_path=out1)
                render_summary(conn=None, output_path=out2)
            assert out1.read_text() == out2.read_text()


# ---------------------------------------------------------------------------
# TS-111-P3: Sub-bullet bounds
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestSubbulletBounds:
    """TS-111-P3: Sub-bullet counts are bounded by their limits.

    Requirements: 111-REQ-4.2, 111-REQ-5.1, 111-REQ-5.2
    """

    @given(
        n_causes=st.integers(min_value=0, max_value=10),
        n_effects=st.integers(min_value=0, max_value=10),
        n_entity_paths=st.integers(min_value=0, max_value=20),
    )
    def test_subbullet_bounds(
        self, n_causes: int, n_effects: int, n_entity_paths: int
    ) -> None:
        """At most 2 causes, 2 effects, 3 paths regardless of input count."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        enrichments = Enrichments(
            causes={fact.id: [f"Cause {i} content" for i in range(n_causes)]},
            effects={fact.id: [f"Effect {i} content" for i in range(n_effects)]},
            entity_paths={fact.id: [f"path/file{i}.py" for i in range(n_entity_paths)]},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "  - cause:" in line]
        effect_lines = [line for line in result.splitlines() if "  - effect:" in line]
        files_lines = [line for line in result.splitlines() if "  - files:" in line]

        assert len(cause_lines) <= 2
        assert len(effect_lines) <= 2
        assert len(files_lines) <= 1  # paths are comma-joined on one line

        if n_entity_paths > 3:
            overflow = n_entity_paths - 3
            assert f"+{overflow} more" in result


# ---------------------------------------------------------------------------
# TS-111-P4: Enrichment independence
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestEnrichmentIndependence:
    """TS-111-P4: Failure in one enrichment query doesn't block the others.

    Requirement: 111-REQ-7.E1
    """

    @given(failing_query=st.integers(min_value=1, max_value=4))
    def test_enrichment_independence(self, failing_query: int) -> None:
        """Each of the 4 queries can fail independently without aborting rendering."""
        fact_id = str(uuid.uuid4())
        call_count = [0]

        def execute_side_effect(sql: str, *args: object, **kwargs: object) -> MagicMock:
            call_count[0] += 1
            if call_count[0] == failing_query:
                raise duckdb.Error(f"Simulated failure in query {failing_query}")
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            return cursor

        conn = MagicMock()
        conn.execute.side_effect = execute_side_effect

        # Should not raise
        enrichments = load_enrichments(conn, [fact_id])

        assert isinstance(enrichments.causes, dict)
        assert isinstance(enrichments.effects, dict)
        assert isinstance(enrichments.entity_paths, dict)
        assert isinstance(enrichments.superseded, dict)


# ---------------------------------------------------------------------------
# TS-111-P5: Graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestGracefulDegradation:
    """TS-111-P5: render_summary(conn=None) produces valid markdown for any facts.

    Requirement: 111-REQ-7.E2
    """

    @given(
        fact_data=st.lists(
            st.tuples(
                st.text(
                    min_size=1,
                    max_size=40,
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        whitelist_characters=" _",
                    ),
                ),
                st.sampled_from(["gotcha", "pattern", "decision"]),
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            ),
            min_size=1,
            max_size=8,
        )
    )
    def test_graceful_degradation(
        self, fact_data: list[tuple[str, str, float]]
    ) -> None:
        """render_summary(conn=None) produces valid markdown with no sub-bullets."""
        facts = [
            _make_fact(
                fact_id=str(uuid.uuid4()),
                content=content.strip() or "fallback content",
                category=cat,
                confidence=conf,
            )
            for content, cat, conf in fact_data
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "memory.md"
            with patch(
                "agent_fox.knowledge.rendering.read_all_facts", return_value=facts
            ):
                render_summary(conn=None, output_path=output_path)
            content = output_path.read_text()

        # Valid markdown starts with the heading
        assert content.startswith("# Agent-Fox Memory")

        # All facts appear in the output
        for fact in facts:
            assert fact.content in content

        # No enrichment sub-bullets since conn=None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                assert not stripped.startswith("- cause:")
                assert not stripped.startswith("- effect:")
                assert not stripped.startswith("- files:")
                assert not stripped.startswith("- replaces:")


# ---------------------------------------------------------------------------
# TS-111-P6: Truncation boundary
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestTruncationBoundary:
    """TS-111-P6: Truncation at exact boundaries for cause (60) and superseded (80).

    Requirements: 111-REQ-5.1, 111-REQ-6.1
    """

    @given(length=st.integers(min_value=1, max_value=200))
    def test_truncation_boundary_cause(self, length: int) -> None:
        """Strings ≤60 chars unchanged; >60 chars truncated to 60 plus ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content = "X" * length
        enrichments = Enrichments(
            causes={fact.id: [content]},
            effects={},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "  - cause:" in line]
        assert len(cause_lines) >= 1
        cause_text = cause_lines[0]

        if length <= 60:
            assert content in cause_text
            # No ellipsis appended to original content
            assert content + "…" not in cause_text
            assert content + "..." not in cause_text
        else:
            assert "X" * 60 in cause_text
            assert "X" * 61 not in cause_text

    @given(length=st.integers(min_value=1, max_value=200))
    def test_truncation_boundary_superseded(self, length: int) -> None:
        """Strings ≤80 chars unchanged; >80 chars truncated to 80 plus ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content = "Y" * length
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={},
            superseded={fact.id: content},
        )

        result = _render_fact(fact, enrichments, now)

        replaces_lines = [line for line in result.splitlines() if "  - replaces:" in line]
        assert len(replaces_lines) >= 1
        replaces_text = replaces_lines[0]

        if length <= 80:
            assert content in replaces_text
            assert content + "…" not in replaces_text
            assert content + "..." not in replaces_text
        else:
            assert "Y" * 80 in replaces_text
            assert "Y" * 81 not in replaces_text
