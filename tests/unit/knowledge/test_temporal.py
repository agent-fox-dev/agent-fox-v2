"""Tests for temporal queries and timeline rendering.

Test Spec: TS-13-9, TS-13-10, TS-13-E4
Requirements: 13-REQ-4.1, 13-REQ-4.2, 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3
"""

from __future__ import annotations

import duckdb

from agent_fox.knowledge.temporal import (
    Timeline,
    TimelineNode,
    build_timeline,
)
from tests.unit.knowledge.conftest import (
    FACT_AAA,
    FACT_BBB,
    FACT_CCC,
    FACT_DDD,
    FACT_EEE,
)


class TestBuildTimeline:
    """TS-13-9: Build timeline from seed facts.

    Requirements: 13-REQ-4.1, 13-REQ-6.1, 13-REQ-6.2
    """

    def test_builds_timeline_from_seed(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Building a timeline from aaa produces ordered nodes."""
        timeline = build_timeline(causal_db, [FACT_AAA])
        assert len(timeline.nodes) == 4
        assert timeline.nodes[0].fact_id == FACT_AAA
        assert timeline.nodes[0].depth == 0

    def test_timeline_ordered_by_timestamp(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Timeline nodes are in ascending timestamp order."""
        timeline = build_timeline(causal_db, [FACT_AAA])
        timestamps = [n.timestamp for n in timeline.nodes if n.timestamp]
        assert timestamps == sorted(timestamps)

    def test_timeline_contains_all_chain_facts(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Timeline from aaa contains aaa, bbb, ccc, eee."""
        timeline = build_timeline(causal_db, [FACT_AAA])
        fact_ids = {n.fact_id for n in timeline.nodes}
        assert FACT_AAA in fact_ids
        assert FACT_BBB in fact_ids
        assert FACT_CCC in fact_ids
        assert FACT_EEE in fact_ids


class TestTimelineRender:
    """TS-13-10: Timeline render produces plain text.

    Requirement: 13-REQ-6.3
    """

    def test_render_plain_text_no_ansi(self) -> None:
        """Rendering with use_color=False produces no ANSI codes."""
        nodes = [
            TimelineNode(
                fact_id=FACT_AAA,
                content="User.email changed to nullable",
                spec_name="07_oauth",
                session_id="07/3",
                commit_sha="a1b2c3d",
                timestamp="2025-11-03T14:22:00",
                relationship="root",
                depth=0,
            ),
            TimelineNode(
                fact_id=FACT_BBB,
                content="test_user_model.py assertions failed",
                spec_name="09_user_tests",
                session_id="09/1",
                commit_sha="e4f5g6h",
                timestamp="2025-11-17T09:15:00",
                relationship="effect",
                depth=1,
            ),
        ]
        timeline = Timeline(nodes=nodes, query="test query")
        text = timeline.render(use_color=False)
        assert len(text) > 0
        assert "\x1b[" not in text
        assert "User.email changed to nullable" in text
        assert "07_oauth" in text

    def test_render_includes_provenance(self) -> None:
        """Rendered timeline includes session_id and commit_sha."""
        nodes = [
            TimelineNode(
                fact_id=FACT_AAA,
                content="User.email changed to nullable",
                spec_name="07_oauth",
                session_id="07/3",
                commit_sha="a1b2c3d",
                timestamp="2025-11-03T14:22:00",
                relationship="root",
                depth=0,
            ),
        ]
        timeline = Timeline(nodes=nodes)
        text = timeline.render(use_color=False)
        assert "07/3" in text
        assert "a1b2c3d" in text


class TestTimelineNoLinks:
    """TS-13-E4: Timeline with no causal links.

    Requirement: 13-REQ-4.1
    """

    def test_isolated_fact_timeline(
        self, causal_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Building a timeline from a fact with no links returns just that fact."""
        timeline = build_timeline(causal_db, [FACT_DDD])
        assert len(timeline.nodes) == 1
        assert timeline.nodes[0].fact_id == FACT_DDD
        assert timeline.nodes[0].relationship == "root"
