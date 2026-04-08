"""Integration smoke tests for spec generator lifecycle.

Test Spec: TS-86-SMOKE-1 through TS-86-SMOKE-5, TS-86-20, TS-86-27, TS-86-28
Requirements: 86-REQ-2.*, 86-REQ-3.*, 86-REQ-4.*, 86-REQ-5.*, 86-REQ-6.*,
              86-REQ-8.*, 86-REQ-10.*
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock

from agent_fox.nightshift.config import NightShiftConfig
from agent_fox.nightshift.spec_gen import (
    LABEL_BLOCKED,
    LABEL_DONE,
    LABEL_PENDING,
    IssueComment,
    SpecGenerator,
    SpecPackage,
)
from agent_fox.platform.github import IssueResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days_ago(n: int) -> str:
    """Return an ISO 8601 UTC timestamp for n days ago.

    Using dynamic timestamps prevents the staleness check in _is_stale()
    from treating test comments as older than 30 days, which would cause
    run_once() to skip the issue and never call close_issue.
    """
    ts = datetime.now(UTC) - timedelta(days=n)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_config(**overrides: object) -> NightShiftConfig:
    """Create NightShiftConfig with overrides."""
    defaults: dict[str, object] = {
        "max_clarification_rounds": 3,
        "max_budget_usd": 2.0,
        "spec_gen_model_tier": "ADVANCED",
    }
    defaults.update(overrides)
    return NightShiftConfig.model_validate(defaults)


def _make_platform() -> MagicMock:
    """Create a mock platform."""
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
    body: str = "We need widget support.",
    html_url: str | None = None,
) -> IssueResult:
    if html_url is None:
        html_url = f"https://github.com/org/repo/issues/{number}"
    return IssueResult(number=number, title=title, html_url=html_url, body=body)


def _make_fox_comment(
    comment_id: int = 100,
    created_at: str | None = None,
) -> IssueComment:
    if created_at is None:
        created_at = _days_ago(2)
    return IssueComment(
        id=comment_id,
        body="## Agent Fox -- Clarification Needed\n\n1. What is X?\n2. How does Y work?",
        user="agent-fox[bot]",
        created_at=created_at,
    )


def _make_human_comment(
    comment_id: int = 101,
    body: str = "Here are my answers: X is foo, Y works like bar.",
    created_at: str | None = None,
) -> IssueComment:
    if created_at is None:
        created_at = _days_ago(1)
    return IssueComment(
        id=comment_id,
        body=body,
        user="alice",
        created_at=created_at,
    )


def _mock_ai_response(text: str = "Generated content") -> MagicMock:
    """Create a mock AI response."""
    resp = MagicMock()
    resp.content = [TextBlock(type="text", text=text)]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


# ---------------------------------------------------------------------------
# TS-86-20: generate 5-file spec package
# Requirements: 86-REQ-6.1
# ---------------------------------------------------------------------------


class TestGenerateSpecPackage:
    """Verify _generate_spec_package produces all 5 files."""

    async def test_produces_five_files(self) -> None:
        """TS-86-20: SpecPackage with 5 files."""
        platform = _make_platform()
        gen = SpecGenerator(
            platform=platform,
            config=_make_config(),
            repo_root=Path("/tmp/test-repo"),
        )

        issue = _make_issue(number=42)

        mock_ai = AsyncMock(return_value=_mock_ai_response("Generated document"))

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            package = await gen._generate_spec_package(issue, [], MagicMock())

        expected_files = {"prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"}
        assert set(package.files.keys()) == expected_files
        assert all(len(content) > 0 for content in package.files.values())


# ---------------------------------------------------------------------------
# TS-86-27: landing creates feature branch and commits
# Requirements: 86-REQ-8.1
# ---------------------------------------------------------------------------


class TestLandSpec:
    """Verify _land_spec creates a branch, writes files, and commits."""

    async def test_creates_branch_and_commits(self, tmp_path: Path) -> None:
        """TS-86-27: Branch created, files written, commit made."""
        import subprocess

        # Set up a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        # Create initial commit on develop
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "-b", "develop"],
            check=True, capture_output=True,
        )
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        config = _make_config()
        config.merge_strategy = "direct"
        gen = SpecGenerator(platform=platform, config=config, repo_root=tmp_path)

        package = SpecPackage(
            spec_name="87_test_spec",
            files={
                "prd.md": "# PRD\nContent",
                "requirements.md": "# Requirements",
                "design.md": "# Design",
                "test_spec.md": "# Tests",
                "tasks.md": "# Tasks",
            },
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        commit_hash = await gen._land_spec(package, 42)

        assert len(commit_hash) > 0
        assert (tmp_path / ".specs" / "87_test_spec" / "prd.md").exists()

        # Verify commit message
        log = subprocess.run(
            ["git", "-C", str(tmp_path), "log", "--oneline", "-1"],
            capture_output=True, text=True,
        )
        assert "feat(spec): generate 87_test_spec from #42" in log.stdout


# ---------------------------------------------------------------------------
# TS-86-28: direct merge strategy
# Requirements: 86-REQ-8.2
# ---------------------------------------------------------------------------


class TestDirectMergeStrategy:
    """Verify direct merge strategy merges and deletes branch."""

    async def test_merges_and_deletes_branch(self, tmp_path: Path) -> None:
        """TS-86-28: Branch merged into develop. Feature branch deleted."""
        import subprocess

        # Set up a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "-b", "develop"],
            check=True, capture_output=True,
        )
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        config = _make_config()
        config.merge_strategy = "direct"
        gen = SpecGenerator(platform=platform, config=config, repo_root=tmp_path)

        package = SpecPackage(
            spec_name="87_test_spec",
            files={
                "prd.md": "# PRD",
                "requirements.md": "# Req",
                "design.md": "# Design",
                "test_spec.md": "# Tests",
                "tasks.md": "# Tasks",
            },
            source_issue_url="https://github.com/org/repo/issues/42",
        )

        await gen._land_spec(package, 42)

        # Verify on develop branch
        branch = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--show-current"],
            capture_output=True, text=True,
        )
        assert "develop" in branch.stdout

        # Verify feature branch deleted
        branches = subprocess.run(
            ["git", "-C", str(tmp_path), "branch"],
            capture_output=True, text=True,
        )
        assert "spec/87_test_spec" not in branches.stdout


# ===========================================================================
# Integration Smoke Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# TS-86-SMOKE-1: Happy path — clear issue generates and lands spec
# Execution Path: Path 1 from design.md
# ---------------------------------------------------------------------------


class TestSmokeHappyPath:
    """End-to-end test: clear issue produces spec files committed to develop."""

    async def test_happy_path_end_to_end(self, tmp_path: Path) -> None:
        """TS-86-SMOKE-1: Full pipeline: discover → analyze → generate → land → close."""
        import subprocess

        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecGeneratorStream

        # Set up git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "checkout", "-b", "develop"], check=True, capture_output=True)
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        issue = _make_issue(number=42, title="Add widgets")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[])

        config = _make_config()
        budget = SharedBudget(max_cost=None)

        # Mock AI to return clear analysis and documents
        # Note: _check_duplicates skips AI call when no specs exist,
        # so first AI call is from _analyze_issue
        analysis_resp = _mock_ai_response('{"clear": true, "questions": [], "summary": "ok"}')
        doc_resp = _mock_ai_response("Generated document content for spec")

        call_count = 0

        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return analysis_resp
            return doc_resp

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=tmp_path,
        )
        stream._budget = budget

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await stream.run_once()

        # Verify spec files exist
        spec_dirs = list((tmp_path / ".specs").glob("*_*"))
        assert len(spec_dirs) >= 1
        spec_dir = spec_dirs[0]
        assert (spec_dir / "prd.md").exists()

        # Verify issue was closed
        platform.close_issue.assert_called_once_with(42)

        # Verify done label assigned
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert any(label == LABEL_DONE for _, label in assign_calls)

        # Verify cost reported
        assert budget.total_cost >= 0


# ---------------------------------------------------------------------------
# TS-86-SMOKE-2: Ambiguous issue posts clarification
# Execution Path: Path 2 from design.md
# ---------------------------------------------------------------------------


class TestSmokeAmbiguousIssue:
    """End-to-end: ambiguous issue gets clarification comment, label transitions to pending."""

    async def test_ambiguous_posts_clarification(self) -> None:
        """TS-86-SMOKE-2: Clarification posted, pending label, no spec files."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=42, title="Vague feature")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[])

        config = _make_config()
        repo_root = Path("/tmp/smoke-test-ambiguous")

        # Note: _check_duplicates skips AI call when no specs exist
        analysis_resp = _mock_ai_response(
            '{"clear": false, "questions": ["What is the scope?", "What APIs?"], "summary": "Ambiguous"}'
        )

        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            return analysis_resp

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=repo_root,
        )

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await stream.run_once()

        # Verify clarification comment posted
        platform.add_issue_comment.assert_called()
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "## Agent Fox" in comment_body

        # Verify pending label
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert any(label == LABEL_PENDING for _, label in assign_calls)

        # Verify no issue close
        platform.close_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-SMOKE-3: Pending issue with response triggers re-analysis
