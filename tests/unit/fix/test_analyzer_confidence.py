"""Tests for analyzer confidence normalization.

Test Spec: TS-37-11, TS-37-12
Requirements: 37-REQ-5.1, 37-REQ-5.2, 37-REQ-5.3
"""

from __future__ import annotations

from agent_fox.fix.analyzer import Improvement, filter_improvements


class TestImprovementConfidence:
    """TS-37-11: Improvement uses float confidence.

    Requirements: 37-REQ-5.1, 37-REQ-5.2
    """

    def test_improvement_accepts_float_confidence(self) -> None:
        """Improvement can be created with float confidence."""
        imp = Improvement(
            id="IMP-1",
            tier="quick_win",
            title="Test improvement",
            description="Test description",
            files=["test.py"],
            impact="high",
            confidence=0.85,
        )
        assert isinstance(imp.confidence, float)
        assert imp.confidence == 0.85


class TestConfidenceFilter:
    """TS-37-12: Confidence filter uses < 0.5 threshold.

    Requirement: 37-REQ-5.3
    """

    def test_filter_excludes_below_threshold(self) -> None:
        """Items with confidence < 0.5 are excluded."""
        improvements = [
            Improvement(
                id=f"IMP-{i}",
                tier="quick_win",
                title=f"Improvement {i}",
                description="desc",
                files=["test.py"],
                impact="medium",
                confidence=conf,
            )
            for i, conf in enumerate([0.3, 0.5, 0.7, 0.9])
        ]

        filtered = filter_improvements(improvements)
        assert len(filtered) == 3
        assert all(i.confidence >= 0.5 for i in filtered)

    def test_filter_keeps_exact_threshold(self) -> None:
        """Items with confidence == 0.5 are kept (not excluded)."""
        imp = Improvement(
            id="IMP-1",
            tier="quick_win",
            title="Borderline",
            description="desc",
            files=["test.py"],
            impact="medium",
            confidence=0.5,
        )
        filtered = filter_improvements([imp])
        assert len(filtered) == 1
