"""Tests for extraction prompt enrichment and causal link parsing.

Test Spec: TS-13-14, TS-13-15, TS-13-16, TS-13-E2, TS-13-E3
Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-2.E1
"""

from __future__ import annotations

from agent_fox.knowledge.extraction import (
    enrich_extraction_with_causal,
    parse_causal_links,
)

# Valid UUIDs for use in tests
_UUID_A = "11111111-1111-1111-1111-111111111111"
_UUID_B = "22222222-2222-2222-2222-222222222222"
_UUID_C = "33333333-3333-3333-3333-333333333333"
_UUID_D = "44444444-4444-4444-4444-444444444444"
_UUID_E = "55555555-5555-5555-5555-555555555555"
_UUID_X1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_UUID_X2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class TestEnrichExtractionPrompt:
    """TS-13-14: Enrich extraction prompt includes prior facts.

    Requirement: 13-REQ-2.1
    """

    def test_enriched_prompt_contains_base(self) -> None:
        """The enriched prompt includes the original base prompt."""
        prior = [{"id": _UUID_A, "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "Extract facts:" in result

    def test_enriched_prompt_contains_causal_section(self) -> None:
        """The enriched prompt includes the Causal Relationships section."""
        prior = [{"id": _UUID_A, "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "Causal Relationships" in result

    def test_enriched_prompt_contains_prior_fact_content(self) -> None:
        """The enriched prompt includes prior fact content."""
        prior = [{"id": _UUID_A, "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "User.email nullable" in result

    def test_enriched_prompt_with_multiple_prior_facts(self) -> None:
        """Multiple prior facts are all included in the enriched prompt."""
        prior = [
            {"id": _UUID_A, "content": "First fact"},
            {"id": _UUID_B, "content": "Second fact"},
        ]
        result = enrich_extraction_with_causal("Base:", prior)
        assert "First fact" in result
        assert "Second fact" in result

    def test_enriched_prompt_with_empty_prior_facts(self) -> None:
        """An empty prior facts list produces a valid enriched prompt."""
        result = enrich_extraction_with_causal("Base:", [])
        assert "Base:" in result
        assert "Causal Relationships" in result


class TestParseCausalLinks:
    """TS-13-15: Parse causal links from extraction response.

    Requirement: 13-REQ-2.2
    """

    def test_parses_valid_links(self) -> None:
        """Valid JSON causal links with proper UUIDs are parsed correctly."""
        response = (
            f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}, '
            f'{{"cause_id": "{_UUID_C}", "effect_id": "{_UUID_D}"}}]'
        )
        links = parse_causal_links(response)
        assert len(links) == 2
        assert links[0] == (_UUID_A, _UUID_B)
        assert links[1] == (_UUID_C, _UUID_D)


class TestParseCausalLinksMalformed:
    """TS-13-16: Parse causal links handles malformed input.

    Requirement: 13-REQ-2.E1
    """

    def test_skips_malformed_entries(self) -> None:
        """Malformed entries are silently skipped, valid ones returned."""
        response = (
            f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}, '
            '{"bad": "entry"}, "not json"]'
        )
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_A, _UUID_B)


class TestParseCausalLinksEmpty:
    """TS-13-E2: Extraction returns no causal links.

    Requirement: 13-REQ-2.E1
    """

    def test_empty_array_returns_empty_list(self) -> None:
        """An empty JSON array returns an empty list."""
        links = parse_causal_links("[]")
        assert len(links) == 0


class TestParseCausalLinksMarkdownFences:
    """parse_causal_links strips markdown fences before parsing."""

    def test_parses_json_inside_code_fence(self) -> None:
        """JSON wrapped in ```json fences is parsed correctly."""
        response = f'```json\n[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}]\n```'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_A, _UUID_B)

    def test_parses_json_inside_plain_fence(self) -> None:
        """JSON wrapped in ``` fences (no language tag) is parsed correctly."""
        response = f'```\n[{{"cause_id": "{_UUID_X1}", "effect_id": "{_UUID_X2}"}}]\n```'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_X1, _UUID_X2)


class TestParseCausalLinksWithEchoedRefs:
    """parse_causal_links handles LLM responses that echo [uuid] refs in prose."""

    def test_parses_links_after_echoed_uuid_references(self) -> None:
        """JSON causal links are parsed when LLM echoes [uuid] refs in prose."""
        response = (
            f"Looking at [{_UUID_A}] and [{_UUID_B}], I see a causal chain:\n\n"
            f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}]'
        )
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_A, _UUID_B)

    def test_parses_empty_array_after_echoed_refs(self) -> None:
        """Empty JSON array is parsed when LLM echoes [uuid] refs in prose."""
        response = f"Reviewing [{_UUID_A}] and [{_UUID_B}], no causal relationship found.\n\n[]"
        links = parse_causal_links(response)
        assert len(links) == 0


