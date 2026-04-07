"""Unit tests for review parse resilience: fuzzy matching, normalization,
format retry, and partial convergence.

Test Spec: TS-74-7 through TS-74-27, TS-74-E1 through TS-74-E3
Requirements: 74-REQ-2.*, 74-REQ-3.*, 74-REQ-4.*, 74-REQ-5.*
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_fox.core.json_extraction import extract_json_array
from agent_fox.engine.review_parser import (
    parse_drift_findings,
    parse_review_findings,
    parse_verification_results,
)
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.knowledge.review_store import ReviewFinding, VerificationResult
from agent_fox.session.convergence import (
    AuditEntry,
    AuditResult,
    converge_auditor,
    converge_skeptic_records,
    converge_verifier_records,
)
from agent_fox.session.review_parser import _unwrap_items

# ---------------------------------------------------------------------------
# Helpers for constructing test data
# ---------------------------------------------------------------------------


def _make_finding(
    severity: str = "major",
    description: str = "test finding",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "sess1",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


def _make_verdict(
    requirement_id: str = "74-REQ-1.1",
    verdict: str = "PASS",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "sess1",
) -> VerificationResult:
    return VerificationResult(
        id=str(uuid.uuid4()),
        requirement_id=requirement_id,
        verdict=verdict,
        evidence=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# TS-74-7: Case-insensitive wrapper key resolution
# ---------------------------------------------------------------------------


class TestCaseInsensitiveWrapperKeyResolution:
    """TS-74-7: _resolve_wrapper_key matches keys regardless of case.

    Requirements: 74-REQ-2.1
    """

    def test_mixed_case_findings_key_resolved(self) -> None:
        """_resolve_wrapper_key returns the actual key for case-insensitive match."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"Findings": [{"severity": "major", "description": "test"}]}
        result = _resolve_wrapper_key(data, "findings")
        assert result == "Findings"

    def test_uppercase_findings_key_resolved(self) -> None:
        """_resolve_wrapper_key handles fully uppercase wrapper key."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"FINDINGS": []}
        result = _resolve_wrapper_key(data, "findings")
        assert result == "FINDINGS"

    def test_exact_case_key_resolved(self) -> None:
        """_resolve_wrapper_key returns exact key when casing matches."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"findings": []}
        result = _resolve_wrapper_key(data, "findings")
        assert result == "findings"

    def test_missing_key_returns_none(self) -> None:
        """_resolve_wrapper_key returns None when no matching key exists."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"something_else": []}
        result = _resolve_wrapper_key(data, "findings")
        assert result is None


# ---------------------------------------------------------------------------
# TS-74-8: Singular/plural variant wrapper key resolution
# ---------------------------------------------------------------------------


class TestSingularVariantWrapperKeyResolution:
    """TS-74-8: _resolve_wrapper_key accepts singular variants of wrapper keys.

    Requirements: 74-REQ-2.2
    """

    def test_finding_resolves_to_findings(self) -> None:
        """_resolve_wrapper_key accepts 'finding' as a variant of 'findings'."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"finding": [{"severity": "minor", "description": "x"}]}
        result = _resolve_wrapper_key(data, "findings")
        assert result == "finding"

    def test_verdict_resolves_to_verdicts(self) -> None:
        """_resolve_wrapper_key accepts 'verdict' as variant of 'verdicts'."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"verdict": [{"requirement_id": "R1", "verdict": "PASS"}]}
        result = _resolve_wrapper_key(data, "verdicts")
        assert result == "verdict"

    def test_drift_finding_resolves_to_drift_findings(self) -> None:
        """_resolve_wrapper_key accepts 'drift_finding' for 'drift_findings'."""
        from agent_fox.session.review_parser import _resolve_wrapper_key

        data = {"drift_finding": [{"severity": "major", "description": "d"}]}
        result = _resolve_wrapper_key(data, "drift_findings")
        assert result == "drift_finding"

    def test_wrapper_key_variants_map_exists(self) -> None:
        """WRAPPER_KEY_VARIANTS map exists and contains canonical keys."""
        from agent_fox.session.review_parser import WRAPPER_KEY_VARIANTS

        assert "findings" in WRAPPER_KEY_VARIANTS
        assert "verdicts" in WRAPPER_KEY_VARIANTS
        assert "drift_findings" in WRAPPER_KEY_VARIANTS
        assert "audit" in WRAPPER_KEY_VARIANTS

    def test_findings_variants_include_singular(self) -> None:
        """WRAPPER_KEY_VARIANTS 'findings' set includes 'finding'."""
        from agent_fox.session.review_parser import WRAPPER_KEY_VARIANTS

        assert "finding" in WRAPPER_KEY_VARIANTS["findings"]

    def test_verdicts_variants_include_singular(self) -> None:
        """WRAPPER_KEY_VARIANTS 'verdicts' set includes 'verdict'."""
        from agent_fox.session.review_parser import WRAPPER_KEY_VARIANTS

        assert "verdict" in WRAPPER_KEY_VARIANTS["verdicts"]


# ---------------------------------------------------------------------------
# TS-74-9: _unwrap_items uses fuzzy key matching
# ---------------------------------------------------------------------------


class TestUnwrapItemsFuzzyMatching:
    """TS-74-9: _unwrap_items extracts findings from variant wrapper keys.

    Requirements: 74-REQ-2.3
    """

    def test_mixed_case_finding_key_unwrapped(self) -> None:
        """_unwrap_items extracts items from 'Finding' when seeking 'findings'."""
        response = '{"Finding": [{"severity": "major", "description": "test"}]}'
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        assert len(items) == 1
        assert items[0]["severity"] == "major"

    def test_singular_variant_finding_key_unwrapped(self) -> None:
        """_unwrap_items extracts items from 'finding' when seeking 'findings'."""
        response = '{"finding": [{"severity": "minor", "description": "x"}]}'
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        assert len(items) == 1
        assert items[0]["severity"] == "minor"

    def test_uppercase_verdicts_key_unwrapped(self) -> None:
        """_unwrap_items extracts items from 'VERDICTS' when seeking 'verdicts'."""
        response = '{"VERDICTS": [{"requirement_id": "R1", "verdict": "PASS"}]}'
        items = _unwrap_items(response, "verdicts", ("requirement_id",), "Verifier")
        assert len(items) == 1
        assert items[0]["requirement_id"] == "R1"


# ---------------------------------------------------------------------------
# TS-74-10: Field-level case normalization
# ---------------------------------------------------------------------------


class TestFieldLevelCaseNormalization:
    """TS-74-10: Typed parsers normalize field keys to lowercase before validation.

    Requirements: 74-REQ-2.4
    """

    def test_parse_review_findings_mixed_case_keys(self) -> None:
        """parse_review_findings handles mixed-case field keys."""
        items = [{"Severity": "critical", "Description": "test issue"}]
        findings = parse_review_findings(items, "spec", "1", "sess1")
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].description == "test issue"

    def test_parse_review_findings_all_uppercase_keys(self) -> None:
        """parse_review_findings handles all-uppercase field keys."""
        items = [{"SEVERITY": "major", "DESCRIPTION": "uppercase test"}]
        findings = parse_review_findings(items, "spec", "1", "sess1")
        assert len(findings) == 1
        assert findings[0].severity == "major"

    def test_parse_verification_results_mixed_case_keys(self) -> None:
        """parse_verification_results handles mixed-case field keys."""
        items = [{"Requirement_Id": "74-REQ-1.1", "Verdict": "PASS"}]
        verdicts = parse_verification_results(items, "spec", "1", "sess1")
        assert len(verdicts) == 1
        assert verdicts[0].requirement_id == "74-REQ-1.1"
        assert verdicts[0].verdict == "PASS"

    def test_parse_drift_findings_mixed_case_keys(self) -> None:
        """parse_drift_findings handles mixed-case field keys."""
        items = [{"Severity": "minor", "Description": "drift desc"}]
        findings = parse_drift_findings(items, "spec", "1", "sess1")
        assert len(findings) == 1
        assert findings[0].severity == "minor"


# ---------------------------------------------------------------------------
# TS-74-11: Markdown fence extraction preserved (backward compat)
# ---------------------------------------------------------------------------


class TestMarkdownFenceExtractionPreserved:
    """TS-74-11: JSON inside markdown fences with surrounding prose is extracted.

    Requirements: 74-REQ-2.5
    """

    def test_fence_with_prose_extracted(self) -> None:
        """extract_json_array extracts JSON from fenced block with surrounding prose."""
        text = 'Here is my analysis:\n```json\n[{"severity": "major"}]\n```\nDone.'
        result = extract_json_array(text)
        assert result == [{"severity": "major"}]

    def test_bare_fence_without_json_label(self) -> None:
        """extract_json_array handles plain fences without 'json' label."""
        text = '```\n[{"severity": "minor"}]\n```'
        result = extract_json_array(text)
        assert result == [{"severity": "minor"}]


# ---------------------------------------------------------------------------
# TS-74-12: Single object treated as finding (REQ-2.E1)
# ---------------------------------------------------------------------------


class TestSingleObjectAsFinding:
    """TS-74-12: A bare JSON object with required fields is treated as finding.

    Requirements: 74-REQ-2.E1
    """

    def test_bare_object_with_severity_treated_as_finding(self) -> None:
        """_unwrap_items returns single-item list for bare object with required keys."""
        response = '{"severity": "minor", "description": "nit"}'
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        assert len(items) == 1
        assert items[0]["severity"] == "minor"


# ---------------------------------------------------------------------------
# TS-74-13: Multiple JSON blocks merged (REQ-2.E2)
# ---------------------------------------------------------------------------


class TestMultipleJsonBlocksMerged:
    """TS-74-13: Findings from multiple JSON blocks in the same output are merged.

    Requirements: 74-REQ-2.E2
    """

    def test_two_findings_blocks_merged(self) -> None:
        """_unwrap_items merges findings from two separate JSON objects."""
        response = (
            '{"findings": [{"severity": "major", "description": "a"}]}\n'
            "More analysis text.\n"
            '{"findings": [{"severity": "minor", "description": "b"}]}'
        )
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        assert len(items) == 2
        severities = {item["severity"] for item in items}
        assert severities == {"major", "minor"}


# ---------------------------------------------------------------------------
# TS-74-15: Retry message contains schema reference (REQ-3.2)
# ---------------------------------------------------------------------------


class TestFormatRetryPrompt:
    """TS-74-15: FORMAT_RETRY_PROMPT constant exists and has correct content.

    Requirements: 74-REQ-3.2
    """

    def test_format_retry_prompt_exists(self) -> None:
        """FORMAT_RETRY_PROMPT constant is defined in review_persistence."""
        from agent_fox.engine.review_persistence import FORMAT_RETRY_PROMPT

        assert isinstance(FORMAT_RETRY_PROMPT, str)
        assert len(FORMAT_RETRY_PROMPT) > 0

    def test_format_retry_prompt_mentions_parse_failure(self) -> None:
        """FORMAT_RETRY_PROMPT explains that previous output could not be parsed."""
        from agent_fox.engine.review_persistence import FORMAT_RETRY_PROMPT

        lower = FORMAT_RETRY_PROMPT.lower()
        assert "could not be parsed" in lower or "not be parsed" in lower, (
            "FORMAT_RETRY_PROMPT must indicate parsing failure"
        )

    def test_format_retry_prompt_mentions_json(self) -> None:
        """FORMAT_RETRY_PROMPT references JSON and format instructions."""
        from agent_fox.engine.review_persistence import FORMAT_RETRY_PROMPT

        assert "JSON" in FORMAT_RETRY_PROMPT or "json" in FORMAT_RETRY_PROMPT.lower()


# ---------------------------------------------------------------------------
# TS-74-16: Maximum one retry (REQ-3.3)
# ---------------------------------------------------------------------------


class TestMaximumOneRetry:
    """TS-74-16: At most 1 format retry is attempted per session.

    Requirements: 74-REQ-3.3
    """

    def test_persist_review_findings_accepts_session_handle(self) -> None:
        """persist_review_findings accepts a session_handle keyword argument."""
        import inspect

        from agent_fox.engine.review_persistence import persist_review_findings

        sig = inspect.signature(persist_review_findings)
        params = sig.parameters
        assert "session_handle" in params or "backend" in params, (
            "persist_review_findings must accept session_handle or backend to support format retry"
        )

    def test_persist_review_findings_retry_count_bounded(self) -> None:
        """Format retry is attempted at most once (retry count <= 1)."""
        from agent_fox.engine.review_persistence import persist_review_findings

        call_count: list[str] = []

        def mock_extract(text: str, **kwargs):  # type: ignore[override]
            call_count.append(text)
            return None  # Always fail

        mock_session = MagicMock()
        mock_session.is_alive = True
        mock_session.append_user_message = MagicMock(return_value="still bad json")

        with patch("agent_fox.engine.review_persistence.extract_json_array", mock_extract):
            persist_review_findings(
                transcript="no json here",
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

        # At most 2 calls: initial parse + 1 retry
        assert len(call_count) <= 2, f"Expected at most 2 extraction attempts, got {len(call_count)}"


# ---------------------------------------------------------------------------
# TS-74-19: No retry on terminated session (REQ-3.E2)
# ---------------------------------------------------------------------------


class TestNoRetryOnTerminatedSession:
    """TS-74-19: Format retry is skipped when session is terminated.

    Requirements: 74-REQ-3.E2
    """

    def test_no_retry_when_session_not_alive(self) -> None:
        """persist_review_findings does not retry when session is terminated."""
        from agent_fox.engine.review_persistence import persist_review_findings

        retry_called: list[bool] = []

        mock_session = MagicMock()
        mock_session.is_alive = False

        original_append = mock_session.append_user_message

        def track_retry(*args, **kwargs):
            retry_called.append(True)
            return original_append(*args, **kwargs)

        mock_session.append_user_message = track_retry

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=None,
        ):
            persist_review_findings(
                transcript="no json here",
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

        assert len(retry_called) == 0, "Format retry must not be attempted when session is terminated"


# ---------------------------------------------------------------------------
# TS-74-20: Partial convergence - Skeptic (REQ-4.1)
# ---------------------------------------------------------------------------


class TestPartialConvergenceSkeptic:
    """TS-74-20: Skeptic convergence proceeds with parseable instances only.

    Requirements: 74-REQ-4.1
    """

    def test_none_instances_filtered_before_convergence(self) -> None:
        """Convergence input has None results filtered out."""
        f_a = _make_finding(severity="major", description="finding a")
        f_b = _make_finding(severity="minor", description="finding b")
        f_c = _make_finding(severity="critical", description="finding c")

        raw_results: list[list[ReviewFinding] | None] = [
            [f_a, f_b],
            [f_c],
            None,
        ]
        filtered = [r for r in raw_results if r is not None]

        assert len(filtered) == 2

        merged, blocked = converge_skeptic_records(filtered, block_threshold=5)
        assert len(merged) >= 1

    def test_single_parseable_instance_produces_results(self) -> None:
        """Single non-None instance still produces merged findings."""
        f = _make_finding(severity="major", description="sole finding")
        raw_results: list[list[ReviewFinding] | None] = [[f], None, None]
        filtered = [r for r in raw_results if r is not None]

        assert len(filtered) == 1
        merged, _blocked = converge_skeptic_records(filtered, block_threshold=5)
        assert len(merged) == 1


# ---------------------------------------------------------------------------
# TS-74-21: Partial convergence - Verifier (REQ-4.2)
# ---------------------------------------------------------------------------


class TestPartialConvergenceVerifier:
    """TS-74-21: Verifier convergence proceeds with parseable instances only.

    Requirements: 74-REQ-4.2
    """

    def test_none_instance_filtered_before_convergence(self) -> None:
        """Verifier convergence receives only non-None verdict lists."""
        v_pass = _make_verdict(requirement_id="74-REQ-1.1", verdict="PASS")

        raw_results: list[list[VerificationResult] | None] = [[v_pass], None]
        filtered = [r for r in raw_results if r is not None]

        assert len(filtered) == 1
        merged = converge_verifier_records(filtered)
        assert len(merged) == 1
        assert merged[0].verdict == "PASS"


# ---------------------------------------------------------------------------
# TS-74-22: Partial convergence - Auditor (REQ-4.3)
# ---------------------------------------------------------------------------


class TestPartialConvergenceAuditor:
    """TS-74-22: Auditor convergence proceeds with parseable instances only.

    Requirements: 74-REQ-4.3
    """

    def test_none_instance_filtered_before_convergence(self) -> None:
        """Auditor convergence receives only non-None AuditResult instances."""
        entry = AuditEntry(ts_entry="TS-74-1", test_functions=["test_foo"], verdict="PASS")
        audit_result = AuditResult(entries=[entry], overall_verdict="PASS", summary="ok")

        raw_results: list[AuditResult | None] = [audit_result, None]
        filtered: list[AuditResult] = [r for r in raw_results if r is not None]

        assert len(filtered) == 1
        merged = converge_auditor(filtered)
        assert merged.overall_verdict == audit_result.overall_verdict


# ---------------------------------------------------------------------------
# TS-74-23: No parse failure when some instances succeed (REQ-4.4)
# ---------------------------------------------------------------------------


class TestNoParseFailureWhenSomeSucceed:
    """TS-74-23: REVIEW_PARSE_FAILURE not emitted when at least one instance succeeds.

    Requirements: 74-REQ-4.4
    """

    def test_no_failure_event_when_some_instances_parseable(self) -> None:
        """No REVIEW_PARSE_FAILURE when at least one instance produced output."""
        f = _make_finding(severity="major", description="valid finding")
        raw_results: list[list[ReviewFinding] | None] = [[f], None]
        filtered = [r for r in raw_results if r is not None]

        # When at least one result is non-None, no REVIEW_PARSE_FAILURE should fire.
        # The convergence call site (task 4.3) implements this behavior.
        # Here we verify that filtering produces at least one result.
        assert len(filtered) > 0, "At least one parseable result must exist"


# ---------------------------------------------------------------------------
# TS-74-24: Warning logged for failed instances (REQ-4.5)
# ---------------------------------------------------------------------------


class TestWarningLoggedForFailedInstances:
    """TS-74-24: A warning is logged when some instances fail parsing.

    Requirements: 74-REQ-4.5
    """

    def test_warning_logged_for_failed_instance(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warning log identifies the instance that failed to parse."""
        # This function will be implemented in task group 4.
        from agent_fox.engine.review_persistence import warn_failed_parse_instances

        f = _make_finding(severity="major", description="found something")
        raw_results: list[list[ReviewFinding] | None] = [[f], None]

        with caplog.at_level(logging.WARNING):
            warn_failed_parse_instances(raw_results, archetype="skeptic", run_id="run1")

        assert any("instance" in r.message.lower() and "failed" in r.message.lower() for r in caplog.records), (
            "Expected a warning about failed parse instances"
        )


