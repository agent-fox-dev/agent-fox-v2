"""Tests for triage and fix-reviewer output parsers.

Test Spec: TS-82-3, TS-82-4, TS-82-5, TS-82-8, TS-82-9,
           TS-82-E1, TS-82-E3, TS-82-E4
Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3, 82-REQ-2.E1,
              82-REQ-5.1
"""

from __future__ import annotations

import json
import logging

# ---------------------------------------------------------------------------
# TS-82-3: Parse valid triage JSON
# Requirements: 82-REQ-2.1, 82-REQ-2.2, 82-REQ-2.3
# ---------------------------------------------------------------------------


class TestParseValidTriageJSON:
    """Verify parse_triage_output correctly parses well-formed triage JSON."""

    def test_parses_all_fields(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        raw = json.dumps(
            {
                "summary": "Bug in engine loop",
                "affected_files": ["agent_fox/engine.py"],
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "Engine handles empty queue",
                        "preconditions": "Queue is empty",
                        "expected": "Engine returns without error",
                        "assertion": "Return value is None",
                    }
                ],
            }
        )
        result = parse_triage_output(raw, "fix-issue-1", "session-1")

        assert result.summary == "Bug in engine loop"
        assert result.affected_files == ["agent_fox/engine.py"]
        assert len(result.criteria) == 1

        ac = result.criteria[0]
        assert ac.id == "AC-1"
        assert ac.description == "Engine handles empty queue"
        assert ac.preconditions == "Queue is empty"
        assert ac.expected == "Engine returns without error"
        assert ac.assertion == "Return value is None"

    def test_parses_multiple_criteria(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        raw = json.dumps(
            {
                "summary": "Multiple bugs",
                "affected_files": ["a.py", "b.py"],
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "d1",
                        "preconditions": "p1",
                        "expected": "e1",
                        "assertion": "a1",
                    },
                    {
                        "id": "AC-2",
                        "description": "d2",
                        "preconditions": "p2",
                        "expected": "e2",
                        "assertion": "a2",
                    },
                ],
            }
        )
        result = parse_triage_output(raw, "fix-issue-1", "s1")
        assert len(result.criteria) == 2
        assert result.criteria[0].id == "AC-1"
        assert result.criteria[1].id == "AC-2"
        assert result.affected_files == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# TS-82-4: Parse triage JSON skips incomplete criteria
# Requirement: 82-REQ-2.2
# ---------------------------------------------------------------------------


class TestParseTriageSkipsIncomplete:
    """Verify that criteria missing required fields are excluded."""

    def test_incomplete_criterion_excluded(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        raw = json.dumps(
            {
                "summary": "Summary",
                "affected_files": [],
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "Good",
                        "preconditions": "P",
                        "expected": "E",
                        "assertion": "A",
                    },
                    {"id": "AC-2", "description": "Missing fields"},
                ],
            }
        )
        result = parse_triage_output(raw, "fix-issue-1", "s1")
        assert len(result.criteria) == 1
        assert result.criteria[0].id == "AC-1"


# ---------------------------------------------------------------------------
# TS-82-5: Parse triage output returns empty on invalid JSON
# Requirement: 82-REQ-2.E1
# ---------------------------------------------------------------------------


