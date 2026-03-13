"""Tests for auditor archetype: registry, convergence, prompt, output, events.

Test Spec: TS-46-1, TS-46-2, TS-46-17, TS-46-18, TS-46-19 through TS-46-22,
           TS-46-29 through TS-46-32, TS-46-E2, TS-46-E3,
           TS-46-P4, TS-46-P5
Requirements: 46-REQ-1.*, 46-REQ-5.*, 46-REQ-6.*, 46-REQ-8.*
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ---------------------------------------------------------------------------
# TS-46-1: Registry Entry Exists
# Requirements: 46-REQ-1.1, 46-REQ-1.2, 46-REQ-1.3, 46-REQ-1.4
# ---------------------------------------------------------------------------


class TestRegistryEntry:
    """Verify the auditor entry exists in ARCHETYPE_REGISTRY with correct fields."""

    def test_registry_entry(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        assert "auditor" in ARCHETYPE_REGISTRY
        entry = ARCHETYPE_REGISTRY["auditor"]
        assert entry.injection == "auto_mid"
        assert entry.retry_predecessor is True
        assert entry.task_assignable is True
        assert entry.default_model_tier == "STANDARD"
        assert entry.templates == ["auditor.md"]
        expected_cmds = {"ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv"}
        assert expected_cmds.issubset(set(entry.default_allowlist))


# ---------------------------------------------------------------------------
# TS-46-2: Get Archetype Returns Auditor
# Requirement: 46-REQ-1.E1
# ---------------------------------------------------------------------------


class TestGetArchetypeAuditor:
    """Verify get_archetype('auditor') returns the auditor entry."""

    def test_get_archetype_auditor(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("auditor")
        assert entry.name == "auditor"


# ---------------------------------------------------------------------------
# TS-46-17: Prompt Template Exists
# Requirement: 46-REQ-5.1
# ---------------------------------------------------------------------------


class TestTemplateExists:
    """Verify auditor.md template file exists."""

    def test_template_exists(self) -> None:
        template_path = Path("agent_fox/_templates/prompts/auditor.md")
        assert template_path.exists(), f"Template not found: {template_path}"


# ---------------------------------------------------------------------------
# TS-46-18: Prompt Template Content
# Requirements: 46-REQ-5.2, 46-REQ-5.3, 46-REQ-5.4, 46-REQ-5.5
# ---------------------------------------------------------------------------


class TestTemplateContent:
    """Verify auditor.md contains required structural elements."""

    def test_template_content(self) -> None:
        template_path = Path("agent_fox/_templates/prompts/auditor.md")
        content = template_path.read_text()
        lower = content.lower()

        # Five audit dimensions
        assert "coverage" in lower
        assert "assertion strength" in lower
        assert "precondition fidelity" in lower
        assert "edge case" in lower
        assert "independence" in lower

        # Verdict values
        assert "PASS" in content
        assert "WEAK" in content
        assert "MISSING" in content
        assert "MISALIGNED" in content

        # Template variables
        assert "{spec_name}" in content
        assert "{task_group}" in content


# ---------------------------------------------------------------------------
# TS-46-19: Convergence Union Semantics
# Requirements: 46-REQ-6.1, 46-REQ-6.2, 46-REQ-6.3
# ---------------------------------------------------------------------------


class TestConvergenceUnion:
    """Verify converge_auditor uses union: worst verdict per TS entry."""

    def test_convergence_union(self) -> None:
        from agent_fox.session.convergence import (
            AuditEntry,
            AuditResult,
            converge_auditor,
        )

        r1 = AuditResult(
            entries=[
                AuditEntry(ts_entry="TS-1", test_functions=[], verdict="PASS"),
                AuditEntry(ts_entry="TS-2", test_functions=[], verdict="WEAK"),
            ],
            overall_verdict="PASS",
            summary="ok",
        )
        r2 = AuditResult(
            entries=[
                AuditEntry(ts_entry="TS-1", test_functions=[], verdict="MISSING"),
                AuditEntry(ts_entry="TS-2", test_functions=[], verdict="PASS"),
            ],
            overall_verdict="FAIL",
            summary="bad",
        )

        merged = converge_auditor([r1, r2])

        entry_map = {e.ts_entry: e for e in merged.entries}
        assert entry_map["TS-1"].verdict == "MISSING"
        assert entry_map["TS-2"].verdict == "WEAK"
        assert merged.overall_verdict == "FAIL"


# ---------------------------------------------------------------------------
# TS-46-20: Convergence Single Instance Passthrough
# Requirement: 46-REQ-6.E1
# ---------------------------------------------------------------------------


class TestConvergenceSingle:
    """Verify single instance result is returned directly."""

    def test_convergence_single(self) -> None:
        from agent_fox.session.convergence import (
            AuditEntry,
            AuditResult,
            converge_auditor,
        )

        result = AuditResult(
            entries=[
                AuditEntry(ts_entry="TS-1", test_functions=["test_a"], verdict="PASS"),
            ],
            overall_verdict="PASS",
            summary="ok",
        )

        merged = converge_auditor([result])
        assert merged == result


# ---------------------------------------------------------------------------
# TS-46-21: Convergence All Instances Fail (empty input)
# Requirement: 46-REQ-6.E2
# ---------------------------------------------------------------------------


class TestConvergenceEmpty:
    """Verify empty input returns PASS with warning."""

    def test_convergence_empty(self) -> None:
        from agent_fox.session.convergence import converge_auditor

        merged = converge_auditor([])
        assert merged.overall_verdict == "PASS"
        assert len(merged.entries) == 0


# ---------------------------------------------------------------------------
# TS-46-22: Convergence No LLM
# Requirement: 46-REQ-6.4
# ---------------------------------------------------------------------------


class TestConvergenceNoLLM:
    """Verify convergence function does not import or call LLM modules."""

    def test_convergence_no_llm(self) -> None:
        from agent_fox.session.convergence import converge_auditor

        source = inspect.getsource(converge_auditor)
        assert "claude" not in source.lower()
        assert "llm" not in source.lower()
        assert "anthropic" not in source.lower()


# ---------------------------------------------------------------------------
# TS-46-29: Audit File Written
# Requirement: 46-REQ-8.1
# ---------------------------------------------------------------------------


class TestAuditFileWritten:
    """Verify audit.md is written to spec directory."""

    def test_audit_file_written(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        from agent_fox.session.convergence import (
            AuditEntry,
            AuditResult,
        )

        result = AuditResult(
            entries=[
                AuditEntry(
                    ts_entry="TS-05-1",
                    test_functions=["test_foo::test_bar"],
                    verdict="PASS",
                    notes="All good",
                ),
                AuditEntry(
                    ts_entry="TS-05-2",
                    test_functions=["test_foo::test_edge"],
                    verdict="WEAK",
                    notes="Assertion only checks not None",
                ),
            ],
            overall_verdict="PASS",
            summary="All entries have adequate tests.",
        )

        persist_auditor_results(tmp_path, result)

        audit_path = tmp_path / "audit.md"
        assert audit_path.exists()
        content = audit_path.read_text()
        assert "TS-05-1" in content
        assert "PASS" in content or "FAIL" in content


# ---------------------------------------------------------------------------
# TS-46-30: GitHub Issue On FAIL
# Requirement: 46-REQ-8.2
# ---------------------------------------------------------------------------


class TestGitHubIssueOnFail:
    """Verify GitHub issue filed on FAIL verdict."""

    @pytest.mark.asyncio
    async def test_github_issue_on_fail(self) -> None:
        from unittest.mock import AsyncMock

        from agent_fox.session.auditor_output import handle_auditor_github_issue

        from agent_fox.session.convergence import AuditResult

        result = AuditResult(
            entries=[],
            overall_verdict="FAIL",
            summary="Tests inadequate",
        )

        mock_platform = AsyncMock()
        mock_platform.search_issues.return_value = []
        mock_platform.create_issue.return_value = AsyncMock(
            html_url="https://github.com/o/r/issues/1"
        )

        await handle_auditor_github_issue("my_spec", result, platform=mock_platform)

        mock_platform.create_issue.assert_called_once()
        call_args = mock_platform.create_issue.call_args
        title = call_args[1].get("title", call_args[0][0] if call_args[0] else "")
        assert "[Auditor]" in title
        assert "FAIL" in title


# ---------------------------------------------------------------------------
# TS-46-31: GitHub Issue Closed On PASS
# Requirement: 46-REQ-8.3
# ---------------------------------------------------------------------------


class TestGitHubIssueClosedOnPass:
    """Verify existing GitHub issue is closed on PASS."""

    @pytest.mark.asyncio
    async def test_github_issue_closed_on_pass(self) -> None:
        from unittest.mock import AsyncMock

        from agent_fox.session.auditor_output import handle_auditor_github_issue

        from agent_fox.platform.github import IssueResult
        from agent_fox.session.convergence import AuditResult

        result = AuditResult(
            entries=[],
            overall_verdict="PASS",
            summary="All good",
        )

        mock_platform = AsyncMock()
        # Simulate existing open issue
        mock_platform.search_issues.return_value = [
            IssueResult(
                number=42,
                title="[Auditor] my_spec: FAIL",
                html_url="https://github.com/o/r/issues/42",
            )
        ]

        await handle_auditor_github_issue("my_spec", result, platform=mock_platform)

        # Should close the existing issue
        mock_platform.close_issue.assert_called_once()


# ---------------------------------------------------------------------------
# TS-46-32: Retry Audit Event Emitted
# Requirement: 46-REQ-8.4
# ---------------------------------------------------------------------------


class TestRetryAuditEvent:
    """Verify auditor.retry audit event is emitted on retry."""

    def test_retry_audit_event(self) -> None:
        from agent_fox.session.auditor_output import create_auditor_retry_event

        event = create_auditor_retry_event(
            spec_name="my_spec",
            group_number=1,
            attempt=2,
        )

        assert event["event_type"] == "auditor.retry"
        assert event["spec_name"] == "my_spec"
        assert event["group_number"] == 1
        assert event["attempt"] == 2


# ---------------------------------------------------------------------------
# TS-46-E2: gh CLI Unavailable
# Requirement: 46-REQ-8.E1
# ---------------------------------------------------------------------------


class TestGhUnavailable:
    """Verify GitHub issue failure does not block execution."""

    @pytest.mark.asyncio
    async def test_gh_unavailable(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.session.auditor_output import handle_auditor_github_issue

        from agent_fox.session.convergence import AuditResult

        result = AuditResult(
            entries=[],
            overall_verdict="FAIL",
            summary="bad",
        )

        # No platform provided — should log warning and not raise
        with caplog.at_level(logging.WARNING):
            await handle_auditor_github_issue("my_spec", result, platform=None)

        # Should not raise, execution continues


# ---------------------------------------------------------------------------
# TS-46-E3: audit.md Write Failure
# Requirement: 46-REQ-8.E2
# ---------------------------------------------------------------------------


class TestAuditWriteFailure:
    """Verify filesystem error during audit.md write does not block."""

    def test_audit_write_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        from agent_fox.session.convergence import AuditResult

        result = AuditResult(
            entries=[],
            overall_verdict="PASS",
            summary="ok",
        )

        # Make the spec_dir a non-existent path that can't be written to
        bad_path = tmp_path / "nonexistent" / "deeply" / "nested"

        with caplog.at_level(logging.ERROR):
            # Should not raise
            persist_auditor_results(bad_path, result)

        assert any(
            "error" in r.message.lower() or "audit" in r.message.lower()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# TS-46-P4: Convergence Union Semantics (Property)
# Property 4: Worst verdict per TS entry wins
# Validates: 46-REQ-6.1, 46-REQ-6.3
# ---------------------------------------------------------------------------


VERDICT_SEVERITY = {"PASS": 0, "WEAK": 1, "MISALIGNED": 2, "MISSING": 3}
VERDICTS = ["PASS", "WEAK", "MISALIGNED", "MISSING"]


class TestPropertyConvergenceUnion:
    """Merged verdict for each TS entry is the worst across instances."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        data=st.data(),
    )
    @settings(max_examples=30)
    def test_prop_convergence_union(self, data: st.DataObject) -> None:
        from agent_fox.session.convergence import (
            AuditEntry,
            AuditResult,
            converge_auditor,
        )

        n_instances = data.draw(st.integers(min_value=1, max_value=5))
        n_entries = data.draw(st.integers(min_value=1, max_value=5))

        ts_ids = [f"TS-{i}" for i in range(n_entries)]

        results = []
        for _ in range(n_instances):
            entries = []
            for ts_id in ts_ids:
                verdict = data.draw(st.sampled_from(VERDICTS))
                entries.append(
                    AuditEntry(ts_entry=ts_id, test_functions=[], verdict=verdict)
                )
            has_missing = any(e.verdict == "MISSING" for e in entries)
            has_misaligned = any(e.verdict == "MISALIGNED" for e in entries)
            weak_count = sum(1 for e in entries if e.verdict == "WEAK")
            is_fail = has_missing or has_misaligned or weak_count >= 2
            overall = "FAIL" if is_fail else "PASS"
            results.append(
                AuditResult(entries=entries, overall_verdict=overall, summary="")
            )

        merged = converge_auditor(results)

        for ts_id in ts_ids:
            individual_verdicts = []
            for r in results:
                for e in r.entries:
                    if e.ts_entry == ts_id:
                        individual_verdicts.append(e.verdict)
            worst = max(individual_verdicts, key=lambda v: VERDICT_SEVERITY[v])
            merged_verdict = next(
                e.verdict for e in merged.entries if e.ts_entry == ts_id
            )
            assert merged_verdict == worst

        if any(r.overall_verdict == "FAIL" for r in results):
            assert merged.overall_verdict == "FAIL"


# ---------------------------------------------------------------------------
# TS-46-P5: Convergence Determinism (Property)
# Property 5: Identical input produces identical output
# Validates: 46-REQ-6.4
# ---------------------------------------------------------------------------


class TestPropertyConvergenceDeterminism:
    """Convergence produces identical output for identical input."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        data=st.data(),
    )
    @settings(max_examples=20)
    def test_prop_convergence_determinism(self, data: st.DataObject) -> None:
        from agent_fox.session.convergence import (
            AuditEntry,
            AuditResult,
            converge_auditor,
        )

        n_instances = data.draw(st.integers(min_value=1, max_value=3))
        n_entries = data.draw(st.integers(min_value=1, max_value=3))

        ts_ids = [f"TS-{i}" for i in range(n_entries)]

        results = []
        for _ in range(n_instances):
            entries = []
            for ts_id in ts_ids:
                verdict = data.draw(st.sampled_from(VERDICTS))
                entries.append(
                    AuditEntry(ts_entry=ts_id, test_functions=[], verdict=verdict)
                )
            results.append(
                AuditResult(entries=entries, overall_verdict="PASS", summary="")
            )

        merged1 = converge_auditor(results)
        merged2 = converge_auditor(results)
        assert merged1 == merged2
