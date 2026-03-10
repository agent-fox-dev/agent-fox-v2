"""Edit tool unit tests.

Test Spec: TS-29-8 (hash verify), TS-29-9 (atomicity), TS-29-10 (reverse order),
           TS-29-11 (delete),
           TS-29-E7 (mismatch), TS-29-E8 (missing file), TS-29-E9 (overlap)
Requirements: 29-REQ-3.1, 29-REQ-3.2, 29-REQ-3.3, 29-REQ-3.4,
              29-REQ-3.E1, 29-REQ-3.E2, 29-REQ-3.E3
"""

from __future__ import annotations

from pathlib import Path


class TestEditVerifiesHashes:
    """TS-29-8: fox_edit checks all hashes against current file content."""

    def test_verifies_hashes(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(10)
        read_result = fox_read(str(f), [(3, 5)])
        hashes = [ln.hash for ln in read_result.lines]

        edit_result = fox_edit(str(f), [EditOperation(3, 5, hashes, "new content\n")])
        assert edit_result.success is True
        assert "new content" in Path(f).read_text()


class TestEditAtomicBatch:
    """TS-29-9: All edits in a batch succeed or none are written."""

    def test_atomic_batch(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(10)
        original = Path(f).read_text()

        # Read valid hashes for range 3-5
        read_result = fox_read(str(f), [(3, 5)])
        valid_hashes = [ln.hash for ln in read_result.lines]

        # Create one valid edit and one with bad hashes
        valid_edit = EditOperation(3, 5, valid_hashes, "replaced\n")
        bad_edit = EditOperation(8, 9, ["badhash000000000", "badhash000000001"], "x\n")

        edit_result = fox_edit(str(f), [valid_edit, bad_edit])
        assert edit_result.success is False
        # File should be unchanged
        assert Path(f).read_text() == original


class TestEditReverseOrder:
    """TS-29-10: Batch edits at different ranges don't shift each other."""

    def test_reverse_order(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(20)

        # Read hashes for two non-overlapping ranges
        read_result = fox_read(str(f), [(3, 5), (15, 17)])
        lines_3_5 = [ln for ln in read_result.lines if ln.line_number <= 5]
        lines_15_17 = [ln for ln in read_result.lines if ln.line_number >= 15]

        hashes_low = [ln.hash for ln in lines_3_5]
        hashes_high = [ln.hash for ln in lines_15_17]

        # Replace lines 3-5 with 2 lines, lines 15-17 with 4 lines
        edit_low = EditOperation(3, 5, hashes_low, "new_low_a\nnew_low_b\n")
        edit_high = EditOperation(
            15, 17, hashes_high, "new_high_a\nnew_high_b\nnew_high_c\nnew_high_d\n"
        )

        result = fox_edit(str(f), [edit_low, edit_high])
        assert result.success is True

        final_lines = Path(f).read_text().splitlines()
        assert "new_low_a" in final_lines[2]
        assert "new_low_b" in final_lines[3]


class TestEditLineDeletion:
    """TS-29-11: Empty replacement content deletes the target range."""

    def test_line_deletion(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(10)

        read_result = fox_read(str(f), [(4, 6)])
        hashes = [ln.hash for ln in read_result.lines]

        result = fox_edit(str(f), [EditOperation(4, 6, hashes, "")])
        assert result.success is True
        # 10 lines - 3 deleted = 7 lines
        assert len(Path(f).read_text().splitlines()) == 7


class TestEditHashMismatch:
    """TS-29-E7: Stale hash causes full batch rejection."""

    def test_hash_mismatch_rejects(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(10)

        # Read hashes
        read_result = fox_read(str(f), [(3, 5)])
        hashes = [ln.hash for ln in read_result.lines]

        # Modify line 4 to create stale hash
        lines = Path(f).read_text().splitlines(keepends=True)
        lines[3] = "modified line 4\n"
        Path(f).write_text("".join(lines))

        result = fox_edit(str(f), [EditOperation(3, 5, hashes, "new")])
        assert result.success is False
        # Error should mention the mismatched line
        assert any("4" in e for e in result.errors)


class TestEditMissingFile:
    """TS-29-E8: Error for missing or non-writable file."""

    def test_missing_file(self) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.types import EditOperation

        result = fox_edit(
            "/missing.py", [EditOperation(1, 1, ["0000000000000000"], "x")]
        )
        assert result.success is False
        assert len(result.errors) > 0


class TestEditOverlappingRanges:
    """TS-29-E9: Error when two edits overlap."""

    def test_overlapping_ranges(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.edit import fox_edit
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.types import EditOperation

        f = make_temp_file_with_lines(20)

        # Read hashes for overlapping ranges
        read_result = fox_read(str(f), [(3, 9)])
        all_hashes = [ln.hash for ln in read_result.lines]

        edit_3_7 = EditOperation(3, 7, all_hashes[:5], "a\n")
        edit_5_9 = EditOperation(5, 9, all_hashes[2:], "b\n")

        result = fox_edit(str(f), [edit_3_7, edit_5_9])
        assert result.success is False
        assert any("overlap" in e.lower() for e in result.errors)
