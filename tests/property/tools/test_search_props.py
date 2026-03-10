"""Property tests for search tool.

Test Spec: TS-29-P7 (context merge — no duplicate line numbers)
Requirements: 29-REQ-4.2, 29-REQ-4.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    n=st.integers(min_value=10, max_value=100),
    num_markers=st.integers(min_value=1, max_value=5),
    context=st.integers(min_value=0, max_value=10),
    data=st.data(),
)
@settings(max_examples=50)
def test_context_merge_no_duplicates(
    n: int, num_markers: int, context: int, data: st.DataObject, tmp_path_factory
) -> None:
    """TS-29-P7: Overlapping context ranges produce no duplicate line numbers."""
    from agent_fox.tools.search import fox_search
    from agent_fox.tools.types import SearchResult

    # Pick unique match positions within [1, n]
    positions = data.draw(
        st.lists(
            st.integers(min_value=1, max_value=n),
            min_size=num_markers,
            max_size=num_markers,
            unique=True,
        )
    )

    # Build file with markers at chosen positions
    lines = []
    for i in range(1, n + 1):
        if i in positions:
            lines.append(f"line {i} MARKER\n")
        else:
            lines.append(f"line {i} normal\n")

    tmp_dir = tmp_path_factory.mktemp("search_prop")
    f = tmp_dir / "test.txt"
    f.write_text("".join(lines))

    result = fox_search(str(f), "MARKER", context=context)
    assert isinstance(result, SearchResult)
    assert result.total_matches == len(positions)

    # Collect all line numbers across all match blocks
    all_numbers = [ln.line_number for m in result.matches for ln in m.lines]

    # No duplicates
    assert len(all_numbers) == len(set(all_numbers)), (
        f"Duplicate line numbers found: {sorted(all_numbers)}"
    )

    # All line numbers should be in ascending order within each block
    for m in result.matches:
        numbers = [ln.line_number for ln in m.lines]
        assert numbers == sorted(numbers)
