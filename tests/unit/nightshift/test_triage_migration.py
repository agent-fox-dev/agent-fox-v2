"""Unit tests for nightshift triage migration to maintainer:hunt archetype.

Verifies that run_batch_triage uses maintainer:hunt for model tier and
security config resolution, and handles legacy config keys correctly.

Test Spec: TS-100-6, TS-100-11, TS-100-E2
Requirements: 100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2, 100-REQ-2.E1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_fox.nightshift.dep_graph import DependencyEdge
from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int = 1) -> IssueResult:
    return IssueResult(
        number=number,
        title=f"Fix issue #{number}",
        html_url=f"https://github.com/test/repo/issues/{number}",
    )


# ===========================================================================
# TS-100-6: Triage Uses Maintainer Hunt
# Requirements: 100-REQ-2.2, 100-REQ-5.3
# ===========================================================================


class TestTriageUsesMaintainerHunt:
    """Verify run_batch_triage resolves model tier from maintainer:hunt."""

    @pytest.mark.asyncio
    async def test_resolve_model_tier_called_with_maintainer_hunt(self) -> None:
        """TS-100-6: run_batch_triage must call resolve_model_tier('maintainer', mode='hunt')."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.triage import run_batch_triage

        config = AgentFoxConfig()
        issues = [_make_issue(1), _make_issue(2)]
        edges: list[DependencyEdge] = []

        # Mock AI call to avoid network I/O
        triage_response = '{"processing_order": [1, 2], "dependencies": [], "supersession": []}'

        with (
            patch("agent_fox.nightshift.triage.resolve_model_tier") as mock_tier,
            patch("agent_fox.nightshift.cost_helpers.nightshift_ai_call") as mock_ai,
        ):
            mock_tier.return_value = "STANDARD"
            mock_ai.return_value = (triage_response, MagicMock())

            await run_batch_triage(issues, edges, config)

        # Verify resolve_model_tier was called with maintainer:hunt
        assert mock_tier.called, "run_batch_triage must call resolve_model_tier (100-REQ-5.1)"
        call_args = mock_tier.call_args
        assert call_args is not None
        # First positional arg after config should be "maintainer"
        pos_args = call_args.args
        kwargs = call_args.kwargs
        archetype_arg = pos_args[1] if len(pos_args) > 1 else kwargs.get("archetype")
        mode_kwarg = kwargs.get("mode")
        assert archetype_arg == "maintainer", (
            f"resolve_model_tier should be called with archetype='maintainer', got {archetype_arg!r} (100-REQ-2.2)"
        )
        assert mode_kwarg == "hunt", (
            f"resolve_model_tier should be called with mode='hunt', got {mode_kwarg!r} (100-REQ-2.2)"
        )

    @pytest.mark.asyncio
    async def test_resolve_security_config_called_with_maintainer_hunt(self) -> None:
        """TS-100-6: run_batch_triage must call resolve_security_config('maintainer', mode='hunt').

        Requirement: 100-REQ-5.2
        """
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.triage import run_batch_triage

        config = AgentFoxConfig()
        issues = [_make_issue(1)]
        edges: list[DependencyEdge] = []

        triage_response = '{"processing_order": [1], "dependencies": [], "supersession": []}'

        with (
            patch("agent_fox.nightshift.triage.resolve_security_config") as mock_sec,
            patch("agent_fox.nightshift.triage.resolve_model_tier", return_value="STANDARD"),
            patch("agent_fox.nightshift.cost_helpers.nightshift_ai_call") as mock_ai,
        ):
            mock_sec.return_value = MagicMock()
            mock_ai.return_value = (triage_response, MagicMock())

            await run_batch_triage(issues, edges, config)

        assert mock_sec.called, "run_batch_triage must call resolve_security_config (100-REQ-5.2)"
        call_args = mock_sec.call_args
        assert call_args is not None
        pos_args = call_args.args
        kwargs = call_args.kwargs
        archetype_arg = pos_args[1] if len(pos_args) > 1 else kwargs.get("archetype")
        mode_kwarg = kwargs.get("mode")
        assert archetype_arg == "maintainer", (
            f"resolve_security_config should be called with archetype='maintainer', got {archetype_arg!r} (100-REQ-5.2)"
        )
        assert mode_kwarg == "hunt", (
            f"resolve_security_config should be called with mode='hunt', got {mode_kwarg!r} (100-REQ-5.2)"
        )


# ===========================================================================
# TS-100-11: Nightshift Model Tier Resolution
# Requirements: 100-REQ-5.1, 100-REQ-5.2
# ===========================================================================


class TestNightshiftModelTierResolution:
    """Verify nightshift resolves STANDARD tier for maintainer:hunt."""

    def test_resolve_model_tier_returns_standard(self) -> None:
        """TS-100-11: resolve_model_tier(config, 'maintainer', mode='hunt') returns 'STANDARD'."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        tier = resolve_model_tier(config, "maintainer", mode="hunt")
        assert tier == "STANDARD", f"Expected STANDARD tier for maintainer:hunt, got {tier!r} (100-REQ-5.1)"

    def test_resolve_security_config_returns_hunt_allowlist(self) -> None:
        """TS-100-11: resolve_security_config for maintainer:hunt returns hunt allowlist."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig()
        sec = resolve_security_config(config, "maintainer", mode="hunt")
        assert sec is not None, "resolve_security_config should return SecurityConfig for maintainer:hunt (100-REQ-5.2)"
        expected_allowlist = {"ls", "cat", "git", "wc", "head", "tail"}
        actual_allowlist = set(sec.bash_allowlist)
        assert actual_allowlist == expected_allowlist, (
            f"Hunt mode allowlist mismatch: expected {expected_allowlist}, got {actual_allowlist} (100-REQ-5.2)"
        )

    def test_resolve_model_tier_extraction_returns_standard(self) -> None:
        """TS-100-11: resolve_model_tier for maintainer:extraction also returns STANDARD."""
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        tier = resolve_model_tier(config, "maintainer", mode="extraction")
        assert tier == "STANDARD", f"Expected STANDARD tier for maintainer:extraction, got {tier!r}"


# ===========================================================================
# TS-100-E2: Old Triage Config Key
# Requirement: 100-REQ-2.E1
# ===========================================================================


class TestOldTriageConfigKey:
    """Verify config with archetypes.triage key is handled gracefully."""

    def test_config_with_triage_key_does_not_raise(self) -> None:
        """TS-100-E2: Parsing config with archetypes.triage key must not fail.

        Requirement: 100-REQ-2.E1 (log deprecation warning, but not fail)
        """
        import tomllib

        from agent_fox.core.config import AgentFoxConfig

        # Try to parse a config dict that includes a 'triage' key under archetypes.
        # Per 100-REQ-2.E1, this should NOT raise — it should log a deprecation warning.
        toml_content = b"""
[archetypes]
triage = true
"""
        raw = tomllib.loads(toml_content.decode())
        # Config parsing must not raise
        config = AgentFoxConfig.model_validate(raw)
        assert config is not None, (
            "AgentFoxConfig.model_validate should succeed when archetypes.triage is present (100-REQ-2.E1)"
        )
