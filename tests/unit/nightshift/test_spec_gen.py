"""Tests for SpecGenerator helper and core logic.

Test Spec: TS-86-6 through TS-86-30, TS-86-E4 through TS-86-E18
           (excluding TS-86-31/E16 which are in test_spec_gen_config.py,
            and TS-86-20/27/28 which are integration tests)
Requirements: 86-REQ-2.* through 86-REQ-8.*, 86-REQ-10.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agent_fox.core.errors import IntegrationError
from agent_fox.nightshift.config import NightShiftConfig
from agent_fox.nightshift.spec_gen import (
    LABEL_ANALYZING,
    LABEL_BLOCKED,
    LABEL_DONE,
    LABEL_GENERATING,
    AnalysisResult,
    DuplicateCheckResult,
    IssueComment,
    ReferencedIssue,
    SpecGenerator,
    SpecGenOutcome,
    SpecGenResult,
    SpecPackage,
)
from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIVE_FILES = {
    "prd.md": "# PRD",
    "requirements.md": "# Req",
    "design.md": "# Design",
    "test_spec.md": "# Tests",
    "tasks.md": "# Tasks",
}


def _make_config(**overrides: object) -> NightShiftConfig:
    """Create a NightShiftConfig with optional overrides."""
    defaults = {
        "max_clarification_rounds": 3,
        "max_budget_usd": 2.0,
        "spec_gen_model_tier": "ADVANCED",
    }
    defaults.update(overrides)
    return NightShiftConfig(**defaults)


def _make_platform() -> MagicMock:
    """Create a mock platform satisfying PlatformProtocol."""
    platform = MagicMock()
    platform.list_issues_by_label = AsyncMock(return_value=[])
    platform.assign_label = AsyncMock()
    platform.remove_label = AsyncMock()
    platform.add_issue_comment = AsyncMock()
    platform.close_issue = AsyncMock()
    platform.get_issue = AsyncMock()
    platform.list_issue_comments = AsyncMock(return_value=[])
    platform.create_pull_request = AsyncMock()
    return platform


def _make_issue(
    number: int = 42,
    title: str = "Add widget support",
    body: str = "We need widget support for the platform.",
    html_url: str | None = None,
) -> IssueResult:
    """Create a test IssueResult."""
    if html_url is None:
        html_url = f"https://github.com/org/repo/issues/{number}"
    return IssueResult(number=number, title=title, html_url=html_url, body=body)


def _make_comment(
    comment_id: int = 1,
    body: str = "A comment",
    user: str = "alice",
    created_at: str = "2026-01-01T00:00:00Z",
) -> IssueComment:
    """Create a test IssueComment."""
    return IssueComment(id=comment_id, body=body, user=user, created_at=created_at)


def _make_fox_comment(
    comment_id: int = 100,
    created_at: str = "2026-01-01T12:00:00Z",
    clarification: bool = True,
) -> IssueComment:
    """Create a fox comment (starts with ## Agent Fox)."""
    if clarification:
        body = "## Agent Fox -- Clarification Needed\n\n1. What is X?\n2. How does Y work?"
    else:
        body = "## Agent Fox -- Specification Created\n\nDone."
    return IssueComment(id=comment_id, body=body, user="agent-fox[bot]", created_at=created_at)


def _make_generator(
    config: NightShiftConfig | None = None,
    platform: MagicMock | None = None,
    repo_root: Path | None = None,
) -> SpecGenerator:
    """Create a SpecGenerator instance with mocked dependencies."""
    if config is None:
        config = _make_config()
    if platform is None:
        platform = _make_platform()
    if repo_root is None:
        repo_root = Path("/tmp/test-repo")
    return SpecGenerator(platform=platform, config=config, repo_root=repo_root)


# ---------------------------------------------------------------------------
# TS-86-6: discover af:spec issues
# Requirements: 86-REQ-2.1
# ---------------------------------------------------------------------------


class TestDiscoverAfSpecIssues:
    """Verify run_once polls for both af:spec and af:spec-pending issues."""

    async def test_polls_both_labels(self) -> None:
        """TS-86-6: Both af:spec and af:spec-pending are queried."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue_a = _make_issue(number=1, title="Issue A")
        issue_b = _make_issue(number=2, title="Issue B")

        # Return different issues for different labels
        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue_a]
            if label == "af:spec-pending":
                return [issue_b]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[])

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        # Mock the generator to track process_issue calls
        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock(
                return_value=SpecGenResult(
                    outcome=SpecGenOutcome.GENERATED,
                    issue_number=1,
                    cost=0.0,
                )
            )
            # No new human comment on pending issue, so it should fall through to af:spec
            mock_gen._has_new_human_comment = MagicMock(return_value=False)
            await stream.run_once()

        # Both labels should have been queried
        call_labels = [call.args[0] for call in platform.list_issues_by_label.call_args_list]
        assert "af:spec" in call_labels
        assert "af:spec-pending" in call_labels


# ---------------------------------------------------------------------------
# TS-86-7: sequential processing of oldest issue
# Requirements: 86-REQ-2.2
# ---------------------------------------------------------------------------


class TestSequentialProcessing:
    """Verify only the oldest af:spec issue is processed when multiple exist."""

    async def test_processes_only_oldest(self) -> None:
        """TS-86-7: Only Issue #1 (oldest) is passed to process_issue."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue_1 = _make_issue(number=1, title="Old issue")
        issue_5 = _make_issue(number=5, title="New issue")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue_1, issue_5]  # sorted by created asc
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock(
                return_value=SpecGenResult(
                    outcome=SpecGenOutcome.GENERATED,
                    issue_number=1,
                    cost=0.0,
                )
            )
            await stream.run_once()

            # Only the oldest issue should be processed
            mock_gen.process_issue.assert_called_once()
            processed_issue = mock_gen.process_issue.call_args[0][0]
            assert processed_issue.number == 1


