"""Property tests for edit tool.

Test Spec: TS-29-P3 (round-trip), TS-29-P4 (atomicity), TS-29-P5 (stale rejection)
Requirements: 29-REQ-3.1, 29-REQ-3.2, 29-REQ-3.E1
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.tools.edit import fox_edit
from agent_fox.tools.read import fox_read
from agent_fox.tools.types import EditOperation, ReadResult


def _create_file(n: int, tmpdir: str) -> Path:
    """Create a temp file with n numbered lines in the given directory."""
    lines = [f"line {i} content\n" for i in range(1, n + 1)]
    p = Path(tmpdir) / f"test_{n}_{id(lines)}.txt"
    p.write_text("".join(lines))
    return p


class TestReadEditRoundTrip:
    """TS-29-P3: Reading lines then editing with same hashes and new content
    produces correct file — lines outside the range are unchanged."""

    @given(
        n=st.integers(min_value=5, max_value=50),
        data=st.data(),
    )
    @settings(max_examples=30, deadline=2000)
    def test_round_trip(self, n: int, data: st.DataObject) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = _create_file(n, tmpdir)
            original_lines = f.read_text().splitlines(keepends=True)

            # Pick a valid range
            s = data.draw(st.integers(min_value=1, max_value=n))
            e = data.draw(st.integers(min_value=s, max_value=n))

            # Read the range
            read_result = fox_read(str(f), [(s, e)])
            assert isinstance(read_result, ReadResult)
            hashes = [ln.hash for ln in read_result.lines]

            # Generate new content (simple to avoid encoding issues)
            new_content = data.draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                    ),
                    min_size=1,
                    max_size=50,
                )
            )
            if not new_content.endswith("\n"):
                new_content += "\n"

            # Apply edit
            result = fox_edit(str(f), [EditOperation(s, e, hashes, new_content)])
            assert result.success is True

            # Verify lines before range unchanged
            final_lines = f.read_text().splitlines(keepends=True)
            assert final_lines[: s - 1] == original_lines[: s - 1]

            # Verify lines after range unchanged
            new_replacement_lines = new_content.splitlines(keepends=True)
            offset = len(new_replacement_lines) - (e - s + 1)
            assert final_lines[e + offset :] == original_lines[e:]

            # Verify new content present
            assert new_content.strip() in f.read_text()


class TestEditAtomicity:
    """TS-29-P4: A batch with one stale hash leaves the file unchanged."""

    @given(
        n=st.integers(min_value=10, max_value=50),
        data=st.data(),
    )
    @settings(max_examples=30, deadline=2000)
    def test_atomicity(self, n: int, data: st.DataObject) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = _create_file(n, tmpdir)
            original = f.read_bytes()

            # Pick a valid range in the first half
            half = n // 2
            s1 = data.draw(st.integers(min_value=1, max_value=max(1, half - 1)))
            e1 = data.draw(st.integers(min_value=s1, max_value=max(s1, half - 1)))

            read_result = fox_read(str(f), [(s1, e1)])
            assert isinstance(read_result, ReadResult)
            valid_hashes = [ln.hash for ln in read_result.lines]
            valid_edit = EditOperation(s1, e1, valid_hashes, "replaced\n")

            # Create a bad edit with corrupted hashes in second half
            s2 = data.draw(st.integers(min_value=half + 1, max_value=n))
            e2 = data.draw(st.integers(min_value=s2, max_value=n))
            bad_hashes = ["badhash000000000"] * (e2 - s2 + 1)
            bad_edit = EditOperation(s2, e2, bad_hashes, "bad\n")

            result = fox_edit(str(f), [valid_edit, bad_edit])
            assert result.success is False
            assert f.read_bytes() == original


class TestStaleHashRejection:
    """TS-29-P5: Modifying a line between read and edit causes rejection."""

    @given(
        n=st.integers(min_value=5, max_value=50),
        data=st.data(),
    )
    @settings(max_examples=30, deadline=2000)
    def test_stale_rejection(self, n: int, data: st.DataObject) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = _create_file(n, tmpdir)

            # Read hashes for a range
            s = data.draw(st.integers(min_value=1, max_value=n))
            e = data.draw(st.integers(min_value=s, max_value=n))

            read_result = fox_read(str(f), [(s, e)])
            assert isinstance(read_result, ReadResult)
            hashes = [ln.hash for ln in read_result.lines]

            # Pick a line within the range to modify
            line_to_modify = data.draw(st.integers(min_value=s, max_value=e))

            # Modify the file
            lines = f.read_text().splitlines(keepends=True)
            lines[line_to_modify - 1] = f"MODIFIED line {line_to_modify}\n"
            f.write_text("".join(lines))

            # Attempt edit with stale hashes
            result = fox_edit(str(f), [EditOperation(s, e, hashes, "new\n")])
            assert result.success is False
            assert any("mismatch" in err.lower() for err in result.errors)
