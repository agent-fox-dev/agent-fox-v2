"""Property tests for hunt scan deduplication.

Test Spec: TS-79-P1 through TS-79-P6
Properties: 1-6 from design.md
Requirements: 79-REQ-1.1, 79-REQ-1.2, 79-REQ-2.1, 79-REQ-2.2, 79-REQ-4.2,
              79-REQ-4.4, 79-REQ-4.E1, 79-REQ-5.1, 79-REQ-5.2, 79-REQ-1.E1
"""

from __future__ import annotations

import asyncio
import random
from unittest.mock import AsyncMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    min_size=1,
    max_size=40,
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_./",
)

_hex_chars = "0123456789abcdef"
_hex_16 = st.text(min_size=16, max_size=16, alphabet=_hex_chars)

_file_path = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_./",
)

_files_list = st.lists(_file_path, min_size=0, max_size=5)


def _make_group(category: str, affected_files: list[str]) -> object:
    """Build a FindingGroup for property testing."""
    from agent_fox.nightshift.finding import FindingGroup

    return FindingGroup(
        findings=[],
        title=f"Group: {category}",
        body="Property test group",
        category=category,
        affected_files=affected_files,
    )


def _make_issue_result_with_fp(number: int, fp: str) -> object:
    """Build an IssueResult whose body embeds the given fingerprint."""
    from agent_fox.nightshift.dedup import embed_fingerprint
    from agent_fox.platform.github import IssueResult

    body = embed_fingerprint("Existing issue body", fp)
    return IssueResult(
        number=number,
        title=f"Issue #{number}",
        html_url=f"https://github.com/example/repo/issues/{number}",
        body=body,
    )


# ---------------------------------------------------------------------------
# TS-79-P1: Fingerprint Determinism
# Property 1 from design.md
# Validates: 79-REQ-1.1, 79-REQ-1.2, 79-REQ-5.1, 79-REQ-5.2
# ---------------------------------------------------------------------------