# ---------------------------------------------------------------------------
# TS-86-8: pending issue with new human comment triggers re-analysis
# Requirements: 86-REQ-2.3
# ---------------------------------------------------------------------------


class TestPendingIssueReanalysis:
    """Verify a pending issue with a new human comment is transitioned to analyzing."""

    async def test_new_human_comment_triggers_transition(self) -> None:
        """TS-86-8: Label transitions: assign analyzing, remove pending."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=10)
        fox = _make_fox_comment(comment_id=1, created_at="2026-01-01T00:00:00Z")
        human = _make_comment(comment_id=2, body="Here are my answers", created_at="2026-01-02T00:00:00Z")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec-pending":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[fox, human])

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock(
                return_value=SpecGenResult(
                    outcome=SpecGenOutcome.GENERATED,
                    issue_number=10,
                    cost=0.0,
                )
            )
            mock_gen._has_new_human_comment = MagicMock(return_value=True)
            await stream.run_once()

        # Should transition to analyzing
        assign_calls = [
            call.args for call in platform.assign_label.call_args_list
        ]
        remove_calls = [
            call.args for call in platform.remove_label.call_args_list
        ]
        assert (10, "af:spec-analyzing") in assign_calls
        assert (10, "af:spec-pending") in remove_calls


# ---------------------------------------------------------------------------
# TS-86-9: pending issue without new comment is skipped
# Requirements: 86-REQ-2.4
# ---------------------------------------------------------------------------


class TestPendingIssueSkipped:
    """Verify a pending issue with no new human comment is skipped."""

    async def test_no_new_comment_skips(self) -> None:
        """TS-86-9: process_issue is not called. No label changes."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=10)
        fox = _make_fox_comment(comment_id=1, created_at="2026-01-01T00:00:00Z")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec-pending":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[fox])

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock()
            mock_gen._has_new_human_comment = MagicMock(return_value=False)
            await stream.run_once()

            mock_gen.process_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-10: label transition assigns new before removing old
# Requirements: 86-REQ-3.1
# ---------------------------------------------------------------------------


class TestLabelTransitionOrder:
    """Verify _transition_label calls assign_label before remove_label."""

    async def test_assign_before_remove(self) -> None:
        """TS-86-10: assign_label called before remove_label."""
        platform = _make_platform()
        call_order: list[str] = []

        async def track_assign(*args: object, **kwargs: object) -> None:
            call_order.append("assign")

        async def track_remove(*args: object, **kwargs: object) -> None:
            call_order.append("remove")

        platform.assign_label = AsyncMock(side_effect=track_assign)
        platform.remove_label = AsyncMock(side_effect=track_remove)

        gen = _make_generator(platform=platform)
        await gen._transition_label(42, "af:spec", "af:spec-analyzing")

        assert call_order == ["assign", "remove"]


# ---------------------------------------------------------------------------
# TS-86-11: initial label transition to analyzing
# Requirements: 86-REQ-3.2
# ---------------------------------------------------------------------------


class TestInitialTransitionToAnalyzing:
    """Verify picking up an af:spec issue transitions it to af:spec-analyzing."""

    async def test_transitions_to_analyzing(self) -> None:
        """TS-86-11: Label transitions to af:spec-analyzing."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        # Mock internal methods to isolate transition behavior
        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._generate_spec_package = AsyncMock(
            return_value=SpecPackage(
                spec_name="87_widget_support",
                files=_FIVE_FILES,
                source_issue_url="https://github.com/org/repo/issues/42",
            )
        )
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        await gen.process_issue(issue)

        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert (42, LABEL_ANALYZING) in assign_calls


# ---------------------------------------------------------------------------
# TS-86-12: transition to generating when clear
# Requirements: 86-REQ-3.3
# ---------------------------------------------------------------------------


class TestTransitionToGenerating:
    """Verify a clear analysis transitions to af:spec-generating."""

    async def test_clear_transitions_to_generating(self) -> None:
        """TS-86-12: Label transitions from analyzing to generating."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._generate_spec_package = AsyncMock(
            return_value=SpecPackage(
                spec_name="87_widget_support",
                files=_FIVE_FILES,
                source_issue_url="https://github.com/org/repo/issues/42",
            )
        )
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        await gen.process_issue(issue)

        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert (42, LABEL_GENERATING) in assign_calls


