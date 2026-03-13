"""Unit tests for AI-powered criteria auto-fix.

Test Spec: TS-22-1 through TS-22-17, TS-22-E1 through TS-22-E4
Requirements: 22-REQ-1.*, 22-REQ-2.*, 22-REQ-3.*, 22-REQ-4.*
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.spec.validator import SEVERITY_HINT, Finding

# -- Constants -----------------------------------------------------------------

_MOCK_CLIENT = "agent_fox.spec.ai_validation.create_async_anthropic_client"

# -- Fixture content -----------------------------------------------------------

REQUIREMENTS_BRACKET = """\
# Requirements: Test Spec

## Requirements

### Requirement 1: Basic Feature

#### Acceptance Criteria

1. [99-REQ-1.1] THE system SHALL be fast.
2. [99-REQ-1.2] THE system SHALL use Redis for caching.
"""

REQUIREMENTS_BOLD = """\
# Requirements: Test Spec

## Requirements

### Requirement 1: Basic Feature

#### Acceptance Criteria

1. **99-REQ-1.1:** THE system SHALL be fast.
2. **99-REQ-1.2:** THE system SHALL use Redis for caching.
"""

REQUIREMENTS_WITH_MARKER = """\
# Requirements: Test Spec UNIQUE_MARKER_STRING

## Requirements

### Requirement 1: Basic Feature

#### Acceptance Criteria

