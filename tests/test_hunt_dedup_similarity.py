"""Tests for embedding-based deduplication in the hunt scan pipeline.

Test cases: TS-110-4 through TS-110-9, TS-110-E1 through TS-110-E3,
TS-110-E8, TS-110-E9, TS-110-P1 through TS-110-P4, TS-110-P7, TS-110-P8

Requirements: 110-REQ-2.1 through 110-REQ-2.E2, 110-REQ-3.1 through 110-REQ-3.E2,
110-REQ-7.1, 110-REQ-7.E1, 110-REQ-7.E2
"""

from __future__ import annotations

import asyncio
import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# These imports will fail until task group 3 implements them.
# All tests in this file will error on collection until then.
from agent_fox.nightshift.dedup import (
    build_finding_group_text,
    build_issue_text,
    compute_fingerprint,
    cosine_similarity,
    embed_fingerprint,
    filter_known_duplicates,
)
from agent_fox.nightshift.finding import Finding, FindingGroup
from agent_fox.platform.protocol import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**overrides: object) -> Finding:
    """Create a Finding with sensible defaults, overridden as needed."""
    defaults: dict[str, object] = {
        "category": "dead_code",
        "title": "Unused function",
        "description": "Function is never called.",
        "severity": "minor",
        "affected_files": ["src/a.py"],
        "suggested_fix": "Remove the function.",
        "evidence": "grep: no callers found",
        "group_key": "dead_code:unused_fn",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


def _make_group(**overrides: object) -> FindingGroup:
    """Create a FindingGroup with sensible defaults."""
    title = str(overrides.pop("title", "Unused function"))
    category = str(overrides.pop("category", "dead_code"))
    affected_files = list(overrides.pop("affected_files", ["src/a.py"]))  # type: ignore[arg-type]
    finding = _make_finding(
        title=title, category=category, affected_files=affected_files
    )
    defaults: dict[str, object] = {
        "findings": [finding],
        "title": title,
        "body": "Issue body text.",
        "category": category,
        "affected_files": affected_files,
    }
    defaults.update(overrides)
    return FindingGroup(**defaults)  # type: ignore[arg-type]


def _make_issue(
    number: int = 1,
    title: str = "Dead code",
    body: str = "",
    fingerprint: str | None = None,
) -> IssueResult:
    """Create an IssueResult, optionally embedding a fingerprint."""
    if fingerprint is not None:
        body = embed_fingerprint(body, fingerprint)
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/org/repo/issues/{number}",
        body=body,
    )


