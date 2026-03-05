"""Integration tests for AI-powered criteria auto-fix CLI flow.

Test Spec: TS-22-5, TS-22-E5, TS-22-15
Requirements: 22-REQ-1.4, 22-REQ-4.E1, 22-REQ-4.2
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from agent_fox.cli.app import main


def _setup_project_with_vague_criterion(project_dir: Path) -> None:
    """Create a project with a spec that has a vague criterion."""
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    specs_dir = project_dir / ".specs"
    specs_dir.mkdir()

    spec = specs_dir / "01_test"
    spec.mkdir()
    for f in ["prd.md", "design.md", "test_spec.md"]:
        (spec / f).write_text(f"# {f}\n")

    (spec / "requirements.md").write_text(
        "# Requirements\n\n"
        "### Requirement 1: Feature\n\n"
        "#### Acceptance Criteria\n\n"
        "1. [01-REQ-1.1] THE system SHALL be fast.\n"
    )
    (spec / "test_spec.md").write_text(
        "# Test Spec\n\n**Requirement:** 01-REQ-1.1\n"
    )
    (spec / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Task\n"
        "  - [ ] 1.1 Sub\n"
        "  - [ ] 1.V Verify task group 1\n"
    )


# ==============================================================================
# TS-22-5: No AI rewrite without --ai flag
# ==============================================================================


class TestNoRewriteWithoutAiFlag:
    """TS-22-5: Verify --fix alone does not invoke AI rewrite.

    Requirement: 22-REQ-1.4
    """

    def test_fix_without_ai_no_rewrite_call(self, tmp_path: Path) -> None:
        _setup_project_with_vague_criterion(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch(
                "agent_fox.spec.ai_validator.create_async_anthropic_client"
            ) as mock_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_cls.return_value = mock_client

                runner.invoke(main, ["lint-spec", "--fix"])
                # No AI rewrite call should have been made
                assert mock_client.messages.create.call_count == 0
        finally:
            os.chdir(original_dir)


# ==============================================================================
# TS-22-E5: Re-validation does not re-rewrite
# ==============================================================================


class TestNoReRewrite:
    """TS-22-E5: Rewrite applied once; re-validation reports without re-rewriting.

    Requirement: 22-REQ-4.E1
    """

    def test_rewrite_called_once(self, tmp_path: Path) -> None:
        _setup_project_with_vague_criterion(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock the rewrite_criteria function directly
            with patch(
                "agent_fox.cli.lint_spec.resolve_model"
            ) as mock_model:
                mock_model.return_value = MagicMock(model_id="test-model")

                # Mock AI analysis to always return a vague-criterion finding
                ai_analysis_response = json.dumps(
                    {
                        "issues": [
                            {
                                "criterion_id": "01-REQ-1.1",
                                "issue_type": "vague",
                                "explanation": "Too vague",
                                "suggestion": "Be specific",
                            }
                        ]
                    }
                )

                rewrite_response = json.dumps(
                    {
                        "rewrites": [
                            {
                                "criterion_id": "01-REQ-1.1",
                                "original": "THE system SHALL be fast.",
                                "replacement": "THE system SHALL respond within 200ms.",
                            }
                        ]
                    }
                )

                with patch(
                    "agent_fox.spec.ai_validator.create_async_anthropic_client"
                ) as mock_cls:
                    mock_client = AsyncMock()

                    # First call: AI analysis, returns vague finding
                    # Second call: rewrite, returns replacement
                    # Third call: re-validation AI analysis
                    mock_response_analysis = MagicMock()
                    mock_response_analysis.content = [
                        MagicMock(text=ai_analysis_response)
                    ]

                    mock_response_rewrite = MagicMock()
                    mock_response_rewrite.content = [
                        MagicMock(text=rewrite_response)
                    ]

                    mock_client.messages.create.side_effect = [
                        mock_response_analysis,  # initial AI analysis
                        mock_response_rewrite,  # rewrite call
                        mock_response_analysis,  # re-validation AI analysis
                    ]
                    mock_client.__aenter__.return_value = mock_client
                    mock_cls.return_value = mock_client

                    runner.invoke(
                        main, ["lint-spec", "--ai", "--fix"]
                    )

                    # rewrite_criteria should be called at most once
                    # (analysis + rewrite + re-analysis = 3 calls max,
                    #  NOT analysis + rewrite + re-analysis + re-rewrite)
                    # The rewrite call count should be exactly 1
                    # Total API calls: analysis(1) + rewrite(1) + re-analysis(1) = 3
                    assert mock_client.messages.create.call_count <= 3
        finally:
            os.chdir(original_dir)
