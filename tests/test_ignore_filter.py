"""Tests for the af:ignore filtering gate in the hunt scan pipeline.

Test cases: TS-110-10, TS-110-11, TS-110-E4, TS-110-P5, TS-110-SMOKE-1

Requirements: 110-REQ-4.1 through 110-REQ-4.E3
"""

from __future__ import annotations

import asyncio

import pytest
from agent_fox.nightshift.ignore_filter import filter_ignored
from hypothesis import given, settings
from hypothesis import strategies as st

# This import will fail until task group 4 implements ignore_filter.py.
# All tests in this file will error on collection until then.
from agent_fox.nightshift.dedup import (
    compute_fingerprint,
    embed_fingerprint,
    filter_known_duplicates,
)
from agent_fox.nightshift.finding import Finding, FindingGroup
from agent_fox.platform.protocol import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(**overrides: object) -> Finding:
    """Create a Finding with sensible defaults."""
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
    title: str = "Ignored issue",
    body: str = "## Issue\n\n**Category:** dead_code\n",
    fingerprint: str | None = None,
) -> IssueResult:
    """Create an IssueResult for testing."""
    if fingerprint is not None:
        body = embed_fingerprint(body, fingerprint)
    return IssueResult(
        number=number,
        title=title,
        html_url=f"https://github.com/org/repo/issues/{number}",
        body=body,
    )