class _SameVectorEmbedder:
    """Returns the same vector for every text (similarity = 1.0 between any two)."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.embed_batch_call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        return [list(self._vector) for _ in texts]


class _SequenceEmbedder:
    """Returns vectors from a fixed sequence, cycling from the last after exhaustion."""

    def __init__(self, *vectors: list[float] | None) -> None:
        self._vectors: list[list[float] | None] = list(vectors)
        self._index = 0
        self.embed_batch_call_count = 0
        self.all_texts: list[str] = []

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        self.all_texts.extend(texts)
        result: list[list[float] | None] = []
        for _ in texts:
            if self._index < len(self._vectors):
                result.append(self._vectors[self._index])
                self._index += 1
            else:
                # Fall back to the last vector
                result.append(self._vectors[-1] if self._vectors else [1.0, 0.0, 0.0])
        return result


class _FailingPlatform:
    """Platform that always raises on list_issues_by_label."""

    def __init__(self) -> None:
        self.list_issues_calls: list[dict[str, str]] = []

    async def list_issues_by_label(
        self, label: str, state: str = "open", **kwargs: object
    ) -> list[IssueResult]:
        self.list_issues_calls.append({"label": label, "state": state})
        raise RuntimeError("Platform API failure (test)")

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> IssueResult:
        raise RuntimeError("create_issue not expected")


class _MockPlatform:
    """Async mock platform with configurable hunt/ignore issues."""

    def __init__(
        self,
        hunt_issues: list[IssueResult] | None = None,
        ignore_issues: list[IssueResult] | None = None,
    ) -> None:
        self._hunt_issues: list[IssueResult] = hunt_issues or []
        self._ignore_issues: list[IssueResult] = ignore_issues or []
        self.list_issues_calls: list[dict[str, str]] = []

    async def list_issues_by_label(
        self, label: str, state: str = "open", **kwargs: object
    ) -> list[IssueResult]:
        self.list_issues_calls.append({"label": label, "state": state})
        if label == "af:hunt":
            return list(self._hunt_issues)
        if label == "af:ignore":
            return list(self._ignore_issues)
        return []

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> IssueResult:
        return IssueResult(number=99, title=title, html_url="", body=body)


# ---------------------------------------------------------------------------
# TS-110-4: cosine_similarity unit tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """TS-110-4: cosine_similarity() returns correct values for known vectors."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have cosine similarity 1.0."""
        assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(
            1.0
        )

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have cosine similarity 0.0."""
        assert cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(
            0.0
        )

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have cosine similarity -1.0."""
        assert cosine_similarity([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]) == pytest.approx(
            -1.0
        )

    def test_general_vectors(self) -> None:
        """General case: similarity of [1,1] and [1,0] is 1/sqrt(2)."""
        expected = 1.0 / math.sqrt(2.0)
        assert cosine_similarity([1.0, 1.0], [1.0, 0.0]) == pytest.approx(
            expected, abs=1e-9
        )

    # TS-110-E1: None vector returns 0.0
    def test_none_first_arg(self) -> None:
        """TS-110-E1: None as first vector returns 0.0."""
        assert cosine_similarity(None, [1.0, 0.0, 0.0]) == 0.0  # type: ignore[arg-type]

    def test_none_second_arg(self) -> None:
        """TS-110-E1: None as second vector returns 0.0."""
        assert cosine_similarity([1.0, 0.0, 0.0], None) == 0.0  # type: ignore[arg-type]

    def test_empty_first_arg(self) -> None:
        """Empty first vector returns 0.0."""
        assert cosine_similarity([], [1.0, 0.0, 0.0]) == 0.0

    def test_empty_second_arg(self) -> None:
        """Empty second vector returns 0.0."""
        assert cosine_similarity([1.0, 0.0, 0.0], []) == 0.0

    def test_both_none(self) -> None:
        """Both None returns 0.0."""
        assert cosine_similarity(None, None) == 0.0  # type: ignore[arg-type]

    def test_both_empty(self) -> None:
        """Both empty returns 0.0."""
        assert cosine_similarity([], []) == 0.0


# ---------------------------------------------------------------------------
# TS-110-5: build_finding_group_text unit tests
# ---------------------------------------------------------------------------


class TestBuildFindingGroupText:
    """TS-110-5: build_finding_group_text() produces the expected format."""

    def test_basic_format(self) -> None:
        """Format: '{category}: {title}\\nFiles: {files}'."""
        group = _make_group(
            category="dead_code",
            title="Unused function",
            affected_files=["src/a.py", "src/b.py"],
        )
        result = build_finding_group_text(group)
        assert result == "dead_code: Unused function\nFiles: src/a.py, src/b.py"

    def test_single_file(self) -> None:
        """Single file in affected_files."""
        group = _make_group(
            category="security",
            title="SQL injection risk",
            affected_files=["app/db.py"],
        )
        result = build_finding_group_text(group)
        assert result == "security: SQL injection risk\nFiles: app/db.py"

    def test_empty_files(self) -> None:
        """Empty affected_files produces empty Files section."""
        group = FindingGroup(
            findings=[],
            title="No files",
            body="",
            category="misc",
            affected_files=[],
        )
        result = build_finding_group_text(group)
        assert result == "misc: No files\nFiles: "

    def test_multiple_files_comma_separated(self) -> None:
        """Multiple files are comma-separated."""
        group = _make_group(
            category="linter_debt",
            title="Many issues",
            affected_files=["a.py", "b.py", "c.py"],
        )
        result = build_finding_group_text(group)
        assert result == "linter_debt: Many issues\nFiles: a.py, b.py, c.py"


# ---------------------------------------------------------------------------
# TS-110-6: build_issue_text unit tests
# ---------------------------------------------------------------------------


