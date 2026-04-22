"""Tests for confidence-aware fact selection.

Test Spec: TS-39-11, TS-39-12, TS-39-13
Requirements: 39-REQ-4.1, 39-REQ-4.2, 39-REQ-4.3

Note: The confidence_threshold field was removed from KnowledgeConfig in
spec 114. Old config files that specify it are silently ignored via
extra="ignore". The original fact selection pipeline was removed.
"""

from __future__ import annotations


class TestConfidenceFiltering:
    """TS-39-11, TS-39-12, TS-39-13: Confidence-aware fact filtering.

    Requirements: 39-REQ-4.2 (superseded by 114-REQ-8.1)

    The confidence_threshold field was removed in spec 114. Old config
    files specifying it are silently ignored.
    """

    def test_old_confidence_threshold_silently_ignored(self) -> None:
        """Old confidence_threshold field is silently ignored."""
        from agent_fox.core.config import KnowledgeConfig

        # Should not raise - extra="ignore" silently drops unknown fields
        config = KnowledgeConfig(confidence_threshold=0.7)  # type: ignore[call-arg]
        assert not hasattr(config, "confidence_threshold") or "confidence_threshold" not in config.model_fields