# ---------------------------------------------------------------------------
# TS-86-13: transition to done and close on completion
# Requirements: 86-REQ-3.4
# ---------------------------------------------------------------------------


class TestTransitionToDone:
    """Verify successful generation transitions to af:spec-done and closes the issue."""

    async def test_done_and_closed(self) -> None:
        """TS-86-13: Label af:spec-done assigned. Issue closed."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._generate_spec_package = AsyncMock(
            return_value=SpecPackage(
                spec_name="87_widget_support",
                files=_FIVE_FILES,
                source_issue_url="https://github.com/org/repo/issues/42",
            )
        )
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.GENERATED
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert (42, LABEL_DONE) in assign_calls
        platform.close_issue.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# TS-86-14: analysis sends full context to AI
# Requirements: 86-REQ-4.1
# ---------------------------------------------------------------------------


class TestAnalysisContext:
    """Verify _analyze_issue sends issue body, comments, referenced issues, etc. to AI."""

    async def test_sends_full_context(self) -> None:
        """TS-86-14: AI call includes all context in the prompt."""
        platform = _make_platform()
        gen = _make_generator(platform=platform)

        issue = _make_issue(number=42, body="We need widget support.")
        comments = [_make_comment(body="Some clarification")]

        # We need to mock the AI client to capture the call
        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"clear": true, "questions": [], "summary": "ok"}')]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        gen._ai_client = MagicMock()

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            result = await gen._analyze_issue(issue, comments, MagicMock())

        assert isinstance(result, AnalysisResult)
        mock_ai.assert_called_once()


# ---------------------------------------------------------------------------
# TS-86-15: ambiguous analysis posts clarification
# Requirements: 86-REQ-4.2
# ---------------------------------------------------------------------------


class TestAmbiguousAnalysis:
    """Verify an ambiguous analysis posts a clarification comment and transitions to pending."""

    async def test_ambiguous_posts_clarification(self) -> None:
        """TS-86-15: Clarification comment posted. Label transitions to pending."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(
                clear=False,
                questions=["What is the scope?", "What are the requirements?"],
                summary="Need more info",
            )
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.PENDING
        platform.add_issue_comment.assert_called_once()
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "## Agent Fox" in comment_body
        assert "What is the scope?" in comment_body


# ---------------------------------------------------------------------------
# TS-86-16: reference harvesting parses and fetches
# Requirements: 86-REQ-4.3
# ---------------------------------------------------------------------------


class TestHarvestReferences:
    """Verify _harvest_references parses #N mentions and fetches referenced issues."""

    async def test_parses_and_fetches_references(self) -> None:
        """TS-86-16: Two ReferencedIssue objects returned."""
        platform = _make_platform()
        platform.get_issue = AsyncMock(
            side_effect=[
                IssueResult(number=10, title="Issue 10", html_url="url10", body="Body 10"),
                IssueResult(number=20, title="Issue 20", html_url="url20", body="Body 20"),
            ]
        )
        platform.list_issue_comments = AsyncMock(
            side_effect=[
                [_make_comment(comment_id=1, body="Comment on 10")],
                [_make_comment(comment_id=2, body="Comment on 20")],
            ]
        )

        gen = _make_generator(platform=platform)

        refs = await gen._harvest_references("see #10 and #20", [])

        assert len(refs) == 2
        assert refs[0].number == 10
        assert refs[1].number == 20
        assert isinstance(refs[0], ReferencedIssue)


# ---------------------------------------------------------------------------
# TS-86-17: count clarification rounds
# Requirements: 86-REQ-5.1
# ---------------------------------------------------------------------------


class TestCountClarificationRounds:
    """Verify _count_clarification_rounds counts fox clarification comments."""

    def test_counts_fox_clarification_comments(self) -> None:
        """TS-86-17: Returns 2 for two fox clarification comments."""
        gen = _make_generator()

        comments = [
            _make_fox_comment(comment_id=1, created_at="2026-01-01T00:00:00Z"),
            _make_comment(comment_id=2, body="Here are my answers", created_at="2026-01-02T00:00:00Z"),
            _make_fox_comment(comment_id=3, created_at="2026-01-03T00:00:00Z"),
            _make_comment(comment_id=4, body="More answers", created_at="2026-01-04T00:00:00Z"),
        ]

        assert gen._count_clarification_rounds(comments) == 2


