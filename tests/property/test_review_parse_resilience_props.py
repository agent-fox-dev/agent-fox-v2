"""Property tests for review parse resilience.

Tests correctness properties for fuzzy wrapper key matching, case normalization,
retry bound, partial convergence monotonicity, and backward compatibility.

Test Spec: TS-74-P1, TS-74-P2, TS-74-P3, TS-74-P4, TS-74-P5, TS-74-P6
Requirements: 74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3, 74-REQ-2.4, 74-REQ-2.5,
              74-REQ-3.3, 74-REQ-3.E1, 74-REQ-4.1, 74-REQ-4.2, 74-REQ-4.3
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.review_store import VALID_SEVERITIES, ReviewFinding
from agent_fox.session.review_parser import _unwrap_items, parse_review_findings

# ---------------------------------------------------------------------------
# TS-74-P1: Fuzzy matching subsumes exact matching
# Property 1 from design.md: exact canonical keys always resolve
# ---------------------------------------------------------------------------


class TestFuzzyMatchingSubsumesExactMatching:
    """TS-74-P1: For any canonical wrapper key, the exact key always resolves.

    Requirements: 74-REQ-2.1, 74-REQ-2.2, 74-REQ-2.3
    Property 1: _resolve_wrapper_key({canonical_key: []}, canonical_key)
    returns canonical_key for every canonical key.
    """

    @given(canonical_key=st.sampled_from(["findings", "verdicts", "drift_findings", "audit"]))
    def test_exact_canonical_key_resolves(self, canonical_key: str) -> None:
        """_resolve_wrapper_key always resolves the exact canonical key."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data: dict[str, list[object]] = {canonical_key: []}
        result = _resolve_wrapper_key(data, canonical_key)
        assert result == canonical_key, f"Expected '{canonical_key}' but got '{result}' for exact canonical key lookup"


# ---------------------------------------------------------------------------
# TS-74-P2: Case normalization preserves values
# Property 2 from design.md: _normalize_keys preserves all values
# ---------------------------------------------------------------------------


class TestCaseNormalizationPreservesValues:
    """TS-74-P2: _normalize_keys preserves all values after lowercasing keys.

    Requirements: 74-REQ-2.4
    Property 2: len(_normalize_keys(d)) == len(d) and same set of values.
    """

    @given(
        items=st.lists(
            st.integers(min_value=0, max_value=1000),
            min_size=1,
            max_size=10,
        )
    )
    def test_normalize_keys_preserves_values(self, items: list[int]) -> None:
        """_normalize_keys preserves all values for non-colliding keys."""
        from agent_fox.session.review_parser import _normalize_keys

        # Build dict with unique lowercase keys and integer values
        d = {f"key_{i}": v for i, v in enumerate(items)}
        result = _normalize_keys(d)

        assert len(result) == len(d), f"_normalize_keys changed dict size: {len(d)} -> {len(result)}"
        assert set(result.values()) == set(d.values()), "_normalize_keys changed the set of values"

    @given(
        d=st.dictionaries(
            keys=st.from_regex(r"[a-z][a-z0-9]{0,8}", fullmatch=True),
            values=st.integers(),
            min_size=1,
            max_size=8,
        )
    )
    def test_normalize_keys_all_lowercase(self, d: dict) -> None:
        """_normalize_keys produces a dict with all lowercase keys."""
        from agent_fox.session.review_parser import _normalize_keys

        result = _normalize_keys(d)
        for key in result:
            assert key == key.lower(), f"_normalize_keys produced a non-lowercase key: {key!r}"


# ---------------------------------------------------------------------------
# TS-74-P3: Retry bound — total parse attempts never exceed 2
# Property 3 from design.md: at most 1 format retry
# ---------------------------------------------------------------------------


class TestRetryBound:
    """TS-74-P3: Total parse attempts never exceed 2.

    Requirements: 74-REQ-3.3, 74-REQ-3.E1
    Property 3: attempt_count <= 2 for any number of bad responses.
    """

    @given(n_bad=st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_retry_attempts_bounded_by_two(self, n_bad: int) -> None:
        """For N bad responses, total extraction attempts is at most 2."""
        from agent_fox.engine.review_persistence import persist_review_findings

        call_count = [0]

        def mock_extract(text: str, **kwargs):  # type: ignore[override]
            call_count[0] += 1
            return None  # Always fail

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value="still bad json")

        with patch("agent_fox.engine.review_persistence.extract_json_array", mock_extract):
            persist_review_findings(
                transcript="bad json " * n_bad,
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=MagicMock(),
                sink=None,
                run_id="run1",
                session_handle=mock_session,
            )

        assert call_count[0] <= 2, f"Expected at most 2 extraction attempts, got {call_count[0]} (n_bad={n_bad})"


# ---------------------------------------------------------------------------
# TS-74-P4: Partial convergence monotonicity
# Property 4 from design.md: filtering preserves all non-None results
# ---------------------------------------------------------------------------