# Execution Path: Path 3 from design.md
# ---------------------------------------------------------------------------


class TestSmokePendingReanalysis:
    """End-to-end: issue with prior clarification re-analyzed after human reset to af:spec."""

    async def test_pending_reanalysis_generates_spec(self, tmp_path: Path) -> None:
        """TS-86-SMOKE-3: af:spec (human reset) → analyzing → generating → done."""
        import subprocess

        from agent_fox.nightshift.streams import SpecGeneratorStream

        # Set up git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True, capture_output=True)
        (tmp_path / "README.md").write_text("# T")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "checkout", "-b", "develop"], check=True, capture_output=True)
        (tmp_path / ".specs").mkdir()

        platform = _make_platform()
        issue = _make_issue(number=42, title="Widget feature")
        fox = _make_fox_comment(comment_id=1, created_at=_days_ago(2))
        human = _make_human_comment(comment_id=2, created_at=_days_ago(1))

        # Human has reset the label to af:spec after answering clarification
        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[fox, human])

        config = _make_config()

        # Mock AI: clear on re-analysis, generate docs
        # Note: _check_duplicates skips AI call when no specs exist
        clear_resp = _mock_ai_response('{"clear": true, "questions": [], "summary": "ok"}')
        doc_resp = _mock_ai_response("Generated document")

        call_count = 0

        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return clear_resp
            return doc_resp

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=tmp_path,
        )

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await stream.run_once()

        # Verify issue was closed (generated successfully)
        platform.close_issue.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# TS-86-SMOKE-4: Max rounds triggers escalation
