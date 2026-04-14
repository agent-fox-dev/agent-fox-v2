"""Integration smoke tests for maintainer archetype wiring.

Verifies end-to-end execution paths from design.md:
  Path 1: Nightshift triage → resolve_model_tier("maintainer", mode="hunt") → AI call
  Path 2: extract_knowledge(input) → ExtractionResult (stub)

Test Spec: TS-100-SMOKE-1, TS-100-SMOKE-2
Requirements: 100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2, 100-REQ-4.3, 100-REQ-4.E1
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
        actual_allowlist = set(sec.bash_allowlist)
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
        from agent_fox.platform.github import IssueResult

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


# ===========================================================================
# TS-100-SMOKE-2: Extraction Stub End-to-End
# Execution Path 2 from design.md
# Requirements: 100-REQ-4.3, 100-REQ-4.E1
# ===========================================================================


class TestExtractionStubEndToEnd:
    """TS-100-SMOKE-2: Extraction stub is callable and returns a valid result.

    Uses the real extract_knowledge function — it MUST NOT be mocked.
    """

    def test_extract_knowledge_returns_not_implemented(self) -> None:
        """TS-100-SMOKE-2: extract_knowledge returns ExtractionResult with status='not_implemented'.

        Requirements: 100-REQ-4.3, 100-REQ-4.E1
        """
        from agent_fox.nightshift.extraction import ExtractionInput, ExtractionResult, extract_knowledge

        extraction_input = ExtractionInput(
            session_id="test-session-001",
            transcript="session content goes here",
            spec_name="100_maintainer_archetype",
            archetype="coder",
        )

        result = extract_knowledge(extraction_input)

        assert isinstance(result, ExtractionResult), (
            "extract_knowledge must return an ExtractionResult instance (100-REQ-4.3)"
        )
        assert result.status == "not_implemented", (
            f"Stub must return status='not_implemented', got {result.status!r} (100-REQ-4.3)"
        )
        assert result.facts == [], f"Stub must return empty facts list, got {result.facts!r} (100-REQ-4.3)"
        assert result.session_id == "test-session-001", (
            f"ExtractionResult must propagate session_id from input, got {result.session_id!r}"
        )

    def test_extract_knowledge_never_raises(self) -> None:
        """TS-100-SMOKE-2: extract_knowledge never raises even with edge-case inputs.

        Requirement: 100-REQ-4.E1
        """
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        edge_cases = [
            ExtractionInput(session_id="", transcript="", spec_name="", archetype=""),
            ExtractionInput(
                session_id="x" * 10000,
                transcript="y" * 50000,
                spec_name="spec",
                archetype="coder",
                mode="fix",
            ),
            ExtractionInput(
                session_id="s1",
                transcript="unicode: 你好 🔥",
                spec_name="spec",
                archetype="reviewer",
                mode=None,
            ),
        ]

        for extraction_input in edge_cases:
            try:
                result = extract_knowledge(extraction_input)
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(
                    f"extract_knowledge raised {type(exc).__name__} with input "
                    f"session_id={extraction_input.session_id!r}: {exc}\n"
                    "The stub must NEVER raise (100-REQ-4.E1)"
                ) from exc

            assert result.status == "not_implemented", (
                f"Stub must always return status='not_implemented', got {result.status!r}"
            )

    def test_extract_knowledge_propagates_session_id(self) -> None:
        """TS-100-SMOKE-2: ExtractionResult.session_id is propagated from input.

        Requirement: 100-REQ-4.3
        """
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        for session_id in ["abc-123", "", "session/with/slashes", "unicode-🎯"]:
            extraction_input = ExtractionInput(
                session_id=session_id,
                transcript="any content",
                spec_name="spec",
                archetype="coder",
            )
            result = extract_knowledge(extraction_input)
            assert result.session_id == session_id, (
                f"session_id not propagated correctly: expected {session_id!r}, got {result.session_id!r}"
            )
