"""Unit tests for AI-powered semantic analysis.

Test Spec: TS-09-E3
Requirements: 09-REQ-8.1, 09-REQ-8.2, 09-REQ-8.3, 09-REQ-8.E1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.spec.ai_validation import (
    analyze_acceptance_criteria,
    run_ai_validation,
)
from agent_fox.spec.discovery import SpecInfo

# -- Fixtures ------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "specs"
_MOCK_AI_CALL = "agent_fox.spec.ai_validation.ai_call"


def _make_spec_info(
    name: str = "test_spec",
    prefix: int = 1,
    path: Path | None = None,
) -> SpecInfo:
    """Create a SpecInfo for testing."""
    return SpecInfo(
        name=name,
        prefix=prefix,
        path=path or FIXTURES_DIR / "complete_spec",
        has_tasks=True,
        has_prd=True,
    )


def _make_ai_response(issues: list[dict[str, str]]) -> str:
    """Create a JSON string representing an AI analysis response."""
    return json.dumps({"issues": issues})


# -- TS-09-E3: AI unavailable graceful fallback --------------------------------


class TestAIUnavailableGracefulFallback:
    """TS-09-E3: AI unavailable graceful fallback.

    Requirements: 09-REQ-8.E1
    Verify AI validation is skipped gracefully when the model is unavailable.
    """

    @pytest.mark.asyncio
    async def test_auth_error_returns_empty(self) -> None:
        """Authentication error returns empty findings list."""
        specs = [_make_spec_info()]
        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.side_effect = Exception("Authentication failed")

            findings = await run_ai_validation(specs, "STANDARD")

            assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_auth_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Authentication error produces a log warning."""
        specs = [_make_spec_info()]
        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.side_effect = Exception("Authentication failed")

            with caplog.at_level(logging.WARNING):
                await run_ai_validation(specs, "STANDARD")

            assert any(
                "warning" in record.levelname.lower() or record.levelno == logging.WARNING for record in caplog.records
            )


# -- AI findings severity and rule tests ---------------------------------------


class TestAIFindingsSeverityAndRule:
    """Verify AI findings have correct severity and rule names.

    Requirements: 09-REQ-8.2, 09-REQ-8.3
    """

    @pytest.mark.asyncio
    async def test_vague_criterion_finding_is_hint(self) -> None:
        """AI finding for vague criterion has severity 'hint'."""
        response_text = _make_ai_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "issue_type": "vague",
                    "explanation": "Too vague",
                    "suggestion": "Be more specific",
                }
            ]
        )

        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = (response_text, MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert len(findings) >= 1
            assert findings[0].severity == "hint"

    @pytest.mark.asyncio
    async def test_vague_criterion_rule_name(self) -> None:
        """AI finding for vague criterion has rule 'vague-criterion'."""
        response_text = _make_ai_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "issue_type": "vague",
                    "explanation": "Too vague",
                    "suggestion": "Be more specific",
                }
            ]
        )

        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = (response_text, MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert findings[0].rule == "vague-criterion"

    @pytest.mark.asyncio
    async def test_implementation_leak_rule_name(self) -> None:
        """AI finding for implementation leak has rule 'implementation-leak'."""
        response_text = _make_ai_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "issue_type": "implementation-leak",
                    "explanation": "Describes how, not what",
                    "suggestion": "Focus on behavior",
                }
            ]
        )

        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = (response_text, MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert len(findings) >= 1
            assert findings[0].rule == "implementation-leak"


# -- AI prompt construction tests ----------------------------------------------


class TestAIPromptConstruction:
    """Verify prompt includes acceptance criteria text.

    Requirements: 09-REQ-8.1
    """

    @pytest.mark.asyncio
    async def test_prompt_includes_criteria_text(self) -> None:
        """AI prompt contains acceptance criteria from requirements.md."""
        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = ('{"issues": []}', MagicMock())

            await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            # Verify the API was called
            assert mock_ai.called
            # Check that the prompt includes criteria text from the fixture
            call_args = mock_ai.call_args
            # The prompt should contain acceptance criteria text
            prompt_text = str(call_args)
            assert "99-REQ-1.1" in prompt_text or "SHALL" in prompt_text


# -- AI response parsing tests ------------------------------------------------


class TestAIResponseParsing:
    """Verify response parsing handles valid and malformed responses.

    Requirements: 09-REQ-8.2, 09-REQ-8.3
    """

    @pytest.mark.asyncio
    async def test_empty_issues_returns_empty(self) -> None:
        """Empty issues list in response produces no findings."""
        response_text = '{"issues": []}'

        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = (response_text, MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self) -> None:
        """Malformed JSON response produces no findings (graceful handling)."""
        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = ("not valid json", MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_fenced_json_response_parsed(self) -> None:
        """JSON wrapped in markdown code fences is parsed correctly."""
        fenced = (
            "```json\n"
            '{"issues": [{"criterion_id": "99-REQ-1.1",'
            ' "issue_type": "vague",'
            ' "explanation": "Too vague",'
            ' "suggestion": "Be specific"}]}\n'
            "```"
        )

        with patch(_MOCK_AI_CALL, new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = (fenced, MagicMock())

            findings = await analyze_acceptance_criteria(
                "test_spec",
                FIXTURES_DIR / "complete_spec",
                "STANDARD",
            )

            assert len(findings) == 1
            assert findings[0].rule == "vague-criterion"