class TestBuildIssueText:
    """TS-110-6: build_issue_text() produces '{title}\\n{body[:500]}'."""

    def test_short_body(self) -> None:
        """Short body included verbatim."""
        issue = IssueResult(
            number=1,
            title="Dead code",
            html_url="https://example.com/1",
            body="Short body text.",
        )
        result = build_issue_text(issue)
        assert result == "Dead code\nShort body text."

    def test_long_body_truncated_at_500(self) -> None:
        """Body longer than 500 chars is truncated to 500."""
        issue = IssueResult(
            number=1,
            title="Dead code",
            html_url="https://example.com/1",
            body="x" * 600,
        )
        result = build_issue_text(issue)
        assert result == "Dead code\n" + "x" * 500

    def test_exact_500_chars_body(self) -> None:
        """Body of exactly 500 chars is included verbatim."""
        issue = IssueResult(
            number=1,
            title="Title",
            html_url="https://example.com/1",
            body="y" * 500,
        )
        result = build_issue_text(issue)
        assert result == "Title\n" + "y" * 500

    def test_empty_body(self) -> None:
        """Empty body produces title + newline."""
        issue = IssueResult(
            number=1,
            title="Title",
            html_url="https://example.com/1",
            body="",
        )
        result = build_issue_text(issue)
        assert result == "Title\n"


# ---------------------------------------------------------------------------
# TS-110-7: filter_known_duplicates fetches state="all"
# ---------------------------------------------------------------------------


class TestFilterKnownDuplicatesFetchesAllStates:
    """TS-110-7: filter_known_duplicates fetches issues with state='all'."""

    async def test_fetches_all_states(self) -> None:
        """list_issues_by_label is called with state='all'."""
        group = _make_group()
        fingerprint = compute_fingerprint(group)  # type: ignore[arg-type]
        closed_issue = _make_issue(number=1, fingerprint=fingerprint)
        platform = _MockPlatform(hunt_issues=[closed_issue])

        result = await filter_known_duplicates([group], platform)  # type: ignore[arg-type]

        # Must have called with state="all"
        assert any(c["state"] == "all" for c in platform.list_issues_calls)
        # Fingerprint-matched group must be filtered out
        assert len(result) == 0

    async def test_closed_issue_fingerprint_match_filtered(self) -> None:
        """A group matching a closed issue fingerprint is filtered out."""
        group = _make_group(title="Closed match")
        fingerprint = compute_fingerprint(group)  # type: ignore[arg-type]
        closed_issue = _make_issue(number=5, fingerprint=fingerprint)
        platform = _MockPlatform(hunt_issues=[closed_issue])

        result = await filter_known_duplicates([group], platform)  # type: ignore[arg-type]

        assert len(result) == 0


# ---------------------------------------------------------------------------
# TS-110-8: embedding similarity filters duplicates
# ---------------------------------------------------------------------------


class TestEmbeddingSimilarityFilters:
    """TS-110-8: Groups with high embedding similarity to existing issues are filtered."""

    async def test_high_similarity_group_filtered(self) -> None:
        """Group with similarity > threshold is filtered out."""
        group = _make_group(category="dead_code", title="Unused function")
        existing_issue = _make_issue(number=2, title="Dead code: unused function")

        # Same vector for all texts → similarity = 1.0 > 0.85
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(hunt_issues=[existing_issue])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert len(result) == 0

    async def test_similarity_threshold_parameter_accepted(self) -> None:
        """filter_known_duplicates accepts similarity_threshold parameter."""
        group = _make_group()
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(hunt_issues=[])

        # Should not raise TypeError even though these are new parameters
        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert isinstance(result, list)

    async def test_embedder_parameter_accepted(self) -> None:
        """filter_known_duplicates accepts embedder parameter."""
        group = _make_group()
        embedder = _SameVectorEmbedder([0.5, 0.5, 0.0])
        platform = _MockPlatform(hunt_issues=[])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            embedder=embedder,
        )

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-110-9: fingerprint checked before embedding (short-circuit)
# ---------------------------------------------------------------------------


