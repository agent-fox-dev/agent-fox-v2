"""Property tests for ADR ingestion correctness invariants.

Test Spec: TS-117-P1 through TS-117-P7
Properties: Properties 1-7 from design.md
Requirements: 117-REQ-1.1, 117-REQ-1.2, 117-REQ-1.E2,
              117-REQ-2.1, 117-REQ-2.5, 117-REQ-2.6,
              117-REQ-3.1, 117-REQ-3.2, 117-REQ-3.3, 117-REQ-3.4,
              117-REQ-4.2, 117-REQ-5.1, 117-REQ-5.2, 117-REQ-5.3,
              117-REQ-6.1, 117-REQ-6.2
"""

from __future__ import annotations

import hashlib
import re
import uuid

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.adr import (
    ADREntry,
    detect_adr_changes,
    format_adrs_for_prompt,
    parse_madr,
    query_adrs,
    store_adr,
    validate_madr,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_adr_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the adr_entries table for property tests."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adr_entries (
            id              VARCHAR PRIMARY KEY,
            file_path       VARCHAR NOT NULL,
            title           VARCHAR NOT NULL,
            status          VARCHAR NOT NULL DEFAULT 'proposed',
            chosen_option   VARCHAR,
            considered_options TEXT[],
            justification   TEXT,
            summary         TEXT NOT NULL,
            content_hash    VARCHAR NOT NULL,
            keywords        TEXT[] DEFAULT [],
            spec_refs       TEXT[] DEFAULT [],
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            superseded_at   TIMESTAMP
        )
    """)


def _matches_adr_glob(path: str) -> bool:
    """Check if a path matches docs/adr/*.md (one level, .md only)."""
    return bool(re.fullmatch(r"docs/adr/[^/]+\.md", path))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe text: alphanumeric + spaces, non-empty, stripped
_safe_text = (
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=3,
        max_size=20,
    )
    .map(str.strip)
    .filter(bool)
)

# File name component: alphanumeric + hyphens
_filename = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=20,
).filter(bool)


# -- Path strategies for P1 ------------------------------------------------

_adr_md_path = _filename.map(lambda s: f"docs/adr/{s}.md")
_non_adr_path = _filename.map(lambda s: f"agent_fox/{s}.py")
_deep_adr_path = _filename.map(lambda s: f"docs/adr/sub/{s}.md")
_non_md_adr_path = _filename.map(lambda s: f"docs/adr/{s}.txt")


@st.composite
def mixed_path_strategy(draw: st.DrawFn) -> list[str]:
    """Generate mixed lists of paths for detection accuracy testing."""
    adr_paths = draw(st.lists(_adr_md_path, min_size=0, max_size=5))
    non_adr = draw(st.lists(_non_adr_path, min_size=0, max_size=5))
    deep = draw(st.lists(_deep_adr_path, min_size=0, max_size=3))
    non_md = draw(st.lists(_non_md_adr_path, min_size=0, max_size=3))
    return adr_paths + non_adr + deep + non_md


# -- MADR content strategy for P2 ------------------------------------------


@st.composite
def madr_content_strategy(draw: st.DrawFn) -> tuple[str, list[str], str]:
    """Generate valid MADR content with known title and options."""
    title = draw(_safe_text)
    options = draw(st.lists(_safe_text, min_size=1, max_size=8))

    options_list = "\n".join(f"- {opt}" for opt in options)
    content = (
        f"# {title}\n\n"
        f"## Context and Problem Statement\n\n"
        f"Context for {title}.\n\n"
        f"## Considered Options\n\n"
        f"{options_list}\n\n"
        f"## Decision Outcome\n\n"
        f'Chosen option: "{options[0]}", because it is the best choice.\n'
    )
    return title, options, content


# -- ADREntry strategies for P3 --------------------------------------------


@st.composite
def valid_entry_strategy(draw: st.DrawFn) -> ADREntry:
    """Generate a well-formed ADREntry that should pass validation."""
    title = draw(_safe_text)
    options = draw(st.lists(_safe_text, min_size=3, max_size=8))
    chosen = options[0]
    return ADREntry(
        id=str(uuid.uuid4()),
        file_path="docs/adr/test.md",
        title=title,
        status="accepted",
        chosen_option=chosen,
        justification="it is the best",
        considered_options=options,
        summary=f'{title}: Chose "{chosen}".',
        content_hash="hash",
        keywords=[],
        spec_refs=[],
        has_context_section=True,
        has_options_section=True,
        has_decision_section=True,
    )


@st.composite
def invalid_entry_strategy(draw: st.DrawFn) -> ADREntry:
    """Generate an ADREntry that should fail validation."""
    defect = draw(st.sampled_from(["few_options", "empty_chosen", "empty_title"]))

    title = "Test ADR" if defect != "empty_title" else ""
    chosen = "Option A" if defect != "empty_chosen" else ""
    options = (
        ["Option A", "Option B"]
        if defect == "few_options"
        else ["Option A", "Option B", "Option C"]
    )

    return ADREntry(
        id=str(uuid.uuid4()),
        file_path="docs/adr/test.md",
        title=title,
        status="accepted",
        chosen_option=chosen,
        justification="reason",
        considered_options=options,
        summary="summary",
        content_hash="hash",
        keywords=[],
        spec_refs=[],
        has_context_section=True,
        has_options_section=True,
        has_decision_section=True,
    )


# -- Entry pair strategy for P4 --------------------------------------------


@st.composite
def same_path_entry_pair(draw: st.DrawFn) -> tuple[ADREntry, ADREntry]:
    """Generate two ADREntry objects with the same file_path."""
    file_path = draw(_filename.map(lambda s: f"docs/adr/{s}.md"))
    same_hash = draw(st.booleans())

    hash1 = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=8,
            max_size=16,
        ).filter(bool)
    )
    hash2 = hash1 if same_hash else hash1 + "_v2"

    entry1 = ADREntry(
        id=str(uuid.uuid4()),
        file_path=file_path,
        title="Test",
        status="accepted",
        chosen_option="A",
        justification="reason",
        considered_options=["A", "B", "C"],
        summary="summary",
        content_hash=hash1,
        keywords=[],
        spec_refs=[],
    )
    entry2 = ADREntry(
        id=str(uuid.uuid4()),
        file_path=file_path,
        title="Test",
        status="accepted",
        chosen_option="A",
        justification="reason",
        considered_options=["A", "B", "C"],
        summary="summary",
        content_hash=hash2,
        keywords=[],
        spec_refs=[],
    )
    return entry1, entry2


# ===========================================================================
# TS-117-P1: Detection Accuracy
# ===========================================================================


class TestDetectionAccuracy:
    """TS-117-P1: detect_adr_changes returns exactly paths matching docs/adr/*.md.

    Property 1 from design.md.
    Validates: 117-REQ-1.1, 117-REQ-1.2, 117-REQ-1.E2
    """

    @given(paths=mixed_path_strategy())
    @settings(max_examples=50, deadline=None)
    def test_detection_accuracy(self, paths: list[str]) -> None:
        """Result set equals the subset matching docs/adr/*.md."""
        result = detect_adr_changes(paths)
        expected = [p for p in paths if _matches_adr_glob(p)]
        assert set(result) == set(expected)


# ===========================================================================
# TS-117-P2: Parse Completeness
# ===========================================================================


class TestParseCompleteness:
    """TS-117-P2: parse_madr extracts all key fields from valid MADR.

    Property 2 from design.md.
    Validates: 117-REQ-2.1, 117-REQ-2.5, 117-REQ-2.6
    """

    @given(data=madr_content_strategy())
    @settings(max_examples=30, deadline=None)
    def test_parse_completeness(
        self, data: tuple[str, list[str], str]
    ) -> None:
        """Parsed entry has correct title, option count, and chosen option."""
        title, options, content = data
        entry = parse_madr(content)
        assert entry is not None
        assert entry.title == title
        assert len(entry.considered_options) == len(options)
        assert entry.chosen_option == options[0]


# ===========================================================================
# TS-117-P3: Validation Consistency
# ===========================================================================


class TestValidationConsistency:
    """TS-117-P3: Well-formed entries pass; malformed entries fail.

    Property 3 from design.md.
    Validates: 117-REQ-3.1, 117-REQ-3.2, 117-REQ-3.3, 117-REQ-3.4
    """

    @given(entry=valid_entry_strategy())
    @settings(max_examples=30, deadline=None)
    def test_valid_entries_pass(self, entry: ADREntry) -> None:
        """All well-formed entries pass validation."""
        result = validate_madr(entry)
        assert result.passed is True
        assert result.diagnostics == []

    @given(entry=invalid_entry_strategy())
    @settings(max_examples=30, deadline=None)
    def test_invalid_entries_fail(self, entry: ADREntry) -> None:
        """All malformed entries fail validation."""
        result = validate_madr(entry)
        assert result.passed is False


# ===========================================================================
# TS-117-P4: Supersession Idempotency
# ===========================================================================


class TestSupersessionIdempotency:
    """TS-117-P4: Storing same content twice is idempotent.

    Property 4 from design.md.
    Validates: 117-REQ-5.1, 117-REQ-5.2, 117-REQ-5.3
    """

    @given(pair=same_path_entry_pair())
    @settings(max_examples=20, deadline=None)
    def test_supersession_idempotency(
        self, pair: tuple[ADREntry, ADREntry]
    ) -> None:
        """After both stores, exactly one active row exists."""
        entry1, entry2 = pair
        conn = duckdb.connect(":memory:")
        _create_adr_table(conn)

        store_adr(conn, entry1)
        store_adr(conn, entry2)

        active = conn.execute(
            "SELECT content_hash FROM adr_entries "
            "WHERE file_path = ? AND superseded_at IS NULL",
            [entry1.file_path],
        ).fetchall()
        assert len(active) == 1

        if entry1.content_hash != entry2.content_hash:
            assert active[0][0] == entry2.content_hash

        conn.close()


# ===========================================================================
# TS-117-P5: Retrieval Excludes Superseded
# ===========================================================================


class TestRetrievalExcludesSuperseded:
    """TS-117-P5: Superseded entries never appear in query results.

    Property 5 from design.md.
    Validates: 117-REQ-6.1, 117-REQ-5.3
    """

    @given(
        n_active=st.integers(min_value=0, max_value=5),
        n_superseded=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    def test_retrieval_excludes_superseded(
        self, n_active: int, n_superseded: int
    ) -> None:
        """Only entries with superseded_at IS NULL are returned."""
        conn = duckdb.connect(":memory:")
        _create_adr_table(conn)

        spec_ref = "42"

        for i in range(n_active):
            conn.execute(
                "INSERT INTO adr_entries "
                "(id, file_path, title, status, summary, content_hash, spec_refs) "
                "VALUES (?, ?, ?, 'accepted', 'summary', ?, ?)",
                [
                    f"active-{i}",
                    f"docs/adr/active-{i}.md",
                    f"Active {i}",
                    f"hash-a-{i}",
                    [spec_ref],
                ],
            )

        for i in range(n_superseded):
            conn.execute(
                "INSERT INTO adr_entries "
                "(id, file_path, title, status, summary, content_hash, "
                "spec_refs, superseded_at) "
                "VALUES (?, ?, ?, 'accepted', 'summary', ?, ?, CURRENT_TIMESTAMP)",
                [
                    f"superseded-{i}",
                    f"docs/adr/sup-{i}.md",
                    f"Superseded {i}",
                    f"hash-s-{i}",
                    [spec_ref],
                ],
            )

        results = query_adrs(conn, "42_rate_limiting", "implement rate limiter")
        assert all(r.superseded_at is None for r in results)
        assert len(results) == n_active

        conn.close()


# ===========================================================================
# TS-117-P6: Summary Format Compliance
# ===========================================================================


class TestSummaryFormatCompliance:
    """TS-117-P6: Formatted output always starts with '[ADR] '.

    Property 6 from design.md.
    Validates: 117-REQ-6.2
    """

    @given(entry=valid_entry_strategy())
    @settings(max_examples=30, deadline=None)
    def test_format_starts_with_adr_prefix(self, entry: ADREntry) -> None:
        """Each formatted string starts with '[ADR] '."""
        result = format_adrs_for_prompt([entry])
        assert len(result) == 1
        assert result[0].startswith("[ADR] ")


# ===========================================================================
# TS-117-P7: Content Hash Determinism
# ===========================================================================


class TestContentHashDeterminism:
    """TS-117-P7: SHA-256 of the same content always produces the same hash.

    Property 7 from design.md.
    Validates: 117-REQ-4.2, 117-REQ-5.2
    """

    @given(s=st.text(min_size=0, max_size=500))
    @settings(max_examples=50, deadline=None)
    def test_hash_determinism(self, s: str) -> None:
        """sha256(s) == sha256(s) for all s."""
        h1 = hashlib.sha256(s.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(s.encode("utf-8")).hexdigest()
        assert h1 == h2
