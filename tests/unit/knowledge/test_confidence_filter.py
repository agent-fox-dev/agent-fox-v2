"""Tests for confidence-aware fact selection.

Test Spec: TS-39-11, TS-39-12, TS-39-13
Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-39-11: Confidence Threshold Filtering
# ---------------------------------------------------------------------------


class TestConfidenceFiltering:
    """TS-39-11, TS-39-12, TS-39-13: Confidence-aware fact filtering.

    Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3
    """

    def test_configurable_threshold(self) -> None:
        """TS-39-12: Confidence threshold configurable via config.

        Requirement: 39-REQ-4.2
        """
        # Verify the config schema supports the knowledge.confidence_threshold
        from agent_fox.core.config import KnowledgeConfig

        # KnowledgeConfig should accept confidence_threshold
        config = KnowledgeConfig(confidence_threshold=0.7)
        assert config.confidence_threshold == 0.7

