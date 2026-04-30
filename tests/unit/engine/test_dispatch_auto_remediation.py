"""Auto-remediation tests for pre-session workspace health check.

When prepare_launch detects untracked files matching known build-artifact
patterns, it must attempt force_clean_workspace() before blocking — instead
of immediately cascade-blocking the entire dependency graph.

The patch targets use the source module path (agent_fox.workspace.health.*)
because check_workspace_health and force_clean_workspace are imported
dynamically inside prepare_launch via ``from agent_fox.workspace.health import …``.

Test Spec: 571-AC-1 (auto-clean known artifacts), 571-AC-2 (force_clean config),
           571-AC-3 (cascade scope), 571-AC-5 (fail-open on exception)
Requirements: 571-AC-1, 571-AC-2, 571-AC-3, 571-AC-5
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.engine.dispatch import DispatchManager, _is_known_build_artifact
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.workspace.health import HealthReport

# Patch targets: functions imported *inside* prepare_launch from the health module.
_HEALTH_CHECK = "agent_fox.workspace.health.check_workspace_health"
_FORCE_CLEAN = "agent_fox.workspace.health.force_clean_workspace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dispatch_manager(
    *,
    force_clean: bool = False,
    full_config: Any = None,
) -> DispatchManager:
    """Build a minimal DispatchManager for prepare_launch tests.

    All external collaborators (circuit, routing, graph, etc.) are mocked
    so that prepare_launch can run to completion after the health-check
    phase under test.
    """
    if full_config is None:
        # Use SimpleNamespace (not MagicMock) so the object is NOT callable.
        # _is_force_clean_enabled checks ``callable(self._full_config_ref)``
        # to decide whether to call it — a MagicMock would always be callable
        # and return a new mock, bypassing the force_clean setting.
        workspace_cfg = types.SimpleNamespace(force_clean=force_clean)
        full_config = types.SimpleNamespace(workspace=workspace_cfg)

    routing = MagicMock()
    routing.assess_node = AsyncMock()
    routing.ladders = {}

    decision = MagicMock()
    decision.allowed = True
    circuit = MagicMock()
    circuit.check_launch = MagicMock(return_value=decision)

    mgr = DispatchManager(
        session_runner_factory=MagicMock(),
        inter_session_delay=0,
        parallel=1,
        graph=None,
        routing=routing,
        circuit=circuit,
        config=MagicMock(max_retries=3, sync_interval=0),
        routing_config=None,
        specs_dir=None,
        full_config=full_config,
        knowledge_db_conn=None,
        sink=None,
        task_callback=None,
        planning_config=None,
    )

    block_fn = MagicMock()
    check_block_budget_fn = MagicMock(return_value=False)
    mgr.set_callbacks(block_fn, check_block_budget_fn)

    node_states: dict[str, str] = {"spec:1": "pending"}
    graph_sync = GraphSync(node_states=node_states, edges={})
    mgr.set_graph_sync(graph_sync)

    return mgr


def _make_state(node_id: str = "spec:1") -> MagicMock:
    state = MagicMock()
    state.node_states = {node_id: "pending"}
    return state


# ---------------------------------------------------------------------------
# _is_known_build_artifact unit tests
# ---------------------------------------------------------------------------


class TestIsKnownBuildArtifact:
    """Unit tests for the _is_known_build_artifact helper."""

    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_property.proptest-regressions",
            "foo.proptest-regressions",
            "src/lib.pyc",
            "module.pyo",
            "__pycache__/mod.cpython-312.pyc",
            "pkg/__pycache__/foo.pyc",
            ".pytest_cache/v/cache/lastfailed",
            "subdir/.pytest_cache/README.md",
            ".mypy_cache/3.12/foo.json",
            ".ruff_cache/0.11/foo",
            ".hypothesis/examples/some_file",
        ],
    )
    def test_known_artifacts_detected(self, path: str) -> None:
        assert _is_known_build_artifact(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "tests/test_core.py",
            "README.md",
            "Cargo.toml",
            "some_unknown_file.rs",
            "leftovers/scratch.txt",
        ],
    )
    def test_non_artifacts_not_matched(self, path: str) -> None:
        assert _is_known_build_artifact(path) is False


# ---------------------------------------------------------------------------
# AC-1: Auto-clean known build artifacts before blocking
# ---------------------------------------------------------------------------


class TestAC1AutoCleanKnownArtifacts:
    """571-AC-1: Auto-remediate when untracked files match known artifact patterns."""

    @pytest.mark.asyncio
    async def test_proptest_regressions_triggers_auto_clean(self) -> None:
        """A .proptest-regressions file triggers auto-remediation, not blocking."""
        dirty_report = HealthReport(
            untracked_files=["tests/test_property.proptest-regressions"],
            dirty_index_files=[],
        )
        clean_report = HealthReport(untracked_files=[], dirty_index_files=[])

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN, new=AsyncMock(return_value=clean_report)
        ) as mock_clean, patch.object(mgr, "_run_preflight", return_value=False):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_awaited_once()
        mgr._block_task_fn.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_pycache_triggers_auto_clean(self) -> None:
        """A __pycache__ artifact triggers auto-remediation."""
        dirty_report = HealthReport(
            untracked_files=["src/__pycache__/foo.cpython-312.pyc"],
            dirty_index_files=[],
        )
        clean_report = HealthReport(untracked_files=[], dirty_index_files=[])

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN, new=AsyncMock(return_value=clean_report)
        ) as mock_clean, patch.object(mgr, "_run_preflight", return_value=False):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_awaited_once()
        mgr._block_task_fn.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_unknown_file_does_not_trigger_auto_clean(self) -> None:
        """An unknown untracked file is NOT auto-remediated; node is blocked."""
        dirty_report = HealthReport(
            untracked_files=["some_unexpected_file.txt"],
            dirty_index_files=[],
        )

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN
        ) as mock_clean:
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_not_called()
        mgr._block_task_fn.assert_called_once()
        assert result is None


# ---------------------------------------------------------------------------
# AC-2: Respect workspace.force_clean config
# ---------------------------------------------------------------------------


class TestAC2ForceCleanConfig:
    """571-AC-2: workspace.force_clean=True triggers cleanup for any untracked file."""

    @pytest.mark.asyncio
    async def test_force_clean_config_triggers_remediation_for_any_file(self) -> None:
        """force_clean=True causes auto-remediation for arbitrary untracked files."""
        dirty_report = HealthReport(
            untracked_files=["some_arbitrary_file.txt"],
            dirty_index_files=[],
        )
        clean_report = HealthReport(untracked_files=[], dirty_index_files=[])

        mgr = _make_dispatch_manager(force_clean=True)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN, new=AsyncMock(return_value=clean_report)
        ) as mock_clean, patch.object(mgr, "_run_preflight", return_value=False):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_awaited_once()
        mgr._block_task_fn.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_force_clean_false_does_not_remediate_unknown_file(self) -> None:
        """force_clean=False does not trigger remediation for unknown files."""
        dirty_report = HealthReport(
            untracked_files=["some_arbitrary_file.txt"],
            dirty_index_files=[],
        )

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN
        ) as mock_clean:
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_not_called()
        mgr._block_task_fn.assert_called_once()
        assert result is None


# ---------------------------------------------------------------------------
# AC-3: Cascade scope — mark_blocked only cascades through dependency edges
# ---------------------------------------------------------------------------


class TestAC3CascadeScope:
    """571-AC-3: mark_blocked() must not cascade to unrelated nodes."""

    def test_cascade_does_not_reach_unrelated_nodes(self) -> None:
        """GraphSync.mark_blocked cascades only along dependency edges.

        Graph: A <- B (same spec, should be cascade-blocked)
               C  (unrelated, must remain pending)
        """
        node_states: dict[str, str] = {
            "spec_a:1": "pending",
            "spec_a:2": "pending",
            "spec_b:1": "pending",
        }
        edges = {
            "spec_a:1": [],
            "spec_a:2": ["spec_a:1"],
            "spec_b:1": [],
        }
        graph_sync = GraphSync(node_states=node_states, edges=edges)

        cascaded = graph_sync.mark_blocked("spec_a:1", reason="workspace-state")

        assert node_states["spec_a:2"] == "blocked"
        assert "spec_a:2" in cascaded
        assert node_states["spec_b:1"] == "pending"
        assert "spec_b:1" not in cascaded

    def test_blocked_node_itself_transitions(self) -> None:
        node_states = {"a:1": "pending", "a:2": "pending"}
        edges = {"a:1": [], "a:2": ["a:1"]}
        graph_sync = GraphSync(node_states=node_states, edges=edges)

        graph_sync.mark_blocked("a:1", reason="test")

        assert node_states["a:1"] == "blocked"


# ---------------------------------------------------------------------------
# Block only when remediation fails
# ---------------------------------------------------------------------------


class TestBlockOnlyWhenRemediationFails:
    """When force_clean returns a non-empty report, the node is still blocked."""

    @pytest.mark.asyncio
    async def test_remediation_failure_blocks_node(self) -> None:
        dirty_report = HealthReport(
            untracked_files=["tests/test_property.proptest-regressions"],
            dirty_index_files=[],
        )
        still_dirty_report = HealthReport(
            untracked_files=["tests/test_property.proptest-regressions"],
            dirty_index_files=[],
        )

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN, new=AsyncMock(return_value=still_dirty_report)
        ):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mgr._block_task_fn.assert_called_once()
        assert result is None


# ---------------------------------------------------------------------------
# AC-5: Fail-open when force_clean_workspace raises
# ---------------------------------------------------------------------------


class TestAC5FailOpenOnException:
    """571-AC-5: If force_clean_workspace() raises, log WARNING and proceed."""

    @pytest.mark.asyncio
    async def test_force_clean_oserror_does_not_block(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """OSError from force_clean_workspace causes fail-open (no blocking)."""
        import logging

        dirty_report = HealthReport(
            untracked_files=["tests/test_property.proptest-regressions"],
            dirty_index_files=[],
        )

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.dispatch"), patch(
            _HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)
        ), patch(_FORCE_CLEAN, side_effect=OSError("permission denied")), patch.object(
            mgr, "_run_preflight", return_value=False
        ):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mgr._block_task_fn.assert_not_called()
        assert result is not None
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("remediation" in m.lower() for m in warning_messages)

    @pytest.mark.asyncio
    async def test_force_clean_runtime_error_does_not_block(self) -> None:
        """RuntimeError from force_clean_workspace also causes fail-open."""
        dirty_report = HealthReport(
            untracked_files=["foo.proptest-regressions"],
            dirty_index_files=[],
        )

        mgr = _make_dispatch_manager(force_clean=True)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=dirty_report)), patch(
            _FORCE_CLEAN, side_effect=RuntimeError("unexpected")
        ), patch.object(mgr, "_run_preflight", return_value=False):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mgr._block_task_fn.assert_not_called()
        assert result is not None


# ---------------------------------------------------------------------------
# Regression: clean workspace still dispatches normally
# ---------------------------------------------------------------------------


class TestCleanWorkspaceUnaffected:
    """Regression: a clean workspace must not trigger any remediation logic."""

    @pytest.mark.asyncio
    async def test_clean_workspace_proceeds_without_remediation(self) -> None:
        clean_report = HealthReport(untracked_files=[], dirty_index_files=[])

        mgr = _make_dispatch_manager(force_clean=False)
        state = _make_state()

        with patch(_HEALTH_CHECK, new=AsyncMock(return_value=clean_report)), patch(
            _FORCE_CLEAN
        ) as mock_clean, patch.object(mgr, "_run_preflight", return_value=False):
            result = await mgr.prepare_launch("spec:1", state, {}, {})

        mock_clean.assert_not_called()
        mgr._block_task_fn.assert_not_called()
        assert result is not None