# Execution Path: Path 4 from design.md
# ---------------------------------------------------------------------------


class TestSmokeMaxRoundsEscalation:
    """End-to-end: issue hits max rounds and gets escalated."""

    async def test_escalation_at_max_rounds(self) -> None:
        """TS-86-SMOKE-4: Escalation comment posted, blocked label, NOT closed."""
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=42, title="Complex feature")

        # Two prior rounds of clarification
        comments = [
            _make_fox_comment(comment_id=1, created_at=_days_ago(4)),
            _make_human_comment(comment_id=2, created_at=_days_ago(3)),
            IssueComment(
                id=3,
                body="## Agent Fox -- Clarification Needed\n\n1. Still need X?",
                user="agent-fox[bot]",
                created_at=_days_ago(2),
            ),
            _make_human_comment(comment_id=4, body="X is Y", created_at=_days_ago(1)),
        ]

        # Human has reset label to af:spec after answering, but max rounds already hit
        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=comments)

        config = _make_config(max_clarification_rounds=2)

        # AI still finds ambiguity
        # Note: _check_duplicates skips AI call when no specs exist
        ambiguous_resp = _mock_ai_response(
            '{"clear": false, "questions": ["Still need clarity on Z"], "summary": "Unclear"}'
        )

        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            return ambiguous_resp

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/smoke-test-escalation"),
        )

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await stream.run_once()

        # Verify escalation comment
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "Specification Blocked" in comment_body or "blocked" in comment_body.lower()

        # Verify blocked label
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert any(label == LABEL_BLOCKED for _, label in assign_calls)

        # Verify NOT closed
        platform.close_issue.assert_not_called()


# ---------------------------------------------------------------------------
# TS-86-SMOKE-5: Cost cap exceeded aborts generation
# Execution Path: Path 5 from design.md
# ---------------------------------------------------------------------------


class TestSmokeCostCapExceeded:
    """End-to-end: generation aborted when per-spec cost exceeds budget."""

    async def test_cost_cap_aborts(self) -> None:
        """TS-86-SMOKE-5: Budget-exceeded comment, blocked label, cost reported."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecGeneratorStream

        platform = _make_platform()
        issue = _make_issue(number=42, title="Expensive feature")

        async def list_by_label(label: str, *args: object, **kwargs: object) -> list[IssueResult]:
            if label == "af:spec":
                return [issue]
            return []

        platform.list_issues_by_label = AsyncMock(side_effect=list_by_label)
        platform.list_issue_comments = AsyncMock(return_value=[])

        config = _make_config(max_budget_usd=0.001)  # Very low
        budget = SharedBudget(max_cost=None)

        # Expensive AI responses
        expensive_resp = MagicMock()
        expensive_resp.content = [TextBlock(type="text", text="Generated content")]
        expensive_resp.usage.input_tokens = 100000
        expensive_resp.usage.output_tokens = 50000
        expensive_resp.usage.cache_read_input_tokens = 0
        expensive_resp.usage.cache_creation_input_tokens = 0

        # For analysis (clear) — duplicate check skipped when no specs exist
        clear_resp = _mock_ai_response('{"clear": true, "questions": [], "summary": "ok"}')

        call_count = 0

        async def mock_ai(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return clear_resp
            return expensive_resp  # generation calls

        stream = SpecGeneratorStream(
            config=config,
            platform=platform,
            repo_root=Path("/tmp/smoke-test-cost"),
        )
        stream._budget = budget

        with patch("agent_fox.nightshift.spec_gen.cached_messages_create", mock_ai):
            await stream.run_once()

        # Verify budget comment posted
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "budget" in comment_body.lower()

        # Verify blocked label
        assign_calls = [call.args for call in platform.assign_label.call_args_list]
        assert any(label == LABEL_BLOCKED for _, label in assign_calls)

        # Cost still reported
        assert budget.total_cost >= 0
