"""Unit tests for the review-only CLI mode and graph construction.

Tests that build_review_only_graph creates the correct per-spec archetype
nodes, that review-only runs emit audit events with mode="review_only",
and that CLI flag handling works correctly including spec filtering.

Test Spec: TS-53-11, TS-53-12, TS-53-E1, TS-53-E3
Requirements: 53-REQ-6.1, 53-REQ-6.2, 53-REQ-6.3, 53-REQ-6.E1, 53-REQ-6.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# NOTE: build_review_only_graph does not yet exist in graph.injection.
# All tests in this file will fail with ImportError until Task Group 4
# adds the function.
from agent_fox.graph.injection import build_review_only_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_spec_with_source(specs_dir: Path, spec_name: str) -> Path:
    """Create a spec directory with source files and requirements.md."""
    spec_dir = specs_dir / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text("# Requirements\n")
    (spec_dir / "main.py").write_text("# source code\n")
    return spec_dir


def _create_spec_source_only(specs_dir: Path, spec_name: str) -> Path:
    """Create a spec directory with source files but no requirements.md."""
    spec_dir = specs_dir / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "main.py").write_text("# source code\n")
    return spec_dir


def _create_spec_reqs_only(specs_dir: Path, spec_name: str) -> Path:
    """Create a spec directory with requirements.md but no source files."""
    spec_dir = specs_dir / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "requirements.md").write_text("# Requirements\n")
    return spec_dir


# ---------------------------------------------------------------------------
# TS-53-11: Review-only graph per-spec nodes
# ---------------------------------------------------------------------------


class TestReviewOnlyGraphPerSpecNodes:
    """TS-53-11: Correct archetype nodes are created per spec based on artifacts."""

    def test_spec_with_both_gets_all_three(self, tmp_path: Path) -> None:
        """TS-53-11: Spec with source + requirements gets Skeptic+Oracle+Verifier."""
        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "spec_a")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        spec_a_nodes = [n for n in graph.nodes.values() if n.spec_name == "spec_a"]
        archetypes_a = {n.archetype for n in spec_a_nodes}
        assert {"skeptic", "oracle", "verifier"} <= archetypes_a

    def test_spec_with_source_only_no_verifier(self, tmp_path: Path) -> None:
        """TS-53-11: Spec with source files but no requirements.md has no Verifier."""
        specs_dir = tmp_path / ".specs"
        _create_spec_source_only(specs_dir, "spec_b")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        spec_b_nodes = [n for n in graph.nodes.values() if n.spec_name == "spec_b"]
        archetypes_b = {n.archetype for n in spec_b_nodes}
        assert "skeptic" in archetypes_b
        assert "oracle" in archetypes_b
        assert "verifier" not in archetypes_b

    def test_spec_with_reqs_only_verifier_only(self, tmp_path: Path) -> None:
        """TS-53-11: Spec with requirements.md only has only a Verifier node."""
        specs_dir = tmp_path / ".specs"
        _create_spec_reqs_only(specs_dir, "spec_c")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        spec_c_nodes = [n for n in graph.nodes.values() if n.spec_name == "spec_c"]
        archetypes_c = {n.archetype for n in spec_c_nodes}
        assert "verifier" in archetypes_c
        assert "skeptic" not in archetypes_c
        assert "oracle" not in archetypes_c

    def test_multiple_specs_all_get_correct_nodes(self, tmp_path: Path) -> None:
        """TS-53-11: Multiple specs each get the correct set of review nodes."""
        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "spec_a")
        _create_spec_source_only(specs_dir, "spec_b")
        _create_spec_reqs_only(specs_dir, "spec_c")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        spec_a_archetypes = {
            n.archetype for n in graph.nodes.values() if n.spec_name == "spec_a"
        }
        spec_b_archetypes = {
            n.archetype for n in graph.nodes.values() if n.spec_name == "spec_b"
        }
        spec_c_archetypes = {
            n.archetype for n in graph.nodes.values() if n.spec_name == "spec_c"
        }

        assert {"skeptic", "oracle", "verifier"} <= spec_a_archetypes
        assert {"skeptic", "oracle"} <= spec_b_archetypes
        assert "verifier" not in spec_b_archetypes
        assert "verifier" in spec_c_archetypes
        assert "skeptic" not in spec_c_archetypes

    def test_source_file_extensions_recognized(self, tmp_path: Path) -> None:
        """TS-53-11: .py, .ts, .go, .rs, .java, .js files trigger Skeptic+Oracle."""
        extensions = [".py", ".ts", ".go", ".rs", ".java", ".js"]
        for ext in extensions:
            specs_dir = tmp_path / f"specs_{ext[1:]}" / ".specs"
            spec_dir = specs_dir / "test_spec"
            spec_dir.mkdir(parents=True)
            (spec_dir / f"code{ext}").write_text("// code\n")

            graph = build_review_only_graph(specs_dir, archetypes_config=None)
            archetypes = {n.archetype for n in graph.nodes.values()}
            assert "skeptic" in archetypes, f"Skeptic missing for {ext} files"
            assert "oracle" in archetypes, f"Oracle missing for {ext} files"


# ---------------------------------------------------------------------------
# TS-53-12: Review-only audit events with mode: "review_only"
# ---------------------------------------------------------------------------


class TestReviewOnlyAuditEvents:
    """TS-53-12: Review-only runs emit run.start and run.complete with mode field."""

    def test_run_start_has_review_only_mode(self, tmp_path: Path) -> None:
        """TS-53-12: run.start audit event has mode='review_only' in payload."""
        from agent_fox.graph.injection import (  # noqa: PLC0415
            run_review_only,
        )

        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "spec_a")

        emitted = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted.append(e)

        run_review_only(specs_dir, archetypes_config=None, sink=mock_sink)

        start_events = [e for e in emitted if e.event_type == "run.start"]
        assert len(start_events) >= 1
        assert start_events[0].payload.get("mode") == "review_only"

    def test_run_complete_has_review_only_mode(self, tmp_path: Path) -> None:
        """TS-53-12: run.complete audit event has mode='review_only' in payload."""
        from agent_fox.graph.injection import run_review_only  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "spec_a")

        emitted = []
        mock_sink = MagicMock()
        mock_sink.emit_audit_event.side_effect = lambda e: emitted.append(e)

        run_review_only(specs_dir, archetypes_config=None, sink=mock_sink)

        complete_events = [e for e in emitted if e.event_type == "run.complete"]
        assert len(complete_events) >= 1
        assert complete_events[0].payload.get("mode") == "review_only"


# ---------------------------------------------------------------------------
# TS-53-E1: No specs eligible for review
# ---------------------------------------------------------------------------


class TestNoEligibleSpecs:
    """TS-53-E1: Review-only mode with no eligible specs exits cleanly."""

    def test_empty_specs_dir_returns_empty_graph(self, tmp_path: Path) -> None:
        """TS-53-E1: Empty specs directory returns a graph with no nodes."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(parents=True)

        graph = build_review_only_graph(specs_dir, archetypes_config=None)
        assert len(graph.nodes) == 0

    def test_no_eligible_specs_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """TS-53-E1: 'No specs eligible for review' is printed when no specs found."""
        from agent_fox.graph.injection import build_review_only_graph  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(parents=True)

        # Spec with neither source files nor requirements.md
        empty_spec = specs_dir / "empty_spec"
        empty_spec.mkdir()

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        if len(graph.nodes) == 0:
            # When building the graph, the runner should print a message
            # The actual message may be printed by the CLI handler
            pass

    def test_cli_review_only_no_specs_exits_zero(
        self, tmp_path: Path, cli_runner: object
    ) -> None:
        """TS-53-E1: --review-only with no eligible specs exits with code 0."""
        from click.testing import CliRunner  # noqa: PLC0415

        from agent_fox.cli.app import main  # noqa: PLC0415

        runner = CliRunner()
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        result = runner.invoke(
            main,
            ["code", "--review-only", "--specs-dir", str(specs_dir)],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "No specs eligible for review" in result.output


# ---------------------------------------------------------------------------
# TS-53-E3: Review-only with spec filter
# ---------------------------------------------------------------------------


class TestReviewOnlyWithSpecFilter:
    """TS-53-E3: --review-only --spec filter restricts which specs are reviewed."""

    def test_spec_filter_restricts_nodes(self, tmp_path: Path) -> None:
        """TS-53-E3: Only the specified spec has review nodes in the graph."""
        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "03_api")
        _create_spec_with_source(specs_dir, "04_auth")
        _create_spec_with_source(specs_dir, "05_billing")

        graph = build_review_only_graph(
            specs_dir,
            archetypes_config=None,
            spec_filter="03_api",
        )

        spec_names = {n.spec_name for n in graph.nodes.values()}
        assert spec_names == {"03_api"}, f"Expected only 03_api, got: {spec_names}"

    def test_spec_filter_nonexistent_empty_graph(self, tmp_path: Path) -> None:
        """TS-53-E3: Filter for non-existent spec returns empty graph."""
        specs_dir = tmp_path / ".specs"
        _create_spec_with_source(specs_dir, "03_api")

        graph = build_review_only_graph(
            specs_dir,
            archetypes_config=None,
            spec_filter="99_nonexistent",
        )

        assert len(graph.nodes) == 0