class TestParseCausalLinksInvalidJSON:
    """TS-13-E3: Extraction returns completely invalid JSON.

    Requirement: 13-REQ-2.E1
    """

    def test_invalid_json_returns_empty_list(self) -> None:
        """Unparseable content returns an empty list without raising."""
        links = parse_causal_links("This is not JSON at all")
        assert len(links) == 0

    def test_partial_json_no_complete_entries_returns_empty(self) -> None:
        """Truncated JSON with no complete entries returns an empty list."""
        links = parse_causal_links(f'[{{"cause_id": "{_UUID_A}", "effect_id":')
        assert len(links) == 0


class TestParseCausalLinksTruncatedRecovery:
    """parse_causal_links recovers valid entries from truncated JSON."""

    def test_recovers_complete_entries_from_truncated_array(self) -> None:
        """Complete entries before the truncation point are recovered."""
        response = (
            f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}, '
            f'{{"cause_id": "{_UUID_C}", "effect_id": "{_UUID_D}"}}, '
            f'{{"cause_id": "{_UUID_E}", "effect_'
        )
        links = parse_causal_links(response)
        assert len(links) == 2
        assert links[0] == (_UUID_A, _UUID_B)
        assert links[1] == (_UUID_C, _UUID_D)

    def test_recovers_from_truncated_fenced_response(self) -> None:
        """Truncated ```json fenced response recovers valid entries."""
        response = (
            f'```json\n[{{"cause_id": "{_UUID_X1}", "effect_id": "{_UUID_X2}"}}, '
            f'{{"cause_id": "{_UUID_A}"'
        )
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_X1, _UUID_X2)

    def test_single_complete_entry_before_truncation(self) -> None:
        """A single complete entry followed by truncation is recovered."""
        response = f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}, {{"cause_id":'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_A, _UUID_B)


# ---------------------------------------------------------------------------
# Regression: malformed UUID filtering (fixes #474)
# ---------------------------------------------------------------------------


class TestParseCausalLinksUUIDValidation:
    """Verify parse_causal_links filters out malformed UUIDs from LLM output."""

    def test_truncated_uuid_filtered(self) -> None:
        """Truncated UUID (missing a segment) is filtered out."""
        truncated = "bcdd143f-4363-a85f-77b6748add6c"
        response = f'[{{"cause_id": "{_UUID_A}", "effect_id": "{truncated}"}}]'
        links = parse_causal_links(response)
        assert len(links) == 0

    def test_git_sha_filtered(self) -> None:
        """40-char git SHA (not a UUID) is filtered out."""
        git_sha = "b7f2ab9cf46b4552d505a3fac075a1935a653b22"
        response = f'[{{"cause_id": "{git_sha}", "effect_id": "{_UUID_A}"}}]'
        links = parse_causal_links(response)
        assert len(links) == 0

    def test_valid_uuid_passes(self) -> None:
        """Valid UUID v4 strings pass validation."""
        response = f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}]'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == (_UUID_A, _UUID_B)

    def test_mixed_valid_and_invalid_keeps_only_valid(self) -> None:
        """Only links with both IDs as valid UUIDs are kept."""
        git_sha = "b7f2ab9cf46b4552d505a3fac075a1935a653b22"
        response = (
            f'[{{"cause_id": "{_UUID_A}", "effect_id": "{_UUID_B}"}}, '
            f'{{"cause_id": "{git_sha}", "effect_id": "{_UUID_C}"}}, '
            f'{{"cause_id": "{_UUID_C}", "effect_id": "{_UUID_D}"}}]'
        )
        links = parse_causal_links(response)
        assert len(links) == 2
        assert links[0] == (_UUID_A, _UUID_B)
        assert links[1] == (_UUID_C, _UUID_D)

    def test_plain_string_filtered(self) -> None:
        """Plain non-hex strings are filtered out."""
        response = f'[{{"cause_id": "not-a-uuid", "effect_id": "{_UUID_A}"}}]'
        links = parse_causal_links(response)
        assert len(links) == 0

    def test_empty_string_filtered(self) -> None:
        """Empty string IDs are filtered out."""
        response = f'[{{"cause_id": "", "effect_id": "{_UUID_A}"}}]'
        links = parse_causal_links(response)
        assert len(links) == 0