class TestParseTriageInvalidJSON:
    """Verify graceful fallback on unparseable triage output."""

    def test_returns_empty_on_prose(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        result = parse_triage_output(
            "This is not JSON at all, just some markdown text",
            "fix-issue-1",
            "s1",
        )
        assert result.summary == ""
        assert result.criteria == []
        assert result.affected_files == []

    def test_returns_empty_on_garbage(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        result = parse_triage_output("not json", "fix-issue-1", "s1")
        assert result.summary == ""
        assert result.criteria == []


# ---------------------------------------------------------------------------
# TS-82-8: Parse valid fix reviewer JSON
# Requirement: 82-REQ-5.1
# ---------------------------------------------------------------------------


class TestParseValidFixReviewJSON:
    """Verify parse_fix_review_output correctly parses well-formed JSON."""

    def test_parses_all_fields(self) -> None:
        from agent_fox.session.review_parser import parse_fix_review_output

        raw = json.dumps(
            {
                "verdicts": [
                    {
                        "criterion_id": "AC-1",
                        "verdict": "PASS",
                        "evidence": "Test passes",
                    },
                    {
                        "criterion_id": "AC-2",
                        "verdict": "FAIL",
                        "evidence": "Function returns wrong value",
                    },
                ],
                "overall_verdict": "FAIL",
                "summary": "1 of 2 criteria failed",
            }
        )
        result = parse_fix_review_output(raw, "fix-issue-1", "s1")

        assert len(result.verdicts) == 2
        assert result.verdicts[0].criterion_id == "AC-1"
        assert result.verdicts[0].verdict == "PASS"
        assert result.verdicts[0].evidence == "Test passes"
        assert result.verdicts[1].criterion_id == "AC-2"
        assert result.verdicts[1].verdict == "FAIL"
        assert result.verdicts[1].evidence == "Function returns wrong value"
        assert result.overall_verdict == "FAIL"
        assert result.summary == "1 of 2 criteria failed"
        assert result.is_parse_failure is False


# ---------------------------------------------------------------------------
# TS-82-9: Parse reviewer output defaults to FAIL on invalid JSON
# Requirement: 82-REQ-5.1
# ---------------------------------------------------------------------------


class TestParseFixReviewInvalidJSON:
    """Verify that unparseable reviewer output is treated as FAIL."""

    def test_returns_fail_on_prose(self) -> None:
        from agent_fox.session.review_parser import parse_fix_review_output

        result = parse_fix_review_output("Some markdown prose, no JSON", "fix-issue-1", "s1")
        assert result.overall_verdict == "FAIL"
        assert result.verdicts == []
        assert result.is_parse_failure is True

    def test_returns_fail_on_garbage(self) -> None:
        from agent_fox.session.review_parser import parse_fix_review_output

        result = parse_fix_review_output("no json", "fix-issue-1", "s1")
        assert result.overall_verdict == "FAIL"
        assert result.verdicts == []
        assert result.is_parse_failure is True


# ---------------------------------------------------------------------------
# TS-82-E1: Triage output with empty criteria array
# Requirement: 82-REQ-2.E1
# ---------------------------------------------------------------------------


class TestTriageEmptyCriteria:
    """Verify that an empty acceptance_criteria array produces empty result."""

    def test_empty_array_returns_empty_criteria(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        raw = json.dumps(
            {
                "summary": "unclear",
                "affected_files": [],
                "acceptance_criteria": [],
            }
        )
        result = parse_triage_output(raw, "fix-issue-1", "s1")
        assert result.criteria == []
        assert result.summary == "unclear"


# ---------------------------------------------------------------------------
# TS-82-E3: Triage JSON wrapped in markdown fences
# Requirement: 82-REQ-2.1
# ---------------------------------------------------------------------------


class TestTriageMarkdownFences:
    """Verify triage JSON inside markdown code fences is parsed."""

    def test_fenced_json_parsed(self) -> None:
        from agent_fox.session.review_parser import parse_triage_output

        inner = json.dumps(
            {
                "summary": "found it",
                "affected_files": [],
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "d",
                        "preconditions": "p",
                        "expected": "e",
                        "assertion": "a",
                    }
                ],
            }
        )
        fenced = f"Here is my analysis:\n```json\n{inner}\n```\n"
        result = parse_triage_output(fenced, "fix-issue-1", "s1")
        assert len(result.criteria) == 1
        assert result.criteria[0].id == "AC-1"


# ---------------------------------------------------------------------------
# TS-82-E4: Reviewer JSON with unknown verdict value
# Requirement: 82-REQ-5.1
# ---------------------------------------------------------------------------


class TestReviewerUnknownVerdict:
    """Verify verdicts with invalid values are excluded."""

    def test_invalid_verdict_excluded(self) -> None:
        from agent_fox.session.review_parser import parse_fix_review_output

        raw = json.dumps(
            {
                "verdicts": [
                    {
                        "criterion_id": "AC-1",
                        "verdict": "MAYBE",
                        "evidence": "unsure",
                    },
                    {
                        "criterion_id": "AC-2",
                        "verdict": "PASS",
                        "evidence": "ok",
                    },
                ],
                "overall_verdict": "PASS",
                "summary": "mixed",
            }
        )
        result = parse_fix_review_output(raw, "fix-issue-1", "s1")
        assert len(result.verdicts) == 1
        assert result.verdicts[0].criterion_id == "AC-2"


# ---------------------------------------------------------------------------
# Verbose dump: parse failures write to .agent-fox/ when --verbose is active
# ---------------------------------------------------------------------------


class TestParseTriageVerboseDump:
    """Verify raw triage response is written to .agent-fox/ on parse failure in verbose mode."""

    def test_dump_written_when_debug_logging_enabled(self, tmp_path, monkeypatch, caplog) -> None:
        """A file is created in .agent-fox/ when the logger is at DEBUG level."""
        from agent_fox.session.review_parser import parse_triage_output

        monkeypatch.chdir(tmp_path)
        with caplog.at_level(logging.DEBUG, logger="agent_fox.session.review_parser"):
            parse_triage_output("not json at all", "fix-issue-1", "fix-issue-1:0:triage")

        dump_dir = tmp_path / ".agent-fox"
        assert dump_dir.is_dir(), "Expected .agent-fox/ directory to be created"
        files = list(dump_dir.glob("parse_failure_triage_*.txt"))
        assert len(files) == 1, f"Expected exactly one dump file, got {files}"
        assert files[0].read_text(encoding="utf-8") == "not json at all"

    def test_no_dump_when_logging_not_debug(self, tmp_path, monkeypatch) -> None:
        """No file is written when verbose mode is not active (WARNING level)."""
        from agent_fox.session.review_parser import parse_triage_output

        monkeypatch.chdir(tmp_path)
        # caplog.at_level is NOT used — the logger stays at WARNING/NOTSET
        parse_triage_output("not json at all", "fix-issue-1", "fix-issue-1:0:triage")

        dump_dir = tmp_path / ".agent-fox"
        assert not dump_dir.exists(), "Expected no .agent-fox/ directory when not in verbose mode"

    def test_session_id_sanitised_in_filename(self, tmp_path, monkeypatch, caplog) -> None:
        """Colons in session_id are replaced so the filename is safe."""
        from agent_fox.session.review_parser import parse_triage_output

        monkeypatch.chdir(tmp_path)
        with caplog.at_level(logging.DEBUG, logger="agent_fox.session.review_parser"):
            parse_triage_output("bad", "fix-issue-99", "fix-issue-99:0:triage")

        files = list((tmp_path / ".agent-fox").glob("parse_failure_triage_*.txt"))
        assert len(files) == 1
        assert ":" not in files[0].name


class TestParseFixReviewVerboseDump:
    """Verify raw reviewer response is written to .agent-fox/ on parse failure in verbose mode."""

    def test_dump_written_when_debug_logging_enabled(self, tmp_path, monkeypatch, caplog) -> None:
        """A file is created in .agent-fox/ when the logger is at DEBUG level."""
        from agent_fox.session.review_parser import parse_fix_review_output

        monkeypatch.chdir(tmp_path)
        with caplog.at_level(logging.DEBUG, logger="agent_fox.session.review_parser"):
            parse_fix_review_output("not json at all", "fix-issue-1", "fix-issue-1:0:reviewer")

        dump_dir = tmp_path / ".agent-fox"
        assert dump_dir.is_dir(), "Expected .agent-fox/ directory to be created"
        files = list(dump_dir.glob("parse_failure_fix_review_*.txt"))
        assert len(files) == 1, f"Expected exactly one dump file, got {files}"
        assert files[0].read_text(encoding="utf-8") == "not json at all"

    def test_no_dump_when_logging_not_debug(self, tmp_path, monkeypatch) -> None:
        """No file is written when verbose mode is not active (WARNING level)."""
        from agent_fox.session.review_parser import parse_fix_review_output

        monkeypatch.chdir(tmp_path)
        parse_fix_review_output("not json at all", "fix-issue-1", "fix-issue-1:0:reviewer")

        dump_dir = tmp_path / ".agent-fox"
        assert not dump_dir.exists(), "Expected no .agent-fox/ directory when not in verbose mode"

    def test_result_still_returned_as_parse_failure(self, tmp_path, monkeypatch, caplog) -> None:
        """Even when verbose dump runs, the result is still FixReviewResult(is_parse_failure=True)."""
        from agent_fox.session.review_parser import parse_fix_review_output

        monkeypatch.chdir(tmp_path)
        with caplog.at_level(logging.DEBUG, logger="agent_fox.session.review_parser"):
            result = parse_fix_review_output("not json", "fix-issue-1", "s1")

        assert result.is_parse_failure is True
        assert result.overall_verdict == "FAIL"