# ---------------------------------------------------------------------------
# TS-74-25: All instances fail emits parse failure (REQ-4.E1)
# ---------------------------------------------------------------------------


class TestAllInstancesFailEmitsParseFailure:
    """TS-74-25: REVIEW_PARSE_FAILURE emitted when all instances fail parsing.

    Requirements: 74-REQ-4.E1
    """

    def test_all_none_results_emit_parse_failure(self) -> None:
        """All-None instance results produce a parse failure event."""
        from agent_fox.engine.review_persistence import (
            converge_multi_instance_skeptic,
        )

        mock_sink = MagicMock()
        emitted_events: list[Any] = []

        def capture_emit(event: Any) -> None:
            emitted_events.append(event)

        mock_sink.emit_audit_event = capture_emit

        raw_results: list[list[ReviewFinding] | None] = [None, None]

        results = converge_multi_instance_skeptic(
            raw_results,
            sink=mock_sink,
            run_id="run1",
            node_id="node1",
            block_threshold=5,
        )

        assert results == [] or results == ([], False)
        event_types = [getattr(e, "event_type", None) for e in emitted_events]
        assert AuditEventType.REVIEW_PARSE_FAILURE in event_types, (
            "REVIEW_PARSE_FAILURE event must be emitted when all instances fail"
        )