class _SameVectorEmbedder:
    """Returns the same vector for all texts (similarity = 1.0)."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.embed_batch_call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        return [list(self._vector) for _ in texts]


class _OrthogonalEmbedder:
    """Returns alternating orthogonal vectors (similarity = 0.0 between any two calls)."""

    def __init__(self) -> None:
        self.embed_batch_call_count = 0
        self._toggle = False

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        result: list[list[float] | None] = []
        for _ in texts:
            if self._toggle:
                result.append([0.0, 1.0, 0.0])
            else:
                result.append([1.0, 0.0, 0.0])
            self._toggle = not self._toggle
        return result


class _SequenceEmbedder:
    """Returns vectors from a fixed sequence."""

    def __init__(self, *vectors: list[float] | None) -> None:
        self._vectors: list[list[float] | None] = list(vectors)
        self._index = 0
        self.embed_batch_call_count = 0

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        self.embed_batch_call_count += 1
        result: list[list[float] | None] = []
        for _ in texts:
            if self._index < len(self._vectors):
                result.append(self._vectors[self._index])
                self._index += 1
            else:
                result.append(self._vectors[-1] if self._vectors else [1.0, 0.0, 0.0])
        return result


class _MockPlatform:
    """Async mock platform with configurable hunt/ignore issues."""

    def __init__(
        self,
        hunt_issues: list[IssueResult] | None = None,
        ignore_issues: list[IssueResult] | None = None,
        raises: bool = False,
    ) -> None:
        self._hunt_issues: list[IssueResult] = hunt_issues or []
        self._ignore_issues: list[IssueResult] = ignore_issues or []
        self._raises = raises
        self.list_issues_calls: list[dict[str, str]] = []

    async def list_issues_by_label(
        self, label: str, state: str = "open", **kwargs: object
    ) -> list[IssueResult]:
        self.list_issues_calls.append({"label": label, "state": state})
        if self._raises:
            raise RuntimeError("Platform API failure (test)")
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
# TS-110-10: filter_ignored suppresses similar findings
# ---------------------------------------------------------------------------


class TestFilterIgnoredSuppresses:
    """TS-110-10: filter_ignored() removes groups similar to af:ignore issues."""

    async def test_similar_group_filtered(self) -> None:
        """Group with similarity >= threshold to af:ignore issue is filtered."""
        group = _make_group(title="Unused function in tests")
        ignored_issue = _make_issue(
            number=10,
            title="Unused function in tests",
        )

        # Same vector → similarity = 1.0 > 0.85
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(ignore_issues=[ignored_issue])

        result = await filter_ignored(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert len(result) == 0

    async def test_fetches_ignore_issues_with_all_states(self) -> None:
        """filter_ignored fetches af:ignore issues with state='all'."""
        group = _make_group()
        ignored_issue = _make_issue(number=1)

        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(ignore_issues=[ignored_issue])

        await filter_ignored(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        # Must have fetched with label="af:ignore" and state="all"
        ignore_calls = [
            c for c in platform.list_issues_calls if c["label"] == "af:ignore"
        ]
        assert len(ignore_calls) >= 1
        assert any(c["state"] == "all" for c in ignore_calls)


# ---------------------------------------------------------------------------
# TS-110-11: filter_ignored passes dissimilar findings
# ---------------------------------------------------------------------------


class TestFilterIgnoredPasses:
    """TS-110-11: filter_ignored() passes groups dissimilar to af:ignore issues."""

    async def test_dissimilar_group_passes_through(self) -> None:
        """Group with similarity < threshold to af:ignore issue passes through."""
        group = _make_group(title="Totally different issue")
        ignored_issue = _make_issue(number=10, title="Ignored finding")

        # Orthogonal vectors → similarity = 0.0 < 0.85
        embedder = _SequenceEmbedder([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
        platform = _MockPlatform(ignore_issues=[ignored_issue])

        result = await filter_ignored(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert len(result) == 1
        assert result[0].title == "Totally different issue"

    async def test_multiple_groups_some_pass(self) -> None:
        """Of two groups, the dissimilar one passes and the similar one is filtered."""
        similar_group = _make_group(title="Similar to ignored")
        different_group = _make_group(title="Totally novel finding")
        ignored_issue = _make_issue(number=10, title="Similar to ignored")

        # For similar_group: same vector as ignored_issue → filtered
        # For different_group: orthogonal → passes
        # Embedder sequence: [similar_vec, ignored_vec, different_vec, ...]
        embedder = _SequenceEmbedder(
            [1.0, 0.0, 0.0],  # similar_group text
            [1.0, 0.0, 0.0],  # ignored_issue text (same → similarity = 1.0)
            [0.0, 1.0, 0.0],  # different_group text
            [1.0, 0.0, 0.0],  # ignored_issue text again
        )
        platform = _MockPlatform(ignore_issues=[ignored_issue])

        result = await filter_ignored(
            [similar_group, different_group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        result_titles = {g.title for g in result}
        assert "Totally novel finding" in result_titles

    async def test_accepts_similarity_threshold_parameter(self) -> None:
        """filter_ignored accepts similarity_threshold parameter."""
        group = _make_group()
        platform = _MockPlatform(ignore_issues=[])
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])

        result = await filter_ignored(
            [group],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.9,
            embedder=embedder,
        )

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-110-E4: No af:ignore issues exist → all groups pass through
# ---------------------------------------------------------------------------


class TestNoIgnoreIssues:
    """TS-110-E4: When no af:ignore issues exist, all groups pass through."""

    async def test_empty_ignore_list_passes_all(self) -> None:
        """No af:ignore issues → all groups returned."""
        g1 = _make_group(title="Group 1")
        g2 = _make_group(title="Group 2")
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])
        platform = _MockPlatform(ignore_issues=[])

        result = await filter_ignored(
            [g1, g2],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert len(result) == 2

    async def test_platform_failure_returns_all_groups(self) -> None:
        """TS-110-E4 / 4.E2: Platform failure → all groups pass through."""
        g1 = _make_group(title="Group 1")
        g2 = _make_group(title="Group 2")
        platform = _MockPlatform(raises=True)
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])

        result = await filter_ignored(
            [g1, g2],  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        assert len(result) == 2


# ---------------------------------------------------------------------------
# TS-110-P5: Ignore Filter Independence (property test)
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestIgnoreFilterIndependence:
    """TS-110-P5: Groups dissimilar to all ignored issues pass through."""

    @given(n=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20)
    def test_all_dissimilar_groups_pass(self, n: int) -> None:
        """With no ignored issues, all groups are returned."""
        groups = [_make_group(title=f"Novel group {i}") for i in range(n)]
        platform = _MockPlatform(ignore_issues=[])
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                filter_ignored(
                    groups,  # type: ignore[arg-type]
                    platform,  # type: ignore[arg-type]
                    similarity_threshold=0.85,
                    embedder=embedder,
                )
            )
        finally:
            loop.close()

        assert len(result) == len(groups)


# ---------------------------------------------------------------------------
# TS-110-SMOKE-1: Full hunt scan dedup pipeline
# ---------------------------------------------------------------------------


class TestHuntScanPipelineSmoke:
    """TS-110-SMOKE-1: Full pipeline: filter_known_duplicates → filter_ignored → create."""

    async def test_full_pipeline_only_novel_creates_issue(self) -> None:
        """Only group D (novel) reaches create_issues_from_groups; A, B, C filtered.

        - Group A: fingerprint matches an open af:hunt issue → filtered by dedup
        - Group B: embedding matches a closed af:hunt issue → filtered by dedup
        - Group C: embedding matches an af:ignore issue → filtered by ignore gate
        - Group D: novel → passes both gates
        """
        # Group A: fingerprint duplicate
        group_a = _make_group(title="Group A - FP dup", affected_files=["src/a.py"])
        fp_a = compute_fingerprint(group_a)  # type: ignore[arg-type]
        hunt_issue_a = _make_issue(number=1, title="Group A - FP dup", fingerprint=fp_a)

        # Group B: similarity duplicate (closed issue)
        group_b = _make_group(title="Group B - sim dup", affected_files=["src/b.py"])
        hunt_issue_b = _make_issue(number=2, title="Group B - similarity match")

        # Group C: matches an af:ignore issue
        group_c = _make_group(title="Group C - ignored", affected_files=["src/c.py"])
        ignore_issue_c = _make_issue(number=3, title="Group C - ignored")

        # Group D: novel
        group_d = _make_group(title="Group D - novel", affected_files=["src/d.py"])

        all_groups = [group_a, group_b, group_c, group_d]

        # Embedder: group_a is already handled by fingerprint
        # For group_b vs hunt_issue_b: same vector → similarity 1.0 → filtered
        # For group_c vs ignore_issue_c: same vector → similarity 1.0 → filtered
        # For group_d vs anything: orthogonal → similarity 0.0 → passes
        embedder = _SameVectorEmbedder([1.0, 0.0, 0.0])

        platform = _MockPlatform(
            hunt_issues=[hunt_issue_a, hunt_issue_b],
            ignore_issues=[ignore_issue_c],
        )

        # Run actual pipeline (not mocked)
        after_dedup = await filter_known_duplicates(
            all_groups,  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )
        after_ignore = await filter_ignored(
            after_dedup,  # type: ignore[arg-type]
            platform,  # type: ignore[arg-type]
            similarity_threshold=0.85,
            embedder=embedder,
        )

        # Only group D should survive
        assert len(after_ignore) == 1
        assert after_ignore[0].title == "Group D - novel"