class TestFingerprintShortCircuits:
    """TS-110-9: Fingerprint match short-circuits embedding comparison."""

    async def test_fingerprint_matched_group_not_embedded(self) -> None:
        """Group matched by fingerprint is not processed by the embedder."""
        group = _make_group()
        fingerprint = compute_fingerprint(group)  # type: ignore[arg-type]
        issue = _make_issue(number=1, fingerprint=fingerprint)

        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(hunt_issues=[issue])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            embedder=embedder,
        )

        # Group is filtered by fingerprint
        assert len(result) == 0
        # Embedder should not have been called for the fingerprint-matched group
        # (at most once for issue embeddings if the implementation is eager,
        # but never for the matched group itself)
        assert embedder.embed_batch_call_count <= 1


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestNoEmbedderFallback:
    """TS-110-E2: When embedder=None, fall back to fingerprint-only."""

    async def test_no_embedder_passes_non_fingerprint_match(self) -> None:
        """Without embedder, semantically similar but fingerprint-distinct group passes."""
        group = _make_group(category="dead_code", title="Unique title")
        # Issue with different fingerprint (different files)
        existing_issue = _make_issue(
            number=2, title="Dead code: unused function", body="Different issue"
        )
        platform = _MockPlatform(hunt_issues=[existing_issue])

        # No embedder → fingerprint-only mode
        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            embedder=None,
        )

        # Group passes through because no fingerprint match and no embedder
        assert len(result) == 1

    async def test_fingerprint_match_still_filtered_without_embedder(self) -> None:
        """Fingerprint matches are still filtered even without embedder."""
        group = _make_group()
        fingerprint = compute_fingerprint(group)  # type: ignore[arg-type]
        issue = _make_issue(number=1, fingerprint=fingerprint)
        platform = _MockPlatform(hunt_issues=[issue])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            embedder=None,
        )

        assert len(result) == 0


class TestPlatformFailureFallsOpen:
    """TS-110-E3: On platform failure, all groups pass through."""

    async def test_platform_failure_returns_all_groups(self) -> None:
        """Platform API failure → all input groups returned unfiltered."""
        g1 = _make_group(title="Group 1")
        g2 = _make_group(title="Group 2")
        platform = _FailingPlatform()

        result = await filter_known_duplicates([g1, g2], platform)  # type: ignore[arg-type]

        assert len(result) == 2

    async def test_platform_failure_with_zero_groups(self) -> None:
        """Platform failure with no groups returns empty list."""
        platform = _FailingPlatform()

        result = await filter_known_duplicates([], platform)  # type: ignore[arg-type]

        assert len(result) == 0


class TestThresholdZero:
    """TS-110-E8: Threshold 0.0 suppresses all groups with any positive similarity."""

    async def test_threshold_zero_suppresses_near_orthogonal(self) -> None:
        """At threshold=0.0, any similarity > 0.0 causes suppression."""
        group = _make_group()
        existing_issue = _make_issue(number=1, title="Different issue")

        # Near-orthogonal vectors: similarity ≈ 0.198 > 0.0
        embedder = _SequenceEmbedder([1.0, 0.1, 0.0], [0.1, 1.0, 0.0])
        platform = _MockPlatform(hunt_issues=[existing_issue])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.0,
            embedder=embedder,
        )

        assert len(result) == 0


class TestThresholdOne:
    """TS-110-E9: Threshold 1.0 only matches identical embeddings."""

    async def test_threshold_one_passes_high_but_imperfect_similarity(self) -> None:
        """At threshold=1.0, similarity 0.995 < 1.0 → group passes through."""
        group = _make_group()
        existing_issue = _make_issue(number=1, title="Very similar issue")

        # High but not perfect similarity: [1.0, 0.1] vs [1.0, 0.0]
        # cosine ≈ 1.0 / sqrt(1.01) ≈ 0.995
        embedder = _SequenceEmbedder([1.0, 0.1, 0.0], [1.0, 0.0, 0.0])
        platform = _MockPlatform(hunt_issues=[existing_issue])

        result = await filter_known_duplicates(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=1.0,
            embedder=embedder,
        )

        # 0.995 < 1.0 → not suppressed
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestCosineSimilaritySymmetry:
    """TS-110-P2: cosine_similarity(a, b) == cosine_similarity(b, a)."""

    @given(
        a=st.lists(
            st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            min_size=1,
            max_size=10,
        ),
        b=st.lists(
            st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            min_size=1,
            max_size=10,
        ),
    )
    def test_symmetry(self, a: list[float], b: list[float]) -> None:
        """Symmetry: cosine_similarity(a, b) == cosine_similarity(b, a)."""
        result_ab = cosine_similarity(a, b)
        result_ba = cosine_similarity(b, a)
        assert result_ab == pytest.approx(result_ba, abs=1e-9)


@pytest.mark.property
class TestCosineSimilarityBounds:
    """TS-110-P3: cosine_similarity is bounded in [-1.0, 1.0]."""

    @given(
        a=st.lists(
            st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            min_size=1,
            max_size=10,
        ),
        b=st.lists(
            st.floats(
                allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
            ),
            min_size=1,
            max_size=10,
        ),
    )
    def test_bounds(self, a: list[float], b: list[float]) -> None:
        """Bounds: cosine_similarity(a, b) in [-1.0, 1.0] for non-zero vectors."""
        assume(any(x != 0.0 for x in a))
        assume(any(x != 0.0 for x in b))
        sim = cosine_similarity(a, b)
        assert -1.0 - 1e-9 <= sim <= 1.0 + 1e-9