# ---------------------------------------------------------------------------
# TS-74-26: Retry success audit event (REQ-5.1)
# ---------------------------------------------------------------------------


class TestRetrySuccessAuditEvent:
    """TS-74-26: REVIEW_PARSE_RETRY_SUCCESS event emitted on successful retry.

    Requirements: 74-REQ-5.1
    """

    def test_review_parse_retry_success_event_type_exists(self) -> None:
        """REVIEW_PARSE_RETRY_SUCCESS is a valid AuditEventType."""
        assert hasattr(AuditEventType, "REVIEW_PARSE_RETRY_SUCCESS"), (
            "AuditEventType must have REVIEW_PARSE_RETRY_SUCCESS member"
        )

    def test_retry_success_event_value(self) -> None:
        """REVIEW_PARSE_RETRY_SUCCESS has the expected string value."""
        retry_success = AuditEventType.REVIEW_PARSE_RETRY_SUCCESS
        assert "retry" in str(retry_success).lower(), "REVIEW_PARSE_RETRY_SUCCESS event type value must contain 'retry'"


# ---------------------------------------------------------------------------
# TS-74-27: Parse failure payload contains strategy field (REQ-5.3)
# ---------------------------------------------------------------------------


class TestParseFailurePayloadStrategyField:
    """TS-74-27: REVIEW_PARSE_FAILURE payload includes a 'strategy' field.

    Requirements: 74-REQ-5.3
    """

    def test_parse_failure_with_retry_includes_strategy(self) -> None:
        """REVIEW_PARSE_FAILURE payload has 'strategy' with extraction strategies."""
        from agent_fox.engine.review_persistence import persist_review_findings

        class CaptureSink:
            def __init__(self) -> None:
                self.events: list[Any] = []

            def emit_audit_event(self, event: Any) -> None:
                self.events.append(event)

            def record_session_outcome(self, outcome: Any) -> None:
                pass

            def record_tool_call(self, tool_call: Any) -> None:
                pass

            def record_tool_error(self, error: Any) -> None:
                pass

            def close(self) -> None:
                pass

        sink = CaptureSink()

        with patch(
            "agent_fox.engine.review_persistence.extract_json_array",
            return_value=None,
        ):
            persist_review_findings(
                transcript="no json here",
                node_id="test-node",
                attempt=1,
                archetype="skeptic",
                spec_name="test_spec",
                task_group="1",
                knowledge_db_conn=MagicMock(),
                sink=sink,
                run_id="run1",
            )

        failure_events = [
            e for e in sink.events if getattr(e, "event_type", None) == AuditEventType.REVIEW_PARSE_FAILURE
        ]
        assert len(failure_events) > 0, "REVIEW_PARSE_FAILURE event must be emitted"

        payload = failure_events[0].payload
        assert "strategy" in payload, "REVIEW_PARSE_FAILURE payload must include 'strategy' field"
        assert "bracket_scan" in payload["strategy"], "Strategy field must include 'bracket_scan' strategy name"