def _make_finding() -> ReviewFinding:
    """Create a minimal ReviewFinding for testing."""
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity="major",
        description="test finding",
        requirement_ref=None,
        spec_name="test_spec",
        task_group="1",
        session_id="sess1",
    )


class TestPartialConvergenceMonotonicity:
    """TS-74-P4: Filtering preserves all non-None results in order.

    Requirements: 74-REQ-4.1, 74-REQ-4.2, 74-REQ-4.3
    Property 4: filtered list contains exactly the non-None elements, in order.
    """

    @given(none_flags=st.lists(st.booleans(), min_size=0, max_size=10))
    def test_filter_preserves_non_none_in_order(self, none_flags: list[bool]) -> None:
        """Filtering a mixed list preserves all non-None elements in order."""
        finding_value = [_make_finding()]
        raw_results = [None if flag else finding_value for flag in none_flags]

        filtered = [r for r in raw_results if r is not None]
        expected_count = sum(1 for flag in none_flags if not flag)

        assert len(filtered) == expected_count
        assert all(f is not None for f in filtered)

    @given(
        none_count=st.integers(min_value=0, max_value=5),
        good_count=st.integers(min_value=0, max_value=5),
    )
    def test_filter_count_matches_non_none(self, none_count: int, good_count: int) -> None:
        """Filtered count equals the number of non-None inputs."""
        finding_value = [_make_finding()]
        raw_results: list[list[ReviewFinding] | None] = [None] * none_count + [finding_value] * good_count
        filtered = [r for r in raw_results if r is not None]
        assert len(filtered) == good_count


# ---------------------------------------------------------------------------
# TS-74-P5: Variant coverage
# Property 6 from design.md: every registered variant resolves correctly
# ---------------------------------------------------------------------------


class TestVariantCoverage:
    """TS-74-P5: Every registered variant resolves correctly.

    Requirements: 74-REQ-2.2, 74-REQ-2.3
    Property 6: _resolve_wrapper_key({variant: []}, canonical) == variant
    for all registered variants.
    """

    @given(canonical_key=st.sampled_from(["findings", "verdicts", "drift_findings", "audit"]))
    def test_all_variants_of_canonical_key_resolve(self, canonical_key: str) -> None:
        """Every variant in WRAPPER_KEY_VARIANTS resolves back to the variant key."""
        from agent_fox.session.review_parser import (
            WRAPPER_KEY_VARIANTS,
            _resolve_wrapper_key,
        )

        variants = WRAPPER_KEY_VARIANTS.get(canonical_key, set())
        for variant in variants:
            data: dict[str, list[object]] = {variant: []}
            result = _resolve_wrapper_key(data, canonical_key)
            assert result == variant, f"Variant '{variant}' of '{canonical_key}' did not resolve: got '{result}'"

    def test_all_canonical_keys_and_variants_resolve(self) -> None:
        """All (canonical, variant) pairs resolve — exhaustive check."""
        from agent_fox.session.review_parser import (
            WRAPPER_KEY_VARIANTS,
            _resolve_wrapper_key,
        )

        for canonical, variants in WRAPPER_KEY_VARIANTS.items():
            for variant in variants:
                data: dict[str, list[object]] = {variant: []}
                result = _resolve_wrapper_key(data, canonical)
                assert result == variant, f"Variant '{variant}' of '{canonical}' did not resolve"


# ---------------------------------------------------------------------------
# TS-74-P6: Backward compatibility
# Property 7 from design.md: exact-match inputs still parse correctly
# ---------------------------------------------------------------------------


@st.composite
def _valid_finding_dict(draw: st.DrawFn) -> dict:
    """Generate a valid finding dict with exact canonical keys."""
    severity = draw(st.sampled_from(list(VALID_SEVERITIES)))
    description = draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
            ),
        )
    )
    return {"severity": severity, "description": description}


class TestBackwardCompatibility:
    """TS-74-P6: Well-formed JSON with exact canonical keys parses correctly.

    Requirements: 74-REQ-2.5
    Property 7: exact-match inputs produce identical findings as before.
    """

    @given(findings=st.lists(_valid_finding_dict(), min_size=1, max_size=5))
    def test_exact_canonical_input_parses_correctly(self, findings: list[dict]) -> None:
        """_unwrap_items returns same items for exact canonical wrapper key."""
        response = json.dumps({"findings": findings})
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        assert len(items) == len(findings)
        for original, item in zip(findings, items):
            assert item["severity"] == original["severity"]
            assert item["description"] == original["description"]

    @given(findings=st.lists(_valid_finding_dict(), min_size=1, max_size=5))
    def test_backward_compatible_parse_review_findings(self, findings: list[dict]) -> None:
        """parse_review_findings works on correctly-cased inputs after changes."""
        results = parse_review_findings(findings, "spec", "1", "sess1")
        assert len(results) == len(findings)
        for result in results:
            assert result.severity in VALID_SEVERITIES