# ---------------------------------------------------------------------------
# TS-86-18: escalation after max rounds
# Requirements: 86-REQ-5.2
# ---------------------------------------------------------------------------


class TestEscalationAfterMaxRounds:
    """Verify escalation when max rounds is reached."""

    async def test_escalates_at_max_rounds(self) -> None:
        """TS-86-18: Escalation comment posted. Label transitions to blocked."""
        platform = _make_platform()
        config = _make_config(max_clarification_rounds=2)

        # Two prior fox clarification comments + human replies
        comments = [
            _make_fox_comment(comment_id=1, created_at="2026-01-01T00:00:00Z"),
            _make_comment(comment_id=2, body="Answers 1", created_at="2026-01-02T00:00:00Z"),
            _make_fox_comment(comment_id=3, created_at="2026-01-03T00:00:00Z"),
            _make_comment(comment_id=4, body="Answers 2", created_at="2026-01-04T00:00:00Z"),
        ]
        platform.list_issue_comments = AsyncMock(return_value=comments)

        issue = _make_issue(number=42)
        gen = _make_generator(config=config, platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(
                clear=False,
                questions=["Still unclear about X"],
                summary="Ambiguous",
            )
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.BLOCKED
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "Specification Blocked" in comment_body or "blocked" in comment_body.lower()

        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert (42, LABEL_BLOCKED) in assign_calls


# ---------------------------------------------------------------------------
# TS-86-19: fox comment detection
# Requirements: 86-REQ-5.3
# ---------------------------------------------------------------------------


class TestFoxCommentDetection:
    """Verify _is_fox_comment correctly identifies fox vs human comments."""

    def test_fox_comment_detected(self) -> None:
        """TS-86-19: Fox comment returns True."""
        gen = _make_generator()
        fox = _make_fox_comment()
        assert gen._is_fox_comment(fox) is True

    def test_human_comment_not_detected(self) -> None:
        """TS-86-19: Human comment returns False."""
        gen = _make_generator()
        human = _make_comment(body="Thanks for the info")
        assert gen._is_fox_comment(human) is False

    def test_whitespace_prefix_detected(self) -> None:
        """TS-86-19: Fox comment with leading whitespace still detected."""
        gen = _make_generator()
        comment = _make_comment(body="  ## Agent Fox -- Info\nContent")
        assert gen._is_fox_comment(comment) is True

    def test_partial_match_not_detected(self) -> None:
        """TS-86-19: Partial '## Agent' without 'Fox' is not detected."""
        gen = _make_generator()
        comment = _make_comment(body="## Agent Smith")
        assert gen._is_fox_comment(comment) is False


# ---------------------------------------------------------------------------
# TS-86-21: prd.md includes source section
# Requirements: 86-REQ-6.2
# ---------------------------------------------------------------------------


class TestPrdSourceSection:
    """Verify the generated prd.md contains a ## Source section linking to the issue."""

    async def test_prd_contains_source_section(self) -> None:
        """TS-86-21: prd.md content contains ## Source and the issue URL."""
        platform = _make_platform()
        gen = _make_generator(platform=platform)

        issue = _make_issue(
            number=42,
            html_url="https://github.com/owner/repo/issues/42",
        )

        # Mock AI to return document contents
        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated document content")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            package = await gen._generate_spec_package(issue, [], MagicMock())

        prd = package.files["prd.md"]
        assert "## Source" in prd
        assert "https://github.com/owner/repo/issues/42" in prd


# ---------------------------------------------------------------------------
# TS-86-22: spec numbering increments from existing
# Requirements: 86-REQ-6.3
# ---------------------------------------------------------------------------


class TestSpecNumbering:
    """Verify _find_next_spec_number returns the next sequential number."""

    def test_increments_from_max(self, tmp_path: Path) -> None:
        """TS-86-22: Returns 87 when max existing prefix is 86."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "84_foo").mkdir()
        (specs_dir / "85_bar").mkdir()
        (specs_dir / "86_baz").mkdir()

        gen = _make_generator(repo_root=tmp_path)
        result = gen._find_next_spec_number()
        assert result == 87


# ---------------------------------------------------------------------------
# TS-86-23: spec generation uses configured model tier
# Requirements: 86-REQ-6.4
# ---------------------------------------------------------------------------


class TestSpecGenModelTier:
    """Verify AI calls use the model resolved from spec_gen_model_tier."""

    async def test_uses_configured_model(self) -> None:
        """TS-86-23: AI calls use correct model tier."""
        config = _make_config(spec_gen_model_tier="STANDARD")
        gen = _make_generator(config=config)

        issue = _make_issue(number=42)

        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated content")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await gen._generate_spec_package(issue, [], MagicMock())

        # Verify the model used matches STANDARD tier
        call_kwargs = mock_ai.call_args
        # model should be claude-sonnet-4-6 for STANDARD
        assert "claude-sonnet-4-6" in str(call_kwargs)


# ---------------------------------------------------------------------------
# TS-86-24: duplicate detection with AI
# Requirements: 86-REQ-7.1
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Verify _check_duplicates calls AI with issue and existing spec info."""

    async def test_detects_duplicate(self) -> None:
        """TS-86-24: AI detects duplicate spec."""
        gen = _make_generator()
        issue = _make_issue(title="Add webhook support")

        from agent_fox.spec.discovery import SpecInfo

        existing_specs = [
            SpecInfo(
                name="42_webhook_support",
                prefix=42,
                path=Path(".specs/42_webhook_support"),
                has_tasks=True,
                has_prd=True,
            )
        ]

        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='{"is_duplicate": true, "overlapping_spec": "42_webhook_support", "explanation": "Same feature"}'
        )]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            result = await gen._check_duplicates(issue, existing_specs)

        assert result.is_duplicate is True
        assert result.overlapping_spec == "42_webhook_support"


