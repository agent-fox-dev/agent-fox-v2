"""Integration smoke tests for maintainer archetype wiring.

Verifies end-to-end execution paths from design.md:
  Path 1: Nightshift triage → resolve_model_tier("maintainer", mode="hunt") → AI call

Test Spec: TS-100-SMOKE-1
Requirements: 100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2
"""

from __future__ import annotations

# ===========================================================================
# TS-100-SMOKE-1: Nightshift Triage Via Maintainer
# Execution Path 1 from design.md
# Requirements: 100-REQ-5.1, 100-REQ-5.2, 100-REQ-2.2
# ===========================================================================


class TestNightshiftTriageViaMaintainer:
    """TS-100-SMOKE-1: Nightshift triage AI call uses maintainer:hunt resolution.

    Uses real resolve_model_tier and resolve_security_config — these functions
    MUST NOT be mocked per the test spec.
    """

    def test_resolve_model_tier_maintainer_hunt_returns_standard(self) -> None:
        """TS-100-SMOKE-1: Model tier for maintainer:hunt resolves to STANDARD.

        Uses real config and registry — resolve_model_tier is not mocked.
        Requirements: 100-REQ-5.1, 100-REQ-2.2
        """
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        tier = resolve_model_tier(config, "maintainer", mode="hunt")

        assert tier == "STANDARD", (
            f"Nightshift triage must resolve STANDARD tier via maintainer:hunt, got {tier!r} (100-REQ-5.1)"
        )

    def test_resolve_security_config_maintainer_hunt_returns_hunt_allowlist(self) -> None:
        """TS-100-SMOKE-1: Security config for maintainer:hunt has the hunt allowlist.

        Uses real config and registry — resolve_security_config is not mocked.
        Requirements: 100-REQ-5.2, 100-REQ-2.2
        """
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig()
        sec = resolve_security_config(config, "maintainer", mode="hunt")

        assert sec is not None, (
            "resolve_security_config must return a SecurityConfig for maintainer:hunt, not None (100-REQ-5.2)"
        )
        expected_allowlist = {"ls", "cat", "git", "wc", "head", "tail"}
        actual_allowlist = set(sec.bash_allowlist or [])
        assert actual_allowlist == expected_allowlist, (
            f"Hunt mode bash allowlist mismatch.\n"
            f"Expected: {expected_allowlist}\n"
            f"Actual:   {actual_allowlist}\n"
            f"(100-REQ-5.2)"
        )

    def test_triage_tier_propagates_to_ai_call(self) -> None:
        """TS-100-SMOKE-1: Tier resolved from maintainer:hunt is passed to nightshift_ai_call.

        Verifies the full execution path:
        run_batch_triage → _run_ai_triage → resolve_model_tier → nightshift_ai_call(model_tier=...)

        Only the external AI call is mocked (network I/O must not occur in tests).
        Requirements: 100-REQ-5.1, 100-REQ-2.2
        """
        import asyncio
        from unittest.mock import MagicMock, patch

        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.nightshift.dep_graph import DependencyEdge
        from agent_fox.nightshift.triage import run_batch_triage
        from agent_fox.platform.protocol import IssueResult

        config = AgentFoxConfig()
        issues = [
            IssueResult(number=1, title="Issue one", html_url="https://github.com/t/r/issues/1"),
            IssueResult(number=2, title="Issue two", html_url="https://github.com/t/r/issues/2"),
        ]
        edges: list[DependencyEdge] = []

        triage_response = '{"processing_order": [1, 2], "dependencies": [], "supersession": []}'

        captured_tier: list[str] = []

        # Only mock the external AI call to capture the tier that was passed to it.
        # resolve_model_tier and resolve_security_config are NOT mocked.
        async def capturing_ai_call(**kwargs: object) -> tuple:
            captured_tier.append(str(kwargs.get("model_tier", "")))
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=triage_response)]
            return (triage_response, mock_response)

        with patch(
            "agent_fox.nightshift.cost_helpers.nightshift_ai_call",
            side_effect=capturing_ai_call,
        ):
            asyncio.run(run_batch_triage(issues, edges, config))

        assert captured_tier, "nightshift_ai_call must have been called"
        # The tier resolved from maintainer:hunt (STANDARD) must be passed to the AI call
        assert captured_tier[0] == "STANDARD", (
            f"Tier passed to nightshift_ai_call must be STANDARD (from maintainer:hunt), "
            f"got {captured_tier[0]!r} (100-REQ-5.1)"
        )