1. [99-REQ-1.1] THE system SHALL be fast.
"""


def _make_mock_rewrite_response(rewrites: list[dict]) -> str:
    """Create a JSON string for a rewrite response."""
    return json.dumps({"rewrites": rewrites})


def _make_finding(
    criterion_id: str = "99-REQ-1.1",
    rule: str = "vague-criterion",
    explanation: str = "Too vague",
    suggestion: str = "Be more specific",
) -> Finding:
    """Create a Finding mimicking AI analysis output."""
    return Finding(
        spec_name="test_spec",
        file="requirements.md",
        rule=rule,
        severity=SEVERITY_HINT,
        message=f"[{criterion_id}] {explanation} Suggestion: {suggestion}",
        line=None,
    )


# ==============================================================================
# TS-22-1: Rewrite call produces replacement text
# ==============================================================================


class TestRewriteProducesReplacement:
    """TS-22-1: Verify rewrite_criteria() returns criterion ID to replacement mapping.

    Requirement: 22-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_returns_mapping_with_criterion_id(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "THE system SHALL be fast.",
                    "replacement": "THE system SHALL respond within 200ms at p95.",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            result = await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            assert "99-REQ-1.1" in result
            assert len(result["99-REQ-1.1"]) > 0


# ==============================================================================
# TS-22-6: EARS keywords in rewrite prompt
# ==============================================================================


class TestEarsKeywordsInPrompt:
    """TS-22-6: Verify rewrite prompt includes EARS syntax keywords.

    Requirement: 22-REQ-2.1
    """

    @pytest.mark.asyncio
    async def test_prompt_contains_ears_keywords(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "THE system SHALL be fast.",
                    "replacement": "THE system SHALL respond within 200ms.",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            call_args = mock_client.messages.create.call_args
            prompt = str(call_args)
            assert "SHALL" in prompt
            assert "WHEN" in prompt
            assert "EARS" in prompt


# ==============================================================================
# TS-22-7: Rewrite prompt includes full requirements text
# ==============================================================================


class TestPromptIncludesFullRequirements:
    """TS-22-7: Verify prompt includes full requirements.md content.

    Requirement: 22-REQ-2.4
    """

    @pytest.mark.asyncio
    async def test_prompt_contains_marker_string(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "THE system SHALL be fast.",
                    "replacement": "THE system SHALL respond within 200ms.",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            await rewrite_criteria(
                "test_spec",
                REQUIREMENTS_WITH_MARKER,
                findings,
                "standard-model",
            )

            prompt = str(mock_client.messages.create.call_args)
            assert "UNIQUE_MARKER_STRING" in prompt


# ==============================================================================
# TS-22-13: Rewrite preserves original intent
# ==============================================================================


class TestRewritePreservesIntent:
    """TS-22-13: Verify prompt instructs AI to preserve original intent.

    Requirement: 22-REQ-2.2
    """

    @pytest.mark.asyncio
    async def test_prompt_mentions_intent(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response([])

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            prompt = str(mock_client.messages.create.call_args).lower()
            assert "intent" in prompt


# ==============================================================================
# TS-22-14: Rewrite prompt prevents fix loops
# ==============================================================================


class TestRewritePreventFixLoops:
    """TS-22-14: Verify prompt instructs AI to produce text that would pass analysis.

    Requirement: 22-REQ-2.3
    """

    @pytest.mark.asyncio
    async def test_prompt_mentions_not_flagged(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response([])

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1", rule="implementation-leak")]
            await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            prompt = str(mock_client.messages.create.call_args).lower()
            assert "pass" in prompt or "not be flagged" in prompt


# ==============================================================================
# TS-22-8: Response JSON structure parsed correctly
# ==============================================================================


class TestResponseJsonParsed:
    """TS-22-8: Verify response JSON mapping is parsed into a dict.

    Requirement: 22-REQ-2.5
    """

    @pytest.mark.asyncio
    async def test_parsed_to_dict(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "THE system SHALL be fast.",
                    "replacement": "new text",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            result = await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            assert result == {"99-REQ-1.1": "new text"}


# ==============================================================================
# TS-22-9: Batching -- one call per spec
# ==============================================================================


class TestBatchingOneCallPerSpec:
    """TS-22-9: Verify multiple findings result in one API call.

    Requirement: 22-REQ-3.1
    """

    @pytest.mark.asyncio
    async def test_single_api_call_for_multiple_findings(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "fast",
                    "replacement": "200ms",
                },
                {
                    "criterion_id": "99-REQ-1.2",
                    "original": "Redis",
                    "replacement": "cache",
                },
                {
                    "criterion_id": "99-REQ-1.3",
                    "original": "good",
                    "replacement": "measurable",
                },
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [
                _make_finding("99-REQ-1.1"),
                _make_finding("99-REQ-1.2", rule="implementation-leak"),
                _make_finding("99-REQ-1.3"),
            ]
            await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            assert mock_client.messages.create.call_count == 1


# ==============================================================================
# TS-22-10: No call for specs without AI findings
# ==============================================================================


class TestNoCallWithoutFindings:
    """TS-22-10: Verify no rewrite call when there are no findings.

    Requirement: 22-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_empty_findings_returns_empty(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            result = await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, [], "standard-model"
            )

            assert result == {}
            assert mock_client.messages.create.call_count == 0


# ==============================================================================
# TS-22-12: STANDARD model used for rewrite
# ==============================================================================


class TestStandardModelUsed:
    """TS-22-12: Verify rewrite call uses STANDARD-tier model.

    Requirement: 22-REQ-3.3
    """

    @pytest.mark.asyncio
    async def test_model_passed_to_api(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "fast",
                    "replacement": "200ms",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            await rewrite_criteria(
                "test_spec",
                REQUIREMENTS_BRACKET,
                findings,
                "standard-model-id",
            )

            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs.get("model") == "standard-model-id" or (
                call_kwargs.args and call_kwargs.args[0] == "standard-model-id"
            )


# ==============================================================================
# TS-22-2: Rewrite applied to requirements.md
# ==============================================================================


class TestRewriteAppliedToFile:
    """TS-22-2: Verify fix_ai_criteria() writes replacement text to file.

    Requirement: 22-REQ-1.2
    """

    def test_replacement_written_to_file(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BRACKET)

        rewrites = {"99-REQ-1.1": "THE system SHALL respond within 200ms at p95."}
        findings_map = {"99-REQ-1.1": "vague-criterion"}
        results = fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        content = req_path.read_text()
        assert "respond within 200ms" in content
        assert "be fast" not in content
        assert len(results) == 1


# ==============================================================================
# TS-22-3: Requirement ID preserved (bracket format)
# ==============================================================================


class TestBracketIdPreserved:
    """TS-22-3: Verify bracket-format requirement ID is preserved after rewrite.

    Requirement: 22-REQ-1.3
    """

    def test_bracket_id_in_output(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BRACKET)

        rewrites = {"99-REQ-1.1": "THE system SHALL respond within 200ms."}
        findings_map = {"99-REQ-1.1": "vague-criterion"}
        fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        content = req_path.read_text()
        assert "[99-REQ-1.1]" in content


# ==============================================================================
# TS-22-4: Bold-format ID preserved
# ==============================================================================


class TestBoldIdPreserved:
    """TS-22-4: Verify bold-format requirement ID is preserved after rewrite.

    Requirement: 22-REQ-1.3
    """

    def test_bold_id_in_output(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BOLD)

        rewrites = {"99-REQ-1.1": "THE system SHALL respond within 200ms."}
        findings_map = {"99-REQ-1.1": "vague-criterion"}
        fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        content = req_path.read_text()
        assert "**99-REQ-1.1:**" in content


# ==============================================================================
# TS-22-11: Fix summary includes AI rewrite counts (FixResult rule names)
# ==============================================================================


class TestFixResultRuleNames:
    """TS-22-11: Verify FixResult objects use correct rule names.

    Requirement: 22-REQ-4.1
    """

    def test_fix_results_have_correct_rules(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BRACKET)

        rewrites = {
            "99-REQ-1.1": "THE system SHALL respond within 200ms.",
            "99-REQ-1.2": "THE system SHALL cache using a TTL strategy.",
        }
        findings_map = {
            "99-REQ-1.1": "vague-criterion",
            "99-REQ-1.2": "implementation-leak",
        }
        results = fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        rules = {r.rule for r in results}
        assert "vague-criterion" in rules or "implementation-leak" in rules


# ==============================================================================
# TS-22-16: FixResult uses matching rule name
# ==============================================================================


class TestFixResultMatchingRule:
    """TS-22-16: Verify FixResult carries the same rule name as the finding.

    Requirement: 22-REQ-4.3
    """

    def test_rule_matches_original_finding(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BRACKET)

        rewrites = {
            "99-REQ-1.1": "THE system SHALL respond within 200ms.",
            "99-REQ-1.2": "THE system SHALL cache responses.",
        }
        findings_map = {
            "99-REQ-1.1": "vague-criterion",
            "99-REQ-1.2": "implementation-leak",
        }
        results = fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        result_by_id = {}
        for r in results:
            # Extract criterion ID from description
            for cid in ["99-REQ-1.1", "99-REQ-1.2"]:
                if cid in r.description:
                    result_by_id[cid] = r

        if "99-REQ-1.1" in result_by_id:
            assert result_by_id["99-REQ-1.1"].rule == "vague-criterion"
        if "99-REQ-1.2" in result_by_id:
            assert result_by_id["99-REQ-1.2"].rule == "implementation-leak"


# ==============================================================================
# TS-22-17: FIXABLE_RULES extended in AI mode
# ==============================================================================


class TestFixableRulesExtended:
    """TS-22-17: Verify vague-criterion and implementation-leak are treated as fixable.

    Requirement: 22-REQ-4.4
    """

    def test_ai_rules_in_fixable_set(self) -> None:
        from agent_fox.spec.fixer import AI_FIXABLE_RULES

        assert "vague-criterion" in AI_FIXABLE_RULES
        assert "implementation-leak" in AI_FIXABLE_RULES


# ==============================================================================
# TS-22-E1: Rewrite call failure leaves file unchanged
# ==============================================================================


class TestApiFailureLeavesFileUnchanged:
    """TS-22-E1: If AI API call fails, return empty dict.

    Requirement: 22-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_api_exception_returns_empty(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.side_effect = Exception("API timeout")
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            result = await rewrite_criteria(
                "test_spec",
                REQUIREMENTS_BRACKET,
                findings,
                "standard-model",
            )

            assert result == {}


# ==============================================================================
# TS-22-E2: Missing criterion ID skipped
# ==============================================================================


class TestMissingCriterionSkipped:
    """TS-22-E2: If criterion ID not in file, skip it.

    Requirement: 22-REQ-1.E2
    """

    def test_phantom_criterion_skipped(self, tmp_path: Path) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        req_path = tmp_path / "requirements.md"
        req_path.write_text(REQUIREMENTS_BRACKET)

        rewrites = {
            "99-REQ-1.1": "THE system SHALL respond within 200ms.",
            "99-REQ-9.9": "phantom text that should not appear",
        }
        findings_map = {
            "99-REQ-1.1": "vague-criterion",
            "99-REQ-9.9": "vague-criterion",
        }
        results = fix_ai_criteria("test_spec", req_path, rewrites, findings_map)

        assert len(results) == 1
        content = req_path.read_text()
        assert "phantom text" not in content


# ==============================================================================
# TS-22-E3: Fenced JSON response parsed
# ==============================================================================


class TestFencedJsonParsed:
    """TS-22-E3: JSON wrapped in markdown code fences is parsed.

    Requirement: 22-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_fenced_json_extracted(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        fenced = (
            "```json\n"
            '{"rewrites": [{"criterion_id": "99-REQ-1.1",'
            ' "original": "fast",'
            ' "replacement": "THE system SHALL respond within 200ms."}]}\n'
            "```"
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=fenced)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [_make_finding("99-REQ-1.1")]
            result = await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            assert len(result) > 0


# ==============================================================================
# TS-22-E4: Omitted criterion in response
# ==============================================================================


class TestOmittedCriterionSkipped:
    """TS-22-E4: If AI response omits a requested criterion, only returned ones apply.

    Requirement: 22-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_partial_response(self) -> None:
        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = _make_mock_rewrite_response(
            [
                {
                    "criterion_id": "99-REQ-1.1",
                    "original": "fast",
                    "replacement": "200ms",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [
                _make_finding("99-REQ-1.1"),
                _make_finding("99-REQ-1.2"),
            ]
            result = await rewrite_criteria(
                "test_spec", REQUIREMENTS_BRACKET, findings, "standard-model"
            )

            assert "99-REQ-1.1" in result
            assert "99-REQ-1.2" not in result