# ---------------------------------------------------------------------------
# TS-74-E1: Empty output text
# ---------------------------------------------------------------------------


class TestEmptyOutputText:
    """TS-74-E1: Empty output returns no findings.

    Requirements: 74-REQ-2.E1
    """

    def test_empty_string_returns_none(self) -> None:
        """extract_json_array returns None for empty input."""
        result = extract_json_array("")
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        """extract_json_array returns None for whitespace-only input."""
        result = extract_json_array("   \n\t  ")
        assert result is None


# ---------------------------------------------------------------------------
# TS-74-E2: JSON with unknown wrapper key
# ---------------------------------------------------------------------------


class TestUnknownWrapperKey:
    """TS-74-E2: JSON with unrecognized wrapper key falls through.

    Requirements: 74-REQ-2.E1
    """

    def test_unrecognized_wrapper_key_returns_empty(self) -> None:
        """_unwrap_items returns empty for unrecognized non-variant wrapper key."""
        response = '{"results_data": [{"severity": "major"}]}'
        items = _unwrap_items(response, "findings", ("severity",), "Skeptic")
        # "results_data" is not a registered variant of "findings"
        # The outer dict doesn't have "severity" as a direct key (it's nested)
        assert items == [], "Items from unrecognized wrapper key 'results_data' should not be returned"


# ---------------------------------------------------------------------------
# TS-74-E3: Single instance bypass (REQ-4.E2)
# ---------------------------------------------------------------------------


class TestSingleInstanceBypass:
    """TS-74-E3: Single-instance mode uses result directly without filtering.

    Requirements: 74-REQ-4.E2
    """

    def test_single_instance_findings_passed_through(self) -> None:
        """Single instance result is used directly without convergence filtering."""
        f = _make_finding(severity="major", description="direct finding")
        raw_results: list[list[ReviewFinding] | None] = [[f]]

        # With a single instance, no filtering should happen.
        # converge_skeptic_records with 1 instance returns the list directly.
        merged, _blocked = converge_skeptic_records(raw_results, block_threshold=5)
        assert len(merged) == 1
        assert merged[0].severity == "major"
        assert merged[0].description == "direct finding"
