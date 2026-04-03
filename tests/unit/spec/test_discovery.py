"""Spec discovery tests.

Test Spec: TS-02-1 (sorted discovery), TS-02-2 (filter), TS-02-E1 (no specs dir),
           TS-02-E2 (filter miss), TS-02-E3 (no tasks.md)
Requirements: 02-REQ-1.1, 02-REQ-1.2, 02-REQ-1.3, 02-REQ-1.E1, 02-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.errors import PlanError
from agent_fox.spec.discovery import SpecInfo, discover_specs


class TestDiscoverSpecsSorted:
    """TS-02-1: Discover spec folders sorted by prefix."""

    def test_discovers_all_specs(self, specs_dir_sorted: Path) -> None:
        """Discovery finds all spec folders."""
        specs = discover_specs(specs_dir_sorted)

        assert len(specs) == 3

    def test_sorted_by_prefix(self, specs_dir_sorted: Path) -> None:
        """Specs are returned sorted by numeric prefix."""
        specs = discover_specs(specs_dir_sorted)

        prefixes = [s.prefix for s in specs]
        assert prefixes == [1, 2, 3]

    def test_names_match_folders(self, specs_dir_sorted: Path) -> None:
        """Spec names match the folder names."""
        specs = discover_specs(specs_dir_sorted)

        assert specs[0].name == "01_bar"
        assert specs[1].name == "02_baz"
        assert specs[2].name == "03_foo"

    def test_returns_spec_info_objects(self, specs_dir_sorted: Path) -> None:
        """Discovery returns SpecInfo dataclass instances."""
        specs = discover_specs(specs_dir_sorted)

        assert all(isinstance(s, SpecInfo) for s in specs)

    def test_has_tasks_true(self, specs_dir_sorted: Path) -> None:
        """Specs with tasks.md have has_tasks=True."""
        specs = discover_specs(specs_dir_sorted)

        assert all(s.has_tasks for s in specs)


class TestDiscoverWithFilter:
    """TS-02-2: Discover with --spec filter."""

    def test_filter_returns_single_spec(self, specs_dir_two_specs: Path) -> None:
        """Filter restricts to a single spec."""
        specs = discover_specs(specs_dir_two_specs, filter_spec="02_beta")

        assert len(specs) == 1
        assert specs[0].name == "02_beta"

    def test_filter_by_name(self, specs_dir_two_specs: Path) -> None:
        """Filter matches by spec folder name."""
        specs = discover_specs(specs_dir_two_specs, filter_spec="01_alpha")

        assert len(specs) == 1
        assert specs[0].name == "01_alpha"


class TestNoSpecsDirectory:
    """TS-02-E1: No specs directory raises PlanError."""

    def test_missing_dir_raises_plan_error(self, tmp_path: Path) -> None:
        """Missing .specs/ raises PlanError."""
        nonexistent = tmp_path / ".specs"

        with pytest.raises(PlanError):
            discover_specs(nonexistent)

    def test_empty_dir_raises_plan_error(self, tmp_path: Path) -> None:
        """Empty .specs/ raises PlanError."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        with pytest.raises(PlanError):
            discover_specs(specs_dir)

    def test_error_mentions_specs(self, tmp_path: Path) -> None:
        """Error message mentions 'specifications' or 'specs'."""
        nonexistent = tmp_path / ".specs"

        with pytest.raises(PlanError) as exc_info:
            discover_specs(nonexistent)

        error_msg = str(exc_info.value).lower()
        assert "spec" in error_msg


class TestFilterMatchesNothing:
    """TS-02-E2: Spec filter matches nothing raises PlanError."""

    def test_unknown_filter_raises_plan_error(self, specs_dir_two_specs: Path) -> None:
        """Unknown --spec value raises PlanError."""
        with pytest.raises(PlanError):
            discover_specs(specs_dir_two_specs, filter_spec="99_nonexistent")

    def test_error_lists_available_specs(self, specs_dir_two_specs: Path) -> None:
        """PlanError message contains at least one available spec name."""
        with pytest.raises(PlanError) as exc_info:
            discover_specs(specs_dir_two_specs, filter_spec="99_nonexistent")

        error_msg = str(exc_info.value)
        assert "01_alpha" in error_msg or "02_beta" in error_msg


class TestSpecWithoutTasksMd:
    """TS-02-E3: Spec folder without tasks.md."""

    def test_spec_without_tasks_has_false_flag(self, specs_dir_missing_tasks: Path) -> None:
        """Spec without tasks.md has has_tasks=False."""
        specs = discover_specs(specs_dir_missing_tasks)

        alpha = [s for s in specs if s.name == "01_alpha"][0]
        assert alpha.has_tasks is False

    def test_spec_with_tasks_has_true_flag(self, specs_dir_missing_tasks: Path) -> None:
        """Spec with tasks.md has has_tasks=True."""
        specs = discover_specs(specs_dir_missing_tasks)

        beta = [s for s in specs if s.name == "02_beta"][0]
        assert beta.has_tasks is True
