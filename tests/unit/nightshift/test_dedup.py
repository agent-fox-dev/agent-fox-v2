"""Unit tests for dedup module: compute_fingerprint, embed_fingerprint, extract_fingerprint.

Test Spec: TS-79-1 through TS-79-8, TS-79-14, TS-79-15
Requirements: 79-REQ-1.1, 79-REQ-1.2, 79-REQ-1.3, 79-REQ-1.E1, 79-REQ-1.E2,
              79-REQ-2.1, 79-REQ-2.2, 79-REQ-2.E1, 79-REQ-2.E2, 79-REQ-5.1, 79-REQ-5.E1
"""

from __future__ import annotations

import hashlib


def _make_group(**overrides: object) -> object:
    """Create a FindingGroup with sensible defaults, overridden as needed."""
    from agent_fox.nightshift.finding import FindingGroup

    defaults: dict[str, object] = {
        "findings": [],
        "title": "Test Group",
        "body": "Test body",
        "category": "linter_debt",
        "affected_files": ["a.py"],
    }
    defaults.update(overrides)
    return FindingGroup(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-79-1: Fingerprint from category and files
# Requirement: 79-REQ-1.1
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    """Verify compute_fingerprint produces deterministic 16-char hex digests."""

    def test_fingerprint_is_16_char_hex(self) -> None:
        """TS-79-1: Fingerprint is 16-char lowercase hex string."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group = _make_group(category="linter_debt", affected_files=["b.py", "a.py"])
        fp = compute_fingerprint(group)  # type: ignore[arg-type]

        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_matches_sha256(self) -> None:
        """TS-79-1: Fingerprint equals SHA-256 of canonical input truncated to 16 chars."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group = _make_group(category="linter_debt", affected_files=["b.py", "a.py"])
        fp = compute_fingerprint(group)  # type: ignore[arg-type]

        # Files sorted: a.py, b.py; joined with \0; prepended with category + \0
        expected = hashlib.sha256(b"linter_debt\0a.py\0b.py").hexdigest()[:16]
        assert fp == expected

    # ---------------------------------------------------------------------------
    # TS-79-2: Identical groups produce identical fingerprints
    # Requirement: 79-REQ-1.2, 79-REQ-5.2
    # ---------------------------------------------------------------------------

    def test_same_category_and_files_same_fingerprint(self) -> None:
        """TS-79-2: Different file order and titles produce same fingerprint."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group_a = _make_group(category="dead_code", affected_files=["x.py", "y.py"], title="Title A")
        group_b = _make_group(category="dead_code", affected_files=["y.py", "x.py"], title="Title B")

        assert compute_fingerprint(group_a) == compute_fingerprint(group_b)  # type: ignore[arg-type]

    # ---------------------------------------------------------------------------
    # TS-79-3: Different category produces different fingerprint
    # Requirement: 79-REQ-1.3, 79-REQ-1.E2
    # ---------------------------------------------------------------------------

    def test_different_category_different_fingerprint(self) -> None:
        """TS-79-3: Same files but different category produces different fingerprint."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group_a = _make_group(category="linter_debt", affected_files=["a.py"])
        group_b = _make_group(category="dead_code", affected_files=["a.py"])

        assert compute_fingerprint(group_a) != compute_fingerprint(group_b)  # type: ignore[arg-type]

    # ---------------------------------------------------------------------------
    # TS-79-4: Empty affected_files fingerprint
    # Requirement: 79-REQ-1.E1
    # ---------------------------------------------------------------------------

    def test_empty_affected_files_uses_category_only(self) -> None:
        """TS-79-4: Empty affected_files computes fingerprint from category alone."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group = _make_group(category="todo_fixme", affected_files=[])
        fp = compute_fingerprint(group)  # type: ignore[arg-type]

        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)
        expected = hashlib.sha256(b"todo_fixme").hexdigest()[:16]
        assert fp == expected

    # ---------------------------------------------------------------------------
    # TS-79-14: Separator prevents ambiguity
    # Requirement: 79-REQ-5.1
    # ---------------------------------------------------------------------------

    def test_null_separator_prevents_ambiguity(self) -> None:
        """TS-79-14: category='ab' + file='c' differs from category='a' + file='bc'."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group_a = _make_group(category="ab", affected_files=["c"])
        group_b = _make_group(category="a", affected_files=["bc"])

        assert compute_fingerprint(group_a) != compute_fingerprint(group_b)  # type: ignore[arg-type]

    # ---------------------------------------------------------------------------
    # TS-79-15: Duplicate files are deduplicated before hashing
    # Requirement: 79-REQ-5.E1
    # ---------------------------------------------------------------------------

    def test_duplicate_files_deduplicated(self) -> None:
        """TS-79-15: Duplicate entries in affected_files don't affect fingerprint."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group_a = _make_group(affected_files=["a.py", "b.py", "a.py"])
        group_b = _make_group(affected_files=["a.py", "b.py"])

        assert compute_fingerprint(group_a) == compute_fingerprint(group_b)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-79-5: Embed fingerprint appends marker
# Requirement: 79-REQ-2.1
# ---------------------------------------------------------------------------


class TestEmbedFingerprint:
    """Verify embed_fingerprint appends the fingerprint HTML comment."""

    def test_embed_appends_marker(self) -> None:
        """TS-79-5: Result ends with the fingerprint HTML comment."""
        from agent_fox.nightshift.dedup import embed_fingerprint

        body = "## Issue\n\nSome description"
        result = embed_fingerprint(body, "a1b2c3d4e5f67890")

        assert result.endswith("\n<!-- af:fingerprint:a1b2c3d4e5f67890 -->")
        assert result.startswith("## Issue\n\nSome description")

    def test_embed_preserves_original_body(self) -> None:
        """embed_fingerprint preserves the original body content."""
        from agent_fox.nightshift.dedup import embed_fingerprint

        body = "## Issue\n\nSome description"
        result = embed_fingerprint(body, "a1b2c3d4e5f67890")

        assert "## Issue" in result
        assert "Some description" in result

    def test_embed_format_exact(self) -> None:
        """embed_fingerprint uses the exact marker format."""
        from agent_fox.nightshift.dedup import embed_fingerprint

        result = embed_fingerprint("body", "a1b2c3d4e5f67890")
        assert "<!-- af:fingerprint:a1b2c3d4e5f67890 -->" in result


# ---------------------------------------------------------------------------
# TS-79-6: Extract fingerprint from body
# Requirement: 79-REQ-2.2
# ---------------------------------------------------------------------------


class TestExtractFingerprint:
    """Verify extract_fingerprint parses fingerprint markers correctly."""

    def test_extract_from_body_with_marker(self) -> None:
        """TS-79-6: Returns hex string from a body containing a marker."""
        from agent_fox.nightshift.dedup import extract_fingerprint

        body = "Some text\n<!-- af:fingerprint:a1b2c3d4e5f67890 -->"
        fp = extract_fingerprint(body)

        assert fp == "a1b2c3d4e5f67890"

    # ---------------------------------------------------------------------------
    # TS-79-7: Extract returns None when no marker
    # Requirement: 79-REQ-2.E2
    # ---------------------------------------------------------------------------

    def test_extract_returns_none_when_no_marker(self) -> None:
        """TS-79-7: Returns None for a body without a fingerprint marker."""
        from agent_fox.nightshift.dedup import extract_fingerprint

        body = "Just a regular issue body"
        fp = extract_fingerprint(body)

        assert fp is None

    # ---------------------------------------------------------------------------
    # TS-79-8: Extract returns first marker when multiple present
    # Requirement: 79-REQ-2.E1
    # ---------------------------------------------------------------------------

    def test_extract_returns_first_when_multiple_markers(self) -> None:
        """TS-79-8: Returns the first fingerprint when multiple markers exist."""
        from agent_fox.nightshift.dedup import extract_fingerprint

        body = "text\n<!-- af:fingerprint:aaaa000000000000 -->\n<!-- af:fingerprint:bbbb000000000000 -->"
        fp = extract_fingerprint(body)

        assert fp == "aaaa000000000000"

    def test_extract_empty_body_returns_none(self) -> None:
        """Empty body returns None."""
        from agent_fox.nightshift.dedup import extract_fingerprint

        assert extract_fingerprint("") is None

    def test_extract_partial_marker_returns_none(self) -> None:
        """Malformed/incomplete marker returns None."""
        from agent_fox.nightshift.dedup import extract_fingerprint

        body = "<!-- af:fingerprint:not16chars -->"
        fp = extract_fingerprint(body)

        assert fp is None
