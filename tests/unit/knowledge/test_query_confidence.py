"""Tests for knowledge query confidence normalization.

Test Spec: TS-37-9, TS-37-10
Requirements: 37-REQ-4.1, 37-REQ-4.2, 37-REQ-4.3, 37-REQ-4.4
"""

from __future__ import annotations

from agent_fox.knowledge.search import SearchResult


class TestOracleAnswerConfidence:
    """TS-37-9: OracleAnswer uses float confidence.

    Requirements: 37-REQ-4.1, 37-REQ-4.2
    """

    def test_oracle_answer_has_float_confidence(self) -> None:
        """OracleAnswer.confidence is a float."""
        from agent_fox.knowledge.query import OracleAnswer

        answer = OracleAnswer(
            answer="Test answer",
            sources=[],
            contradictions=None,
            confidence=0.9,
        )
        assert isinstance(answer.confidence, float)

    def test_determine_confidence_returns_float(self) -> None:
        """_determine_confidence returns a float >= 0.8 for 3+ high-sim results."""
        from agent_fox.knowledge.query import Oracle

        oracle = Oracle.__new__(Oracle)

        results = [
            SearchResult(
                fact_id=f"fact-{i}",
                content=f"fact {i}",
                category="decision",
                spec_name="test",
                session_id="test/1",
                commit_sha="abc",
                similarity=0.8,
            )
            for i in range(3)
        ]

        conf = oracle._determine_confidence(results)
        assert isinstance(conf, float)
        assert conf >= 0.8


class TestPatternConfidence:
    """TS-37-10: Pattern uses float confidence.

    Requirements: 37-REQ-4.3, 37-REQ-4.4
    """

    def test_assign_confidence_occurrence_mapping(self) -> None:
        """_assign_confidence returns correct floats for occurrence counts."""
        from agent_fox.knowledge.query import _assign_confidence

        assert _assign_confidence(2) == 0.4
        assert _assign_confidence(3) == 0.7
        assert _assign_confidence(5) == 0.9
        assert _assign_confidence(10) == 0.9

    def test_pattern_has_float_confidence(self) -> None:
        """Pattern.confidence is a float."""
        from agent_fox.knowledge.query import Pattern

        pattern = Pattern(
            trigger="src/auth/",
            effect="test failures",
            occurrences=5,
            last_seen="2026-03-01",
            confidence=0.9,
        )
        assert isinstance(pattern.confidence, float)
