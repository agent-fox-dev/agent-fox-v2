"""Tests for extraction prompt enrichment and causal link parsing.

Test Spec: TS-13-14, TS-13-15, TS-13-16, TS-13-E2, TS-13-E3
Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-2.E1
"""

from __future__ import annotations

from agent_fox.knowledge.extraction import (
    enrich_extraction_with_causal,
    parse_causal_links,
)


class TestEnrichExtractionPrompt:
    """TS-13-14: Enrich extraction prompt includes prior facts.

    Requirement: 13-REQ-2.1
    """

    def test_enriched_prompt_contains_base(self) -> None:
        """The enriched prompt includes the original base prompt."""
        prior = [{"id": "aaa", "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "Extract facts:" in result

    def test_enriched_prompt_contains_causal_section(self) -> None:
        """The enriched prompt includes the Causal Relationships section."""
        prior = [{"id": "aaa", "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "Causal Relationships" in result

    def test_enriched_prompt_contains_prior_fact_content(self) -> None:
        """The enriched prompt includes prior fact content."""
        prior = [{"id": "aaa", "content": "User.email nullable"}]
        result = enrich_extraction_with_causal("Extract facts:", prior)
        assert "User.email nullable" in result

    def test_enriched_prompt_with_multiple_prior_facts(self) -> None:
        """Multiple prior facts are all included in the enriched prompt."""
        prior = [
            {"id": "aaa", "content": "First fact"},
            {"id": "bbb", "content": "Second fact"},
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
        """Valid JSON causal links are parsed correctly."""
        response = (
            '[{"cause_id": "aaa", "effect_id": "bbb"}, '
            '{"cause_id": "ccc", "effect_id": "ddd"}]'
        )
        links = parse_causal_links(response)
        assert len(links) == 2
        assert links[0] == ("aaa", "bbb")
        assert links[1] == ("ccc", "ddd")


class TestParseCausalLinksMalformed:
    """TS-13-16: Parse causal links handles malformed input.

    Requirement: 13-REQ-2.E1
    """

    def test_skips_malformed_entries(self) -> None:
        """Malformed entries are silently skipped, valid ones returned."""
        response = (
            '[{"cause_id": "aaa", "effect_id": "bbb"}, {"bad": "entry"}, "not json"]'
        )
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("aaa", "bbb")


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
        response = '```json\n[{"cause_id": "aaa", "effect_id": "bbb"}]\n```'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("aaa", "bbb")

    def test_parses_json_inside_plain_fence(self) -> None:
        """JSON wrapped in ``` fences (no language tag) is parsed correctly."""
        response = '```\n[{"cause_id": "x1", "effect_id": "x2"}]\n```'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("x1", "x2")


class TestParseCausalLinksWithEchoedRefs:
    """parse_causal_links handles LLM responses that echo [uuid] refs in prose."""

    def test_parses_links_after_echoed_uuid_references(self) -> None:
        """JSON causal links are parsed when LLM echoes [uuid] refs in prose."""
        response = (
            "Looking at [aaa-111] and [bbb-222], I see a causal chain:\n\n"
            '[{"cause_id": "aaa-111", "effect_id": "bbb-222"}]'
        )
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("aaa-111", "bbb-222")

    def test_parses_empty_array_after_echoed_refs(self) -> None:
        """Empty JSON array is parsed when LLM echoes [uuid] refs in prose."""
        response = (
            "Reviewing [fact-1] and [fact-2], no causal relationship found.\n\n[]"
        )
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
        links = parse_causal_links('[{"cause_id": "aaa", "effect_id":')
        assert len(links) == 0


class TestParseCausalLinksTruncatedRecovery:
    """parse_causal_links recovers valid entries from truncated JSON."""

    def test_recovers_complete_entries_from_truncated_array(self) -> None:
        """Complete entries before the truncation point are recovered."""
        response = (
            '[{"cause_id": "aaa", "effect_id": "bbb"}, '
            '{"cause_id": "ccc", "effect_id": "ddd"}, '
            '{"cause_id": "eee", "effect_'
        )
        links = parse_causal_links(response)
        assert len(links) == 2
        assert links[0] == ("aaa", "bbb")
        assert links[1] == ("ccc", "ddd")

    def test_recovers_from_truncated_fenced_response(self) -> None:
        """Truncated ```json fenced response recovers valid entries."""
        response = '```json\n[{"cause_id": "x1", "effect_id": "x2"}, {"cause_id": "y1"'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("x1", "x2")

    def test_single_complete_entry_before_truncation(self) -> None:
        """A single complete entry followed by truncation is recovered."""
        response = '[{"cause_id": "a", "effect_id": "b"}, {"cause_id":'
        links = parse_causal_links(response)
        assert len(links) == 1
        assert links[0] == ("a", "b")
