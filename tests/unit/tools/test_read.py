"""Read tool unit tests.

Test Spec: TS-29-5 (ranges), TS-29-6 (multiple ranges), TS-29-7 (hash correctness),
           TS-29-E4 (missing file), TS-29-E5 (beyond EOF), TS-29-E6 (invalid range)
Requirements: 29-REQ-2.1, 29-REQ-2.2, 29-REQ-2.3,
              29-REQ-2.E1, 29-REQ-2.E2, 29-REQ-2.E3
"""

from __future__ import annotations


class TestReadReturnsHashedLines:
    """TS-29-5: fox_read returns HashedLine objects for requested ranges."""

    def test_returns_hashed_lines(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import ReadResult

        f = make_temp_file_with_lines(20)
        result = fox_read(str(f), [(5, 10)])
        assert isinstance(result, ReadResult)
        assert len(result.lines) == 6
        assert result.lines[0].line_number == 5
        assert "line 5" in result.lines[0].content
        assert len(result.lines[0].hash) == 16


class TestReadMultipleRanges:
    """TS-29-6: Multiple disjoint ranges returned in ascending order."""

    def test_multiple_ranges_ordered(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.read import fox_read

        f = make_temp_file_with_lines(20)
        # Pass ranges out of order
        result = fox_read(str(f), [(15, 17), (3, 5)])
        assert len(result.lines) == 6
        numbers = [ln.line_number for ln in result.lines]
        assert numbers == [3, 4, 5, 15, 16, 17]


class TestReadHashCorrectness:
    """TS-29-7: Content hashes match independently computed xxh3_64."""

    def test_xxh3_hashes(self, make_temp_file) -> None:
        from agent_fox.tools.hashing import hash_line
        from agent_fox.tools.read import fox_read

        content = "hello world\n"
        f = make_temp_file(content, "hash_test.txt")
        result = fox_read(str(f), [(1, 1)])

        expected_hash = hash_line(content.encode())
        assert result.lines[0].hash == expected_hash


class TestReadMissingFile:
    """TS-29-E4: Error for missing file."""

    def test_missing_file(self) -> None:
        from agent_fox.tools.read import fox_read

        result = fox_read("/missing.py", [(1, 5)])
        assert isinstance(result, str)


class TestReadBeyondEOF:
    """TS-29-E5: Truncation warning when range exceeds file."""

    def test_range_beyond_eof(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.read import fox_read

        f = make_temp_file_with_lines(10)
        result = fox_read(str(f), [(8, 20)])
        assert len(result.lines) == 3
        assert result.lines[-1].line_number == 10
        assert len(result.warnings) == 1
        assert "truncat" in result.warnings[0].lower()


class TestReadInvalidRange:
    """TS-29-E6: Error for reversed range (start > end)."""

    def test_invalid_range(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.read import fox_read

        f = make_temp_file_with_lines(10)
        result = fox_read(str(f), [(10, 5)])
        assert isinstance(result, str)
        assert "invalid" in result.lower() or "range" in result.lower()
