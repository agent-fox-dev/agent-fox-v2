"""Clusterer tests.

Test Spec: TS-08-8 (fallback clustering), TS-08-9 (AI clustering)
Edge Cases: TS-08-E4 (unparseable AI response)
Requirements: 08-REQ-3.1, 08-REQ-3.2, 08-REQ-3.3
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent_fox.core.config import AgentFoxConfig
from agent_fox.fix.clusterer import cluster_failures
from agent_fox.fix.detector import CheckCategory, CheckDescriptor

from .conftest import make_failure_record


class TestFallbackClusteringByCheck:
    """TS-08-8: Fallback clustering groups by check command.

    Requirement: 08-REQ-3.3
    """

    def test_fallback_produces_one_cluster_per_check(
        self, mock_config: AgentFoxConfig,
    ) -> None:
        """When AI is unavailable, fallback creates one cluster per check."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        ruff_check = CheckDescriptor(
            name="ruff",
            command=["uv", "run", "ruff", "check", "."],
            category=CheckCategory.LINT,
        )
        pytest_failure = make_failure_record(check=pytest_check, output="test failed")
        ruff_failure = make_failure_record(
            check=ruff_check, output="lint error",
        )

        with patch(
            "agent_fox.fix.clusterer.anthropic.Anthropic",
            side_effect=ConnectionError("no API"),
        ):
            clusters = cluster_failures(
                [pytest_failure, ruff_failure], mock_config,
            )

        assert len(clusters) == 2
        # Each cluster should relate to one of the checks
        labels = {c.label for c in clusters}
        assert any("pytest" in label.lower() for label in labels)

    def test_fallback_preserves_all_failures(
        self, mock_config: AgentFoxConfig,
    ) -> None:
        """Fallback clustering preserves every failure record."""
        check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        failures = [
            make_failure_record(check=check, output="fail 1"),
            make_failure_record(check=check, output="fail 2"),
        ]

        with patch(
            "agent_fox.fix.clusterer.anthropic.Anthropic",
            side_effect=ConnectionError("no API"),
        ):
            clusters = cluster_failures(failures, mock_config)

        total = sum(len(c.failures) for c in clusters)
        assert total == 2


class TestAIClusteringSemanticGroups:
    """TS-08-9: AI clustering groups failures semantically.

    Requirement: 08-REQ-3.1, 08-REQ-3.2
    """

    def test_ai_clustering_parses_response(
        self, mock_config: AgentFoxConfig,
    ) -> None:
        """AI clustering parses a valid model response into semantic clusters."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        ruff_check = CheckDescriptor(
            name="ruff",
            command=["uv", "run", "ruff", "check", "."],
            category=CheckCategory.LINT,
        )
        f1 = make_failure_record(check=pytest_check, output="ImportError: no module")
        f2 = make_failure_record(check=pytest_check, output="ImportError: missing lib")
        f3 = make_failure_record(check=ruff_check, output="unused import os")

        ai_response = json.dumps({
            "groups": [
                {
                    "label": "Missing import",
                    "failure_indices": [0, 1],
                    "suggested_approach": "Add missing import statements",
                },
                {
                    "label": "Style violation",
                    "failure_indices": [2],
                    "suggested_approach": "Fix formatting and remove unused imports",
                },
            ],
        })

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=ai_response)]
        mock_client.return_value.messages.create.return_value = mock_response

        with patch("agent_fox.fix.clusterer.anthropic.Anthropic", mock_client):
            clusters = cluster_failures([f1, f2, f3], mock_config)

        assert len(clusters) == 2
        total_failures = sum(len(c.failures) for c in clusters)
        assert total_failures == 3
        assert all(c.label != "" for c in clusters)
        assert all(c.suggested_approach != "" for c in clusters)


# -- Edge case tests ---------------------------------------------------------


class TestAIClusteringUnparseableResponse:
    """TS-08-E4: AI clustering response unparseable.

    Requirement: 08-REQ-3.3
    """

    def test_invalid_json_falls_back(
        self, mock_config: AgentFoxConfig,
    ) -> None:
        """Invalid AI JSON response triggers fallback clustering."""
        pytest_check = CheckDescriptor(
            name="pytest",
            command=["uv", "run", "pytest"],
            category=CheckCategory.TEST,
        )
        ruff_check = CheckDescriptor(
            name="ruff",
            command=["uv", "run", "ruff", "check", "."],
            category=CheckCategory.LINT,
        )
        f1 = make_failure_record(check=pytest_check, output="test failed")
        f2 = make_failure_record(check=ruff_check, output="lint error")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]
        mock_client.return_value.messages.create.return_value = mock_response

        with patch("agent_fox.fix.clusterer.anthropic.Anthropic", mock_client):
            clusters = cluster_failures([f1, f2], mock_config)

        # Fallback: one cluster per check
        assert len(clusters) == 2
        total = sum(len(c.failures) for c in clusters)
        assert total == 2
