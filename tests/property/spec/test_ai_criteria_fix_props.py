"""Property tests for AI-powered criteria auto-fix.

Test Spec: TS-22-P1, TS-22-P2, TS-22-P3
Properties: 1, 2, 5 from design.md
Requirements: 22-REQ-1.2, 22-REQ-1.3, 22-REQ-2.1
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.spec.validator import SEVERITY_HINT, Finding

_MOCK_CLIENT = "agent_fox.spec.ai_validation.create_async_anthropic_client"


# -- Strategies ----------------------------------------------------------------

# Criterion ID: two digits, hyphen, REQ, hyphen, digit(s).digit(s)
criterion_id_strategy = st.from_regex(
    r"[0-9]{2}-REQ-[1-9]\.[1-9]", fullmatch=True
)

# Non-empty replacement text (printable ASCII, no empty)
replacement_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters=" .",
    ),
    min_size=5,
    max_size=100,
).filter(lambda t: t.strip())


def _make_bracket_fixture(criterion_id: str) -> str:
    """Build a minimal requirements.md with a bracket-format criterion."""
    return (
        "# Requirements\n\n"
        "### Requirement 1: Feature\n\n"
        "#### Acceptance Criteria\n\n"
        f"1. [{criterion_id}] THE system SHALL be fast.\n"
    )


def _make_multi_section_fixture(n_reqs: int, criterion_id: str) -> str:
    """Build a requirements.md with n_reqs requirement sections."""
    sections = []
    for i in range(1, n_reqs + 1):
        sections.append(
            f"### Requirement {i}: Feature {i}\n\n"
            f"#### Acceptance Criteria\n\n"
        )
        if i == 1:
            sections.append(f"1. [{criterion_id}] THE system SHALL be fast.\n")
        else:
            cid = criterion_id.replace(".", f".{i}")
            sections.append(
                f"1. [{cid}] THE system SHALL do thing {i}.\n"
            )
    return "# Requirements\n\n" + "\n".join(sections)


def _make_finding(criterion_id: str) -> Finding:
    return Finding(
        spec_name="test_spec",
        file="requirements.md",
        rule="vague-criterion",
        severity=SEVERITY_HINT,
        message=f"[{criterion_id}] Too vague",
        line=None,
    )


# ==============================================================================
# TS-22-P1: Requirement ID round-trip
# ==============================================================================


class TestIdRoundtrip:
    """TS-22-P1: For any criterion ID and replacement text, the fixer preserves the ID.

    Property 1 from design.md.
    Validates: 22-REQ-1.3
    """

    @given(
        criterion_id=criterion_id_strategy,
        replacement=replacement_strategy,
    )
    @settings(max_examples=50)
    def test_id_preserved_after_rewrite(
        self,
        criterion_id: str,
        replacement: str,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        tmp_dir = tmp_path_factory.mktemp("spec")
        req_path = tmp_dir / "requirements.md"
        req_path.write_text(_make_bracket_fixture(criterion_id))

        fix_ai_criteria(
            "spec",
            req_path,
            {criterion_id: replacement},
            {criterion_id: "vague-criterion"},
        )

        content = req_path.read_text()
        assert criterion_id in content


# ==============================================================================
# TS-22-P2: File integrity after rewrite
# ==============================================================================


class TestFileIntegrity:
    """TS-22-P2: Requirement heading count is unchanged after rewrite.

    Property 2 from design.md.
    Validates: 22-REQ-1.2, 22-REQ-1.3
    """

    @given(n_reqs=st.integers(min_value=1, max_value=5))
    @settings(max_examples=20)
    def test_heading_count_preserved(
        self,
        n_reqs: int,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.fixer import fix_ai_criteria

        tmp_dir = tmp_path_factory.mktemp("spec")
        req_path = tmp_dir / "requirements.md"
        content = _make_multi_section_fixture(n_reqs, "99-REQ-1.1")
        req_path.write_text(content)

        fix_ai_criteria(
            "spec",
            req_path,
            {"99-REQ-1.1": "THE system SHALL respond within 200ms."},
            {"99-REQ-1.1": "vague-criterion"},
        )

        result = req_path.read_text()
        assert result.count("### Requirement") == n_reqs


# ==============================================================================
# TS-22-P3: Prompt contains EARS keywords
# ==============================================================================


class TestEarsInPrompt:
    """TS-22-P3: For any set of findings, the prompt always contains EARS keywords.

    Property 5 from design.md.
    Validates: 22-REQ-2.1
    """

    @given(
        n_findings=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_ears_keywords_always_present(
        self,
        n_findings: int,
    ) -> None:
        import json

        from agent_fox.spec.ai_validation import rewrite_criteria

        response_text = json.dumps({"rewrites": []})

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=response_text)]
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = [
                _make_finding(f"99-REQ-1.{i}") for i in range(1, n_findings + 1)
            ]
            req_text = _make_bracket_fixture("99-REQ-1.1")

            await rewrite_criteria("spec", req_text, findings, "model")

            prompt = str(mock_client.messages.create.call_args)
            assert "SHALL" in prompt
            assert "EARS" in prompt
