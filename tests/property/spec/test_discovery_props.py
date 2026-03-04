"""Property tests for spec discovery.

Test Spec: TS-02-P5 (discovery sort order)
Property: Property 5 from design.md
Requirements: 02-REQ-1.1
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.spec.discovery import discover_specs

# -- Strategies for generating spec folder names ------------------------------


@st.composite
def valid_spec_folder_sets(draw: st.DrawFn) -> tuple[list[str], Path]:
    """Generate sets of valid spec folder names with NN_ prefix.

    Creates a tmp_path-like structure with 1-10 spec folders,
    each having a tasks.md file.

    Returns:
        Tuple of (folder_names, tmp_specs_dir_path).
    """
    # Generate unique prefixes
    n = draw(st.integers(min_value=1, max_value=10))
    prefixes = draw(
        st.lists(
            st.integers(min_value=1, max_value=99),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    folder_names = [f"{p:02d}_spec_{p}" for p in prefixes]
    return folder_names, Path("unused")  # path created in test


class TestDiscoverySortOrder:
    """TS-02-P5: Discovered specs are always sorted by numeric prefix.

    Property 5: For any set of spec folders, discover_specs() returns them
    sorted by numeric prefix in ascending order.
    """

    @given(data=st.data())
    @settings(max_examples=50)
    def test_prefixes_sorted_ascending(
        self, data: st.DataObject, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """Discovery always returns specs sorted by prefix."""
        # Generate unique prefixes
        n = data.draw(st.integers(min_value=1, max_value=10))
        prefixes = data.draw(
            st.lists(
                st.integers(min_value=1, max_value=99),
                min_size=n,
                max_size=n,
                unique=True,
            )
        )

        # Create filesystem structure
        tmp_dir = tmp_path_factory.mktemp("specs")
        specs_dir = tmp_dir / ".specs"
        specs_dir.mkdir()

        for p in prefixes:
            folder = specs_dir / f"{p:02d}_spec_{p}"
            folder.mkdir()
            (folder / "tasks.md").write_text(f"- [ ] 1. Task for spec {p}\n")

        # Run discovery
        specs = discover_specs(specs_dir)

        # Verify sorted
        result_prefixes = [s.prefix for s in specs]
        assert result_prefixes == sorted(result_prefixes), (
            f"Prefixes not sorted: {result_prefixes}"
        )
