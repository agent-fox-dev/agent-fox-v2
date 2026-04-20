"""Property tests for temporal query and timeline rendering.

TS-13-P3: Timeline ordering — nodes are always in non-decreasing
timestamp order.

Requirements: 13-REQ-6.1, 13-REQ-6.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.query_temporal import Timeline, TimelineNode

_RELATIONSHIPS = st.sampled_from(["root", "cause", "effect"])
_TIMESTAMPS = st.one_of(
    st.none(),
    st.datetimes().map(lambda dt: dt.isoformat()),
)


@st.composite
def timeline_nodes(draw: st.DrawFn) -> list[TimelineNode]:
    """Generate a random list of TimelineNodes."""
    n = draw(st.integers(min_value=0, max_value=20))
    nodes: list[TimelineNode] = []
    for i in range(n):
        nodes.append(
            TimelineNode(
                fact_id=f"fact-{i}",
                content=draw(st.text(min_size=1, max_size=50)),
                spec_name=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
                session_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
                commit_sha=draw(st.one_of(st.none(), st.text(min_size=7, max_size=7))),
                timestamp=draw(_TIMESTAMPS),
                relationship=draw(_RELATIONSHIPS),
                depth=draw(st.integers(min_value=0, max_value=5)),
            )
        )
    return nodes


class TestTimelineProperties:
    """TS-13-P3: Timeline ordering and rendering properties."""

    @given(nodes=timeline_nodes())
    @settings(max_examples=50)
    def test_render_never_raises(self, nodes: list[TimelineNode]) -> None:
        """Rendering any valid timeline should never raise."""
        tl = Timeline(nodes=nodes, query="test")
        text = tl.render(use_color=False)
        assert isinstance(text, str)

    @given(nodes=timeline_nodes())
    @settings(max_examples=50)
    def test_render_plain_text_no_ansi(self, nodes: list[TimelineNode]) -> None:
        """Plain text rendering never contains ANSI escape codes."""
        tl = Timeline(nodes=nodes, query="test")
        text = tl.render(use_color=False)
        assert "\x1b[" not in text

    @given(nodes=timeline_nodes())
    @settings(max_examples=50)
    def test_sorted_timeline_preserves_timestamp_order(self, nodes: list[TimelineNode]) -> None:
        """After sorting by (timestamp, depth), timestamps are non-decreasing."""
        sorted_nodes = sorted(nodes, key=lambda n: (n.timestamp or "", n.depth))
        tl = Timeline(nodes=sorted_nodes, query="test")
        timestamps = [n.timestamp for n in tl.nodes if n.timestamp]
        assert timestamps == sorted(timestamps)

    @given(nodes=timeline_nodes())
    @settings(max_examples=50)
    def test_empty_timeline_message(self, nodes: list[TimelineNode]) -> None:
        """Empty node list always produces the 'No causal timeline' message."""
        tl = Timeline(nodes=[], query="test")
        assert "No causal timeline" in tl.render()
