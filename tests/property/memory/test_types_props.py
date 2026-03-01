"""Property tests for category completeness.

Test Spec: TS-05-P5 (category completeness)
Property: Property 3 from design.md
Requirement: 05-REQ-2.1
"""

from __future__ import annotations

from agent_fox.memory.render import CATEGORY_TITLES
from agent_fox.memory.types import Category


class TestCategoryCompleteness:
    """TS-05-P5: Category completeness.

    Every Category enum value has a corresponding CATEGORY_TITLES entry.

    Property 3 from design.md.
    """

    def test_every_category_has_title(self) -> None:
        """Every Category enum value has a corresponding CATEGORY_TITLES entry."""
        for cat in Category:
            assert cat.value in CATEGORY_TITLES, (
                f"Category {cat.value} missing from CATEGORY_TITLES"
            )

    def test_no_extra_titles(self) -> None:
        """CATEGORY_TITLES has no entries without a Category enum value."""
        category_values = {c.value for c in Category}
        for key in CATEGORY_TITLES:
            assert key in category_values, (
                f"CATEGORY_TITLES has key '{key}' with no Category enum value"
            )

    def test_category_count_matches_titles(self) -> None:
        """Category enum and CATEGORY_TITLES have the same count."""
        assert len(list(Category)) == len(CATEGORY_TITLES)