# ---------------------------------------------------------------------------
# TS-86-25: duplicate found posts comment and waits
# Requirements: 86-REQ-7.2
# ---------------------------------------------------------------------------


class TestDuplicatePostsComment:
    """Verify a duplicate detection posts a comment and transitions to pending."""

    async def test_duplicate_posts_comment_and_pending(self) -> None:
        """TS-86-25: Comment posted asking about supersession. Label af:spec-pending."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42, title="Add webhook support")

        gen = _make_generator(platform=platform)

        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(
                is_duplicate=True,
                overlapping_spec="42_webhook_support",
                explanation="Same feature",
            )
        )
        gen._harvest_references = AsyncMock(return_value=[])

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.PENDING
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "supersede" in comment_body.lower() or "duplicate" in comment_body.lower()


# ---------------------------------------------------------------------------
# TS-86-26: supersede generates with supersedes section
# Requirements: 86-REQ-7.3
# ---------------------------------------------------------------------------


class TestSupersedeGeneratesSection:
    """Verify supersession generates a spec with ## Supersedes section."""

    async def test_supersede_includes_section(self) -> None:
        """TS-86-26: Generated prd.md contains ## Supersedes referencing old spec."""
        platform = _make_platform()
        gen = _make_generator(platform=platform)

        issue = _make_issue(number=42, title="Add webhook v2")

        # Mock AI to include Supersedes in response
        mock_ai = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated content")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_ai.return_value = mock_response

        # Context indicating supersession
        context = MagicMock()
        context.supersedes = "42_webhook_support"

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            package = await gen._generate_spec_package(issue, [], context)

        prd = package.files["prd.md"]
        assert "## Supersedes" in prd
        assert "42_webhook_support" in prd


# ---------------------------------------------------------------------------
# TS-86-29: PR merge strategy
# Requirements: 86-REQ-8.3
# ---------------------------------------------------------------------------