class TestFingerprintDeterminism:
    """Same category and same files always produce the same fingerprint."""

    @given(
        category=_safe_text,
        files=_files_list,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_shuffled_files_same_fingerprint(self, category: str, files: list[str]) -> None:
        """TS-79-P1: Shuffled file order produces same fingerprint."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        shuffled = files[:]
        random.shuffle(shuffled)

        group_a = _make_group(category=category, affected_files=files)
        group_b = _make_group(category=category, affected_files=shuffled)

        assert compute_fingerprint(group_a) == compute_fingerprint(group_b)  # type: ignore[arg-type]

    @given(
        category=_safe_text,
        files=_files_list,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_same_inputs_deterministic(self, category: str, files: list[str]) -> None:
        """TS-79-P1: Calling compute_fingerprint twice with same inputs yields same result."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group = _make_group(category=category, affected_files=files)
        assert compute_fingerprint(group) == compute_fingerprint(group)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-79-P2: Fingerprint Uniqueness
# Property 2 from design.md
# Validates: 79-REQ-1.3, 79-REQ-1.E2
# ---------------------------------------------------------------------------


class TestFingerprintUniqueness:
    """Different category or different files produce different fingerprints."""

    @given(
        cat_a=_safe_text,
        cat_b=_safe_text,
        files=_files_list,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_categories_different_fingerprints(self, cat_a: str, cat_b: str, files: list[str]) -> None:
        """TS-79-P2: Different categories with same files produce different fingerprints."""
        from hypothesis import assume

        from agent_fox.nightshift.dedup import compute_fingerprint

        assume(cat_a != cat_b)

        group_a = _make_group(category=cat_a, affected_files=files)
        group_b = _make_group(category=cat_b, affected_files=files)

        assert compute_fingerprint(group_a) != compute_fingerprint(group_b)  # type: ignore[arg-type]

    @given(
        category=_safe_text,
        files_a=_files_list,
        files_b=_files_list,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_files_different_fingerprints(
        self, category: str, files_a: list[str], files_b: list[str]
    ) -> None:
        """TS-79-P2: Different deduplicated-sorted files with same category produce different fingerprints."""
        from hypothesis import assume

        from agent_fox.nightshift.dedup import compute_fingerprint

        # Only test when sorted-deduped sets differ
        assume(sorted(set(files_a)) != sorted(set(files_b)))

        group_a = _make_group(category=category, affected_files=files_a)
        group_b = _make_group(category=category, affected_files=files_b)

        assert compute_fingerprint(group_a) != compute_fingerprint(group_b)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TS-79-P3: Embed-Extract Round-Trip
# Property 3 from design.md
# Validates: 79-REQ-2.1, 79-REQ-2.2
# ---------------------------------------------------------------------------


class TestEmbedExtractRoundTrip:
    """Embedding then extracting a fingerprint recovers the original."""

    @given(
        body=st.text(min_size=0, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz \n#_-./"),
        fp=_hex_16,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip_recovers_fingerprint(self, body: str, fp: str) -> None:
        """TS-79-P3: extract_fingerprint(embed_fingerprint(body, fp)) == fp."""
        from agent_fox.nightshift.dedup import embed_fingerprint, extract_fingerprint

        embedded = embed_fingerprint(body, fp)
        recovered = extract_fingerprint(embedded)

        assert recovered == fp


# ---------------------------------------------------------------------------
# TS-79-P4: Dedup Gate Conservation
# Property 4 from design.md
# Validates: 79-REQ-4.2, 79-REQ-4.4, 79-REQ-4.E3
# ---------------------------------------------------------------------------


@st.composite
def _groups_and_known_fps(draw: st.DrawFn) -> tuple[list[object], set[str]]:
    """Generate a list of FindingGroups and a set of known fingerprints."""
    from agent_fox.nightshift.dedup import compute_fingerprint

    n = draw(st.integers(min_value=0, max_value=6))
    groups = []
    for i in range(n):
        category = draw(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"))
        files = draw(st.lists(_file_path, min_size=0, max_size=3))
        # Use index to ensure uniqueness across groups when desired
        groups.append(_make_group(category=f"{category}_{i}", affected_files=files))

    # Generate some known fingerprints, possibly overlapping with group fingerprints
    group_fps = [compute_fingerprint(g) for g in groups]  # type: ignore[arg-type]
    known = set(draw(st.lists(st.sampled_from(group_fps) if group_fps else st.just(""), min_size=0, max_size=n)))
    known.discard("")  # remove empty string if it crept in from st.just("")
    return groups, known


class TestDedupGateConservation:
    """The gate returns a subset; no novel group is dropped, no duplicate passes."""

    @given(data=_groups_and_known_fps())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_conservation_invariant(self, data: tuple[list[object], set[str]]) -> None:
        """TS-79-P4: Result subset; novel groups kept; duplicate groups removed."""
        from agent_fox.nightshift.dedup import compute_fingerprint, filter_known_duplicates

        groups, known_fps = data

        # Build mock platform returning issues with known fingerprints
        known_issue_results = [_make_issue_result_with_fp(i + 1, fp) for i, fp in enumerate(known_fps)]
        mock_platform = AsyncMock()
        mock_platform.list_issues_by_label = AsyncMock(return_value=known_issue_results)

        result = asyncio.run(filter_known_duplicates(groups, mock_platform))  # type: ignore[arg-type]

        # Result is a subset of input
        assert all(g in groups for g in result)

        # Every novel group passes through
        for g in groups:
            fp = compute_fingerprint(g)  # type: ignore[arg-type]
            if fp not in known_fps:
                assert g in result, f"Novel group with fp={fp} was incorrectly filtered out"

        # Every duplicate is excluded
        for g in groups:
            fp = compute_fingerprint(g)  # type: ignore[arg-type]
            if fp in known_fps:
                assert g not in result, f"Duplicate group with fp={fp} was incorrectly passed through"


# ---------------------------------------------------------------------------
# TS-79-P5: Fail-Open Guarantee
# Property 5 from design.md
# Validates: 79-REQ-4.E1
# ---------------------------------------------------------------------------


class TestFailOpenGuarantee:
    """Platform failure returns all groups unchanged."""

    @given(
        categories=st.lists(
            st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_fail_open_returns_all_groups(self, categories: list[str]) -> None:
        """TS-79-P5: filter_known_duplicates(groups, failing_platform) == groups."""
        from agent_fox.nightshift.dedup import filter_known_duplicates

        groups = [_make_group(category=cat, affected_files=[]) for cat in categories]

        failing_platform = AsyncMock()
        failing_platform.list_issues_by_label = AsyncMock(side_effect=RuntimeError("platform failure"))

        result = asyncio.run(filter_known_duplicates(groups, failing_platform))  # type: ignore[arg-type]

        assert result == groups


# ---------------------------------------------------------------------------
# TS-79-P6: Empty Files Stability
# Property 6 from design.md
# Validates: 79-REQ-1.E1
# ---------------------------------------------------------------------------


class TestEmptyFilesStability:
    """Empty affected_files produces valid fingerprint from category alone."""

    @given(category=st.text(min_size=1, max_size=40, alphabet="abcdefghijklmnopqrstuvwxyz_"))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_empty_files_produces_valid_fingerprint(self, category: str) -> None:
        """TS-79-P6: Fingerprint is valid 16-char hex for any category with empty files."""
        from agent_fox.nightshift.dedup import compute_fingerprint

        group = _make_group(category=category, affected_files=[])
        fp = compute_fingerprint(group)  # type: ignore[arg-type]

        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)