@pytest.mark.property
class TestCosineSimilarityNullSafety:
    """TS-110-P4: None or empty vectors always return 0.0."""

    @given(
        a=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
            min_size=1,
            max_size=10,
        )
    )
    def test_none_returns_zero(self, a: list[float]) -> None:
        """None vector → 0.0 (both argument positions)."""
        assert cosine_similarity(a, None) == 0.0  # type: ignore[arg-type]
        assert cosine_similarity(None, a) == 0.0  # type: ignore[arg-type]

    @given(
        a=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
            min_size=1,
            max_size=10,
        )
    )
    def test_empty_returns_zero(self, a: list[float]) -> None:
        """Empty vector → 0.0 (both argument positions)."""
        assert cosine_similarity(a, []) == 0.0
        assert cosine_similarity([], a) == 0.0


@pytest.mark.property
class TestFingerprintSuperset:
    """TS-110-P1: Enhanced filter returns a subset of fingerprint-only filter."""

    @given(n=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20)
    def test_enhanced_is_subset_of_fingerprint_only(self, n: int) -> None:
        """With no existing issues, both modes return all groups (enhanced ⊆ fp-only)."""
        groups = [_make_group(title=f"Group {i}") for i in range(n)]
        platform_fp = _MockPlatform(hunt_issues=[])
        platform_en = _MockPlatform(hunt_issues=[])
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])

        loop = asyncio.new_event_loop()
        try:
            r_fp = loop.run_until_complete(
                filter_known_duplicates(
                    groups,  # type: ignore[arg-type]
                    platform_fp,  # type: ignore[arg-type]
                    similarity_threshold=1.0,
                )
            )
            r_en = loop.run_until_complete(
                filter_known_duplicates(
                    groups,  # type: ignore[arg-type]
                    platform_en,  # type: ignore[arg-type]
                    similarity_threshold=0.85,
                    embedder=embedder,
                )
            )
        finally:
            loop.close()

        fp_titles = {g.title for g in r_fp}
        en_titles = {g.title for g in r_en}
        assert en_titles <= fp_titles


@pytest.mark.property
class TestThresholdMonotonicity:
    """TS-110-P7: Higher threshold → fewer groups suppressed (more pass through)."""

    @given(
        t1=st.floats(min_value=0.0, max_value=0.99),
        t2=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=30)
    def test_higher_threshold_more_groups_pass(self, t1: float, t2: float) -> None:
        """len(filter(groups, t2)) >= len(filter(groups, t1)) when t1 < t2."""
        assume(math.isfinite(t1) and math.isfinite(t2))
        assume(t1 < t2)

        group = _make_group()
        existing_issue = _make_issue(1, "Similar issue")

        # Use same vector for all texts → similarity = 1.0
        embedder1 = _SameVectorEmbedder([1.0, 0.0, 0.0])
        embedder2 = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform1 = _MockPlatform(hunt_issues=[existing_issue])
        platform2 = _MockPlatform(hunt_issues=[existing_issue])

        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(
                filter_known_duplicates(
                    [group],  # type: ignore[arg-type]
                    platform1,  # type: ignore[arg-type]
                    similarity_threshold=t1,
                    embedder=embedder1,
                )
            )
            r2 = loop.run_until_complete(
                filter_known_duplicates(
                    [group],  # type: ignore[arg-type]
                    platform2,  # type: ignore[arg-type]
                    similarity_threshold=t2,
                    embedder=embedder2,
                )
            )
        finally:
            loop.close()

        assert len(r2) >= len(r1)


@pytest.mark.property
class TestFailOpenGuarantee:
    """TS-110-P8: Platform failure → all groups returned unmodified."""

    @given(n=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20)
    def test_fail_open_returns_all_groups(self, n: int) -> None:
        """When platform raises, all input groups are returned."""
        groups = [_make_group(title=f"Group {i}") for i in range(n)]
        platform = _FailingPlatform()

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                filter_known_duplicates(groups, platform)  # type: ignore[arg-type]
            )
        finally:
            loop.close()

        assert len(result) == n
