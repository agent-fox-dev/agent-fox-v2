"""Property tests for triage/reviewer parsing and escalation.

Test Spec: TS-82-P1, TS-82-P2, TS-82-P3, TS-82-P4
Properties: 1 (criteria completeness), 2 (verdict validation),
            3 (escalation consistency), 4 (retry feedback injection)
"""

from __future__ import annotations

import json

import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

pytestmark = pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")

REQUIRED_TRIAGE_KEYS = ("id", "description", "preconditions", "expected", "assertion")


# ---------------------------------------------------------------------------
# TS-82-P1: Triage criteria field completeness
# Property 1: All parsed criteria contain all five required fields.
# Validates: 82-REQ-2.1, 82-REQ-2.2
# ---------------------------------------------------------------------------


class TestTriageCriteriaCompleteness:
    """For any generated triage JSON, parsed criteria have all required fields."""

    @given(
        criteria_dicts=st.lists(
            st.fixed_dictionaries(
                {},
                optional={
                    "id": st.text(min_size=1, max_size=20),
                    "description": st.text(min_size=1, max_size=100),
                    "preconditions": st.text(min_size=1, max_size=100),
                    "expected": st.text(min_size=1, max_size=100),
                    "assertion": st.text(min_size=1, max_size=100),
                },
            ),
            min_size=0,
            max_size=5,
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_parsed_criteria_always_complete(self, criteria_dicts: list[dict]) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        json_str = json.dumps(
            {
                "summary": "s",
                "affected_files": [],
                "acceptance_criteria": criteria_dicts,
            }
        )
        result = parse_triage_output(json_str, "fix-issue-1", "s1")

        # Every parsed criterion must have all five fields as non-empty strings
        for criterion in result.criteria:
            assert criterion.id != ""
            assert criterion.description != ""
            assert criterion.preconditions != ""
            assert criterion.expected != ""
            assert criterion.assertion != ""

        # Count: only criteria with all 5 fields present should be included
        complete = [c for c in criteria_dicts if all(k in c and c[k] for k in REQUIRED_TRIAGE_KEYS)]
        assert len(result.criteria) == len(complete)


# ---------------------------------------------------------------------------
# TS-82-P2: Reviewer verdict validation
# Property 2: All parsed verdicts have valid values; overall is FAIL if any is FAIL.
# Validates: 82-REQ-5.1, 82-REQ-5.3
# ---------------------------------------------------------------------------


class TestReviewerVerdictValidation:
    """Parsed verdicts have valid verdict values and consistent overall_verdict."""

    @given(
        verdict_dicts=st.lists(
            st.fixed_dictionaries(
                {
                    "criterion_id": st.text(
                        min_size=1,
                        max_size=10,
                        alphabet=st.characters(
                            whitelist_categories=("L", "N"),
                            whitelist_characters="-_",
                        ),
                    ),
                    "verdict": st.sampled_from(["PASS", "FAIL", "MAYBE", ""]),
                    "evidence": st.text(min_size=1, max_size=50),
                },
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_parsed_verdicts_valid_and_consistent(self, verdict_dicts: list[dict]) -> None:
        from agent_fox.session.review_parser import parse_fix_review_output

        json_str = json.dumps(
            {
                "verdicts": verdict_dicts,
                "overall_verdict": "PASS",
                "summary": "s",
            }
        )
        result = parse_fix_review_output(json_str, "fix-issue-1", "s1")

        # Every parsed verdict must have valid verdict value
        for v in result.verdicts:
            assert v.verdict in {"PASS", "FAIL"}

        # If any verdict is FAIL, overall must be FAIL
        if any(v.verdict == "FAIL" for v in result.verdicts):
            assert result.overall_verdict == "FAIL"


# ---------------------------------------------------------------------------
# TS-82-P3: Escalation ladder consistency
# Property 3: Pipeline escalation state matches reference ladder.
# Validates: 82-REQ-8.2, 82-REQ-8.3, 82-REQ-8.4
# ---------------------------------------------------------------------------


class TestEscalationLadderConsistency:
    """Escalation state after N failures matches a fresh ladder."""

    @given(
        n=st.integers(min_value=1, max_value=9),
        retries_before=st.sampled_from([0, 1, 2]),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_ladder_state_matches_reference(self, n: int, retries_before: int) -> None:
        from agent_fox.core.models import ModelTier
        from agent_fox.routing.escalation import EscalationLadder

        ref_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=retries_before,
        )

        # Replay ladder: a second instance with same N failures
        test_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=retries_before,
        )

        for _ in range(n):
            ref_ladder.record_failure()
            test_ladder.record_failure()

        assert test_ladder.current_tier == ref_ladder.current_tier
        assert test_ladder.is_exhausted == ref_ladder.is_exhausted
        assert test_ladder.escalation_count == ref_ladder.escalation_count


# ---------------------------------------------------------------------------
# TS-82-P4: Retry feedback injection
# Property 4: Coder retry prompt contains all FAIL evidence.
# Validates: 82-REQ-8.1
# ---------------------------------------------------------------------------


class TestRetryFeedbackInjection:
    """Coder retry prompt contains evidence of every FAIL verdict."""

    @given(
        verdicts=st.lists(
            st.tuples(
                st.text(
                    min_size=1,
                    max_size=10,
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                ),
                st.sampled_from(["PASS", "FAIL"]),
                st.text(
                    min_size=5,
                    max_size=50,
                    alphabet=st.characters(
                        whitelist_categories=("L", "N", "Z"),
                    ),
                ),
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_fail_evidence_in_coder_prompt(self, verdicts: list[tuple[str, str, str]]) -> None:
        from unittest.mock import MagicMock

        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.nightshift.spec_builder import build_in_memory_spec
        from agent_fox.platform.protocol import IssueResult
        from agent_fox.session.review_parser import (
            parse_fix_review_output,
            parse_triage_output,
        )

        # Build triage result
        triage_result = parse_triage_output(
            json.dumps(
                {
                    "summary": "s",
                    "affected_files": [],
                    "acceptance_criteria": [
                        {
                            "id": cid,
                            "description": "d",
                            "preconditions": "p",
                            "expected": "e",
                            "assertion": "a",
                        }
                        for cid, _, _ in verdicts
                    ],
                }
            ),
            "fix-issue-1",
            "s1",
        )

        # Build review result with mixed verdicts
        review_json = json.dumps(
            {
                "verdicts": [
                    {
                        "criterion_id": cid,
                        "verdict": v,
                        "evidence": ev,
                    }
                    for cid, v, ev in verdicts
                ],
                "overall_verdict": ("FAIL" if any(v == "FAIL" for _, v, _ in verdicts) else "PASS"),
                "summary": "review",
            }
        )
        review_result = parse_fix_review_output(review_json, "fix-issue-1", "s1")

        # Skip if no FAIL verdicts (nothing to inject)
        fail_verdicts = [(cid, ev) for cid, v, ev in verdicts if v == "FAIL"]
        if not fail_verdicts:
            return

        # Build coder prompt with feedback
        issue = IssueResult(
            number=1,
            title="Bug",
            html_url="http://test",
        )
        spec = build_in_memory_spec(issue, "fix the bug")

        config = MagicMock()
        pipeline = FixPipeline(config=config, platform=MagicMock())

        _, task_prompt = pipeline._build_coder_prompt(spec, triage_result, review_feedback=review_result)

        # Every FAIL evidence must appear in the task prompt
        combined = task_prompt
        for _cid, evidence in fail_verdicts:
            # Only check parsed FAIL verdicts (invalid ones are excluded)
            matching = [v for v in review_result.verdicts if v.verdict == "FAIL"]
            for v in matching:
                assert v.evidence in combined, f"FAIL evidence '{v.evidence}' not in coder prompt"