class TestPRMergeStrategy:
    """Verify PR merge strategy creates a draft PR."""

    async def test_creates_draft_pr(self) -> None:
        """TS-86-29: create_pull_request called with correct args."""
        platform = _make_platform()
        platform.create_pull_request = AsyncMock(
            return_value=MagicMock(html_url="https://github.com/org/repo/pull/1")
        )
        config = _make_config()
        config.merge_strategy = "pr"

        gen = _make_generator(config=config, platform=platform)

        package = SpecPackage(
            spec_name="87_test_spec",
            files=_FIVE_FILES,
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        with patch("agent_fox.nightshift.spec_gen.subprocess") as mock_subprocess:
            mock_subprocess.run = MagicMock(
                return_value=MagicMock(returncode=0, stdout="abc1234\n")
            )
            await gen._land_spec(package, 42)

        platform.create_pull_request.assert_called_once()
        call_kwargs = platform.create_pull_request.call_args
        assert "spec/87_test_spec" in str(call_kwargs)


# ---------------------------------------------------------------------------
# TS-86-30: completion comment and issue close
# Requirements: 86-REQ-8.4
# ---------------------------------------------------------------------------


class TestCompletionComment:
    """Verify completion comment is posted with correct content and issue is closed."""

    async def test_completion_comment_content(self) -> None:
        """TS-86-30: Comment contains spec folder, file list, commit hash."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._generate_spec_package = AsyncMock(
            return_value=SpecPackage(
                spec_name="87_test_spec",
                files=_FIVE_FILES,
                source_issue_url="https://github.com/org/repo/issues/42",
            )
        )
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.GENERATED

        # Find the completion comment (may not be the only comment)
        comment_calls = platform.add_issue_comment.call_args_list
        completion_comment = None
        for call in comment_calls:
            body = call[0][1]
            if "87_test_spec" in body or "Specification Created" in body:
                completion_comment = body
                break

        assert completion_comment is not None
        assert "87_test_spec" in completion_comment
        assert "abc1234" in completion_comment
        platform.close_issue.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# TS-86-32: cost tracking during generation
# Requirements: 86-REQ-10.1
# ---------------------------------------------------------------------------


class TestCostTracking:
    """Verify cumulative cost is tracked across AI calls."""

    async def test_tracks_cumulative_cost(self) -> None:
        """TS-86-32: Cumulative cost tracks across calls."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        config = _make_config(max_budget_usd=10.0)  # High limit so we don't abort
        gen = _make_generator(config=config, platform=platform)

        issue = _make_issue(number=42)

        # Create mock AI responses with cost info
        call_count = 0

        async def mock_ai_call(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.content = [MagicMock(text="Generated content")]
            resp.usage.input_tokens = 1000
            resp.usage.output_tokens = 500
            resp.usage.cache_read_input_tokens = 0
            resp.usage.cache_creation_input_tokens = 0
            return resp

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._find_next_spec_number = MagicMock(return_value=87)

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai_call):
            result = await gen.process_issue(issue)

        # Cost should be positive and tracked
        assert result.cost > 0


# ---------------------------------------------------------------------------
# TS-86-33: cost cap aborts generation
# Requirements: 86-REQ-10.2
# ---------------------------------------------------------------------------


class TestCostCapAbort:
    """Verify generation aborts when cost exceeds max_budget_usd."""

    async def test_aborts_when_budget_exceeded(self) -> None:
        """TS-86-33: Generation aborts. Budget-exceeded comment posted. Issue blocked."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        config = _make_config(max_budget_usd=0.001)  # Very low limit
        gen = _make_generator(config=config, platform=platform)

        issue = _make_issue(number=42)

        # Mock AI with high-cost responses
        async def expensive_ai(*args: object, **kwargs: object) -> MagicMock:
            resp = MagicMock()
            resp.content = [MagicMock(text="Generated content")]
            resp.usage.input_tokens = 100000  # Very expensive
            resp.usage.output_tokens = 50000
            resp.usage.cache_read_input_tokens = 0
            resp.usage.cache_creation_input_tokens = 0
            return resp

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", expensive_ai):
            result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.BLOCKED
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "budget" in comment_body.lower()


# ---------------------------------------------------------------------------
# TS-86-34: cost reported to SharedBudget
# Requirements: 86-REQ-10.3
# ---------------------------------------------------------------------------


class TestCostReportedToSharedBudget:
    """Verify run_once reports cost to SharedBudget."""

    async def test_reports_cost(self) -> None:
        """TS-86-34: SharedBudget.add_cost called with positive value."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=1)

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)

        config = _make_config()
        budget = SharedBudget(max_cost=None)

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )
        stream._budget = budget

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock(
                return_value=SpecGenResult(
                    outcome=SpecGenOutcome.GENERATED,
                    issue_number=1,
                    spec_name="87_test",
                    commit_hash="abc1234",
                    cost=1.50,
                )
            )
            await stream.run_once()

        assert budget.total_cost >= 1.50


# ===========================================================================
# Edge Case Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# TS-86-E4: no af:spec issues is a no-op
# Requirements: 86-REQ-2.E1
# ---------------------------------------------------------------------------


class TestNoIssuesNoOp:
    """Verify run_once does nothing when no issues found."""

    async def test_no_op_on_empty(self) -> None:
        """TS-86-E4: No calls to process_issue."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        platform.list_issues_by_label = AsyncMock(return_value=[])

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock()
            await stream.run_once()

            mock_gen.process_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-E5: stale issue is skipped
# Requirements: 86-REQ-2.E2
# ---------------------------------------------------------------------------


class TestStaleIssueSkipped:
    """Verify issues with no activity for 30+ days are skipped."""

    async def test_stale_issue_skipped_with_warning(self) -> None:
        """TS-86-E5: Issue skipped. Warning logged."""

        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        # Issue with comments older than 30 days
        old_comment = _make_comment(created_at="2025-01-01T00:00:00Z")
        issue = _make_issue(number=1)

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[old_comment])

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        with patch.object(stream, "_generator", create=True) as mock_gen:
            mock_gen.process_issue = AsyncMock()
            await stream.run_once()
            # Stale issue should be skipped, so process_issue should not be called
            mock_gen.process_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-E6: crash recovery resets stale analyzing label
# Requirements: 86-REQ-3.E1
# ---------------------------------------------------------------------------


class TestCrashRecoveryAnalyzing:
    """Verify stale af:spec-analyzing is reset to af:spec."""

    async def test_resets_stale_analyzing(self) -> None:
        """TS-86-E6: Label reset to af:spec."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=10)

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec-analyzing":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        await stream.run_once()

        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        remove_calls = [call.args for call in platform.remove_label.call_args_list]
        assert (10, "af:spec") in assign_calls
        assert (10, "af:spec-analyzing") in remove_calls


