"""Property tests for hook runner removal and security module relocation.

Test Spec: TS-103-P1, TS-103-P2, TS-103-P3, TS-103-P4
Requirements: 103-REQ-1.1, 103-REQ-1.2, 103-REQ-1.3, 103-REQ-1.6,
              103-REQ-2.1, 103-REQ-2.2, 103-REQ-3.1, 103-REQ-3.2
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, load_config

# ---------------------------------------------------------------------------
# TS-103-P1: Security Module Functional Equivalence
# ---------------------------------------------------------------------------

# Banned symbols that must not appear in any production code file
_BANNED_SYMBOLS = [
    "HookConfig",
    "HookContext",
    "HookResult",
    "HookError",
    "run_pre_session_hooks",
    "run_post_session_hooks",
    "run_sync_barrier_hooks",
    "from agent_fox.hooks.hooks",
]


class TestSecurityModuleFunctionalEquivalence:
    """TS-103-P1: Relocated module produces valid allow/deny decisions."""

    @given(cmd=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
    @settings(max_examples=50)
    def test_check_command_allowed_returns_typed_result(self, cmd: str) -> None:
        """check_command_allowed always returns (bool, str) for any non-whitespace command string."""
        from agent_fox.security.security import (  # noqa: PLC0415
            DEFAULT_ALLOWLIST,
            check_command_allowed,
        )

        result = check_command_allowed(cmd, DEFAULT_ALLOWLIST)
        allowed, msg = result
        assert isinstance(allowed, bool)
        assert isinstance(msg, str)

    @given(cmd=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_build_effective_allowlist_returns_frozenset(self, cmd: str) -> None:
        """build_effective_allowlist always returns a frozenset."""
        from agent_fox.core.config import SecurityConfig  # noqa: PLC0415
        from agent_fox.security.security import (  # noqa: PLC0415
            build_effective_allowlist,
        )

        cfg = SecurityConfig()
        allowlist = build_effective_allowlist(cfg)
        assert isinstance(allowlist, frozenset)


# ---------------------------------------------------------------------------
# TS-103-P2: Hook Runner Absence in Production Code
# ---------------------------------------------------------------------------


class TestHookRunnerAbsentInProductionCode:
    """TS-103-P2: No production module imports or references hook runner symbols."""

    def test_no_banned_symbols_in_production_code(self) -> None:
        """Every .py file in agent_fox/ is free of hook runner symbols."""
        repo_root = Path(__file__).parent.parent.parent.parent
        agent_fox_dir = repo_root / "agent_fox"
        py_files = [
            f
            for f in agent_fox_dir.rglob("*.py")
            if "__pycache__" not in str(f)
        ]

        violations: list[tuple[str, str]] = []
        for py_file in py_files:
            content = py_file.read_text(encoding="utf-8")
            for symbol in _BANNED_SYMBOLS:
                if symbol in content:
                    violations.append(
                        (str(py_file.relative_to(repo_root)), symbol)
                    )

        assert not violations, (
            "Hook runner symbols found in production code:\n"
            + "\n".join(f"  {path}: {sym}" for path, sym in violations)
        )


# ---------------------------------------------------------------------------
# TS-103-P3: ReloadResult Field Access by Name
# ---------------------------------------------------------------------------


class TestReloadResultFieldAccessByName:
    """TS-103-P3: ReloadResult fields accessible by name; dataclass is frozen."""

    def test_reload_result_field_access_by_name(self) -> None:
        """ReloadResult constructed with keyword args and accessed by field name."""
        from agent_fox.core.config import OrchestratorConfig, PlanningConfig  # noqa: PLC0415
        from agent_fox.engine.circuit import CircuitBreaker  # noqa: PLC0415
        from agent_fox.engine.engine import ReloadResult  # noqa: PLC0415

        cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        cb = CircuitBreaker(cfg)
        plan = PlanningConfig()
        arch = None

        result = ReloadResult(config=cfg, circuit=cb, archetypes=arch, planning=plan)
        assert result.config is cfg
        assert result.circuit is cb
        assert result.archetypes is arch
        assert result.planning is plan

    def test_reload_result_is_immutable(self) -> None:
        """ReloadResult (frozen dataclass) raises on mutation attempt."""
        from agent_fox.core.config import OrchestratorConfig, PlanningConfig  # noqa: PLC0415
        from agent_fox.engine.circuit import CircuitBreaker  # noqa: PLC0415
        from agent_fox.engine.engine import ReloadResult  # noqa: PLC0415

        cfg = OrchestratorConfig(parallel=1, inter_session_delay=0)
        cb = CircuitBreaker(cfg)
        plan = PlanningConfig()

        result = ReloadResult(config=cfg, circuit=cb, archetypes=None, planning=plan)
        with pytest.raises((AttributeError, TypeError)):
            result.config = cfg  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-103-P4: TOML Backward Compatibility
# ---------------------------------------------------------------------------

_HOOKS_TOML_VARIANTS = [
    "[hooks]\n",
    "[hooks]\npre_code = []\n",
    '[hooks]\npre_code = ["echo hello"]\ntimeout = 60\n',
    '[hooks]\npre_code = ["echo hi"]\npost_code = ["echo bye"]\nsync_barrier = []\ntimeout = 120\n',
    "[hooks]\nsome_unknown_key = 42\n",
]


class TestTomlBackwardCompatibility:
    """TS-103-P4: Any TOML with [hooks] section parses without error."""

    @pytest.mark.parametrize("hooks_content", _HOOKS_TOML_VARIANTS)
    def test_toml_with_hooks_parses_successfully(
        self, hooks_content: str, tmp_path: Path
    ) -> None:
        """load_config() returns AgentFoxConfig for any [hooks] TOML variant."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(hooks_content, encoding="utf-8")
        config = load_config(config_file)
        assert isinstance(config, AgentFoxConfig)
