"""Search tool unit tests.

Test Spec: TS-29-12 (matches), TS-29-13 (context), TS-29-14 (merge),
           TS-29-E10 (missing file), TS-29-E11 (bad regex), TS-29-E12 (no matches)
Requirements: 29-REQ-4.1, 29-REQ-4.2, 29-REQ-4.3,
              29-REQ-4.E1, 29-REQ-4.E2, 29-REQ-4.E3
"""

from __future__ import annotations


class TestSearchReturnsMatches:
    """TS-29-12: fox_search returns matches with line numbers and hashes."""

    def test_returns_matches(self, make_temp_file) -> None:
        from agent_fox.tools.search import fox_search
        from agent_fox.tools.types import SearchResult

        lines = []
        for i in range(1, 21):
            if i in (5, 12):
                lines.append(f"line {i} TODO fix this\n")
            else:
                lines.append(f"line {i} normal\n")
        f = make_temp_file("".join(lines))

        result = fox_search(str(f), "TODO")
        assert isinstance(result, SearchResult)
        assert result.total_matches == 2

        match_lines = []
        for m in result.matches:
            match_lines.extend(m.match_line_numbers)
        assert 5 in match_lines
        assert 12 in match_lines


class TestSearchContextLines:
    """TS-29-13: Context parameter includes surrounding lines."""

    def test_context_lines(self, make_temp_file) -> None:
        from agent_fox.tools.search import fox_search

        lines = []
        for i in range(1, 21):
            if i == 10:
                lines.append(f"line {i} TODO fix this\n")
            else:
                lines.append(f"line {i} normal\n")
        f = make_temp_file("".join(lines))

        result = fox_search(str(f), "TODO", context=2)
        assert len(result.matches) == 1
        numbers = [ln.line_number for ln in result.matches[0].lines]
        assert numbers == [8, 9, 10, 11, 12]


class TestSearchContextMerge:
    """TS-29-14: Overlapping context ranges are merged."""

    def test_context_merge(self, make_temp_file) -> None:
        from agent_fox.tools.search import fox_search

        lines = []
        for i in range(1, 21):
            if i in (10, 12):
                lines.append(f"line {i} TODO fix this\n")
            else:
                lines.append(f"line {i} normal\n")
        f = make_temp_file("".join(lines))

        result = fox_search(str(f), "TODO", context=2)
        # Lines 10 and 12 with context=2: [8-12] and [10-14] => merged [8-14]
        assert len(result.matches) == 1
        numbers = [ln.line_number for ln in result.matches[0].lines]
        assert numbers == list(range(8, 15))
        # No duplicates
        assert len(numbers) == len(set(numbers))


class TestSearchMissingFile:
    """TS-29-E10: Error for missing file."""

    def test_missing_file(self) -> None:
        from agent_fox.tools.search import fox_search

        result = fox_search("/missing.py", "pattern")
        assert isinstance(result, str)


class TestSearchInvalidRegex:
    """TS-29-E11: Error for bad regex pattern."""

    def test_invalid_regex(self, make_temp_file) -> None:
        from agent_fox.tools.search import fox_search

        f = make_temp_file("some content\n")
        result = fox_search(str(f), "[invalid")
        assert isinstance(result, str)
        assert "pattern" in result.lower() or "regex" in result.lower()


class TestSearchNoMatches:
    """TS-29-E12: Empty result (not error) when no lines match."""

    def test_no_matches(self, make_temp_file) -> None:
        from agent_fox.tools.search import fox_search
        from agent_fox.tools.types import SearchResult

        f = make_temp_file("no matching content\nanother line\n")
        result = fox_search(str(f), "ZZZZZ")
        assert isinstance(result, SearchResult)
        assert result.total_matches == 0
        assert result.matches == []