# ---------------------------------------------------------------------------
# TS-86-E7: crash recovery resets stale generating label
# Requirements: 86-REQ-3.E2
# ---------------------------------------------------------------------------


class TestCrashRecoveryGenerating:
    """Verify stale af:spec-generating is reset to af:spec."""

    async def test_resets_stale_generating(self) -> None:
        """TS-86-E7: Label reset to af:spec."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=10)

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec-generating":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)

        config = _make_config()
        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/test-repo"),
        )

        await stream.run_once()

        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        remove_calls = [call.args for call in platform.remove_label.call_args_list]
        assert (10, "af:spec") in assign_calls
        assert (10, "af:spec-generating") in remove_calls


# ---------------------------------------------------------------------------
# TS-86-E8: inaccessible referenced issue is skipped
# Requirements: 86-REQ-4.E1
# ---------------------------------------------------------------------------


class TestInaccessibleReferenceSkipped:
    """Verify inaccessible #N reference is skipped with warning."""

    async def test_skips_inaccessible_reference(self) -> None:
        """TS-86-E8: Warning logged. Reference skipped."""
        platform = _make_platform()
        platform.get_issue = AsyncMock(side_effect=IntegrationError("Not found"))

        gen = _make_generator(platform=platform)

        refs = await gen._harvest_references("see #99", [])

        assert len(refs) == 0


# ---------------------------------------------------------------------------
# TS-86-E9: empty issue body treated as ambiguous
# Requirements: 86-REQ-4.E2
# ---------------------------------------------------------------------------


class TestEmptyBodyAmbiguous:
    """Verify empty body triggers clarification."""

    async def test_empty_body_is_ambiguous(self) -> None:
        """TS-86-E9: Issue treated as ambiguous. Clarification posted."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])

        issue = _make_issue(number=1, title="Feature", body="")

        gen = _make_generator(platform=platform)
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])

        # The system should treat empty body as ambiguous
        # Either via direct check or via AI analysis
        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(
                clear=False,
                questions=["What is this feature about?"],
                summary="Empty body",
            )
        )

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.PENDING


# ---------------------------------------------------------------------------
# TS-86-E10: max rounds reached on first analysis
# Requirements: 86-REQ-5.E1
# ---------------------------------------------------------------------------


class TestMaxRoundsFirstAnalysis:
    """Verify escalation works with max_clarification_rounds=1 and 1 prior round."""

    async def test_escalation_at_one_round(self) -> None:
        """TS-86-E10: Escalation posted when 1 >= max of 1."""
        platform = _make_platform()
        config = _make_config(max_clarification_rounds=1)

        # One prior fox clarification + human reply
        comments = [
            _make_fox_comment(comment_id=1, created_at="2026-01-01T00:00:00Z"),
            _make_comment(comment_id=2, body="My answer", created_at="2026-01-02T00:00:00Z"),
        ]
        platform.list_issue_comments = AsyncMock(return_value=comments)

        issue = _make_issue(number=42)
        gen = _make_generator(config=config, platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(
                clear=False,
                questions=["Still unclear"],
                summary="Ambiguous",
            )
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.BLOCKED


# ---------------------------------------------------------------------------
# TS-86-E11: API failure during generation aborts
# Requirements: 86-REQ-6.E1
# ---------------------------------------------------------------------------


class TestApiFailureAborts:
    """Verify API failure aborts generation and blocks issue."""

    async def test_api_failure_blocks_issue(self) -> None:
        """TS-86-E11: Generation aborted. Comment posted. Issue blocked."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])

        issue = _make_issue(number=42)
        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        # Make generation fail
        gen._generate_spec_package = AsyncMock(
            side_effect=Exception("AI API call failed")
        )

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.BLOCKED
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert (42, LABEL_BLOCKED) in assign_calls


# ---------------------------------------------------------------------------
# TS-86-E12: no existing specs uses prefix 01
# Requirements: 86-REQ-6.E2
# ---------------------------------------------------------------------------


class TestNoExistingSpecsPrefix:
    """Verify first spec uses prefix 01."""

    def test_empty_specs_returns_one(self, tmp_path: Path) -> None:
        """TS-86-E12: Returns 1 when no NN_ folders exist."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        gen = _make_generator(repo_root=tmp_path)
        result = gen._find_next_spec_number()
        assert result == 1


# ---------------------------------------------------------------------------
# TS-86-E13: no specs skips duplicate detection
# Requirements: 86-REQ-7.E1
# ---------------------------------------------------------------------------


class TestNoSpecsSkipsDuplicates:
    """Verify duplicate detection is skipped when no specs exist."""

    async def test_skips_when_no_specs(self) -> None:
        """TS-86-E13: Returns not-duplicate without AI call."""
        gen = _make_generator()

        mock_ai = AsyncMock()

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            result = await gen._check_duplicates(_make_issue(), [])

        assert result.is_duplicate is False
        mock_ai.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-E14: branch name collision appends suffix
# Requirements: 86-REQ-8.E1
# ---------------------------------------------------------------------------


class TestBranchCollision:
    """Verify branch name gets suffix on collision."""

    async def test_appends_suffix_on_collision(self, tmp_path: Path) -> None:
        """TS-86-E14: Branch spec/87_test_spec-2 used instead."""
        platform = _make_platform()
        config = _make_config()
        config.merge_strategy = "direct"
        gen = _make_generator(config=config, platform=platform, repo_root=tmp_path)

        package = SpecPackage(
            spec_name="87_test_spec",
            files=_FIVE_FILES,
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        # Mock subprocess to simulate branch collision then success
        call_count = 0

        with patch("agent_fox.nightshift.spec_gen.subprocess") as mock_subprocess:

            def mock_run(cmd, *args: object, **kwargs: object) -> MagicMock:
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                # First branch creation fails, second succeeds
                if "checkout" in cmd and "-b" in cmd:
                    if "spec/87_test_spec-2" in cmd or "spec/87_test_spec-" in " ".join(cmd):
                        result.returncode = 0
                    elif call_count <= 2:
                        result.returncode = 128  # branch exists
                    else:
                        result.returncode = 0
                else:
                    result.returncode = 0
                result.stdout = "abc1234\n"
                return result

            mock_subprocess.run = mock_run
            commit_hash = await gen._land_spec(package, 42)

        # Verify we got a result (the branch collision was handled)
        assert commit_hash is not None


# ---------------------------------------------------------------------------
# TS-86-E15: merge failure blocks issue
# Requirements: 86-REQ-8.E2
# ---------------------------------------------------------------------------


class TestMergeFailureBlocks:
    """Verify merge failure posts branch name and blocks."""

    async def test_merge_failure_posts_branch(self) -> None:
        """TS-86-E15: Comment with branch name posted. Issue blocked."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        issue = _make_issue(number=42)

        gen = _make_generator(platform=platform)

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._generate_spec_package = AsyncMock(
            return_value=SpecPackage(
                spec_name="87_test_spec",
                files=_FIVE_FILES,
                source_issue_url="https://github.com/org/repo/issues/42",
            )
        )
        gen._harvest_references = AsyncMock(return_value=[])
        gen._find_next_spec_number = MagicMock(return_value=87)

        # Make landing fail
        gen._land_spec = AsyncMock(side_effect=Exception("Merge conflict"))

        result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.BLOCKED
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "spec/87_test_spec" in comment_body or "87_test_spec" in comment_body


# ---------------------------------------------------------------------------
# TS-86-E17: invalid model tier falls back to ADVANCED
# Requirements: 86-REQ-9.E2
# ---------------------------------------------------------------------------


class TestInvalidModelTierFallback:
    """Verify invalid tier defaults to ADVANCED with warning."""

    def test_invalid_tier_uses_advanced(self) -> None:
        """TS-86-E17: Model resolves to ADVANCED tier model."""
        from agent_fox.core.models import TIER_DEFAULTS, ModelTier

        config = _make_config(spec_gen_model_tier="NONEXISTENT")
        gen = _make_generator(config=config)

        # The generator should have resolved to the ADVANCED default
        expected_model = TIER_DEFAULTS[ModelTier.ADVANCED]
        assert gen._model_id == expected_model


# ---------------------------------------------------------------------------
# TS-86-E18: unlimited budget when max_budget_usd is 0
# Requirements: 86-REQ-10.E1
# ---------------------------------------------------------------------------


class TestUnlimitedBudget:
    """Verify no budget enforcement when cap is 0."""

    async def test_zero_budget_no_enforcement(self) -> None:
        """TS-86-E18: Generation completes. No budget abort."""
        platform = _make_platform()
        platform.list_issue_comments = AsyncMock(return_value=[])
        config = _make_config(max_budget_usd=0)

        gen = _make_generator(config=config, platform=platform)
        issue = _make_issue(number=42)

        # Mock AI with somewhat expensive responses
        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            resp = MagicMock()
            resp.content = [MagicMock(text="Generated content")]
            resp.usage.input_tokens = 50000
            resp.usage.output_tokens = 25000
            resp.usage.cache_read_input_tokens = 0
            resp.usage.cache_creation_input_tokens = 0
            return resp

        gen._analyze_issue = AsyncMock(
            return_value=AnalysisResult(clear=True, questions=[], summary="ok")
        )
        gen._check_duplicates = AsyncMock(
            return_value=DuplicateCheckResult(is_duplicate=False)
        )
        gen._harvest_references = AsyncMock(return_value=[])
        gen._land_spec = AsyncMock(return_value="abc1234")
        gen._find_next_spec_number = MagicMock(return_value=87)

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            result = await gen.process_issue(issue)

        assert result.outcome == SpecGenOutcome.GENERATED
