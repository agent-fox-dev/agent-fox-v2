"""Tests for predictive pattern detection.

Test Spec: TS-13-11, TS-13-12, TS-13-13, TS-13-E5
Requirements: 13-REQ-5.1, 13-REQ-5.2, 13-REQ-5.3, 13-REQ-5.E1
"""

from __future__ import annotations

import duckdb

from agent_fox.knowledge.query_patterns import (
    Pattern,
    detect_patterns,
    render_patterns,
)
from tests.unit.knowledge.conftest import create_empty_db


class TestDetectPatterns:
    """TS-13-11: Detect patterns finds recurring co-occurrences.

    Requirements: 13-REQ-5.1, 13-REQ-5.2
    """

    def test_finds_recurring_path_change_failures(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Detects src/auth/ changes followed by test failures."""
        patterns = detect_patterns(causal_db, min_occurrences=2)
        assert len(patterns) >= 1
        assert any("src/auth/" in p.trigger for p in patterns)
        assert all(p.occurrences >= 2 for p in patterns)
        assert all(isinstance(p.confidence, float) for p in patterns)

    def test_pattern_has_required_fields(self, causal_db: duckdb.DuckDBPyConnection) -> None:
        """Each pattern has trigger, effect, occurrences, last_seen, confidence."""
        patterns = detect_patterns(causal_db, min_occurrences=2)
        for p in patterns:
            assert isinstance(p.trigger, str)
            assert isinstance(p.effect, str)
            assert isinstance(p.occurrences, int)
            assert isinstance(p.last_seen, str)
            assert isinstance(p.confidence, float)


class TestDetectPatternsInsufficientData:
    """TS-13-12: Detect patterns with insufficient data.

    Requirement: 13-REQ-5.E1
    """

    def test_empty_outcomes_returns_empty(self) -> None:
        """An empty session_outcomes table yields no patterns."""
        conn = create_empty_db()
        try:
            patterns = detect_patterns(conn, min_occurrences=2)
            assert len(patterns) == 0
        finally:
            conn.close()


class TestRenderPatterns:
    """TS-13-13: Render patterns as text.

    Requirement: 13-REQ-5.3
    """

    def test_render_plain_text(self) -> None:
        """Rendering patterns produces readable text."""
        patterns = [
            Pattern(
                trigger="src/auth/",
                effect="test failures",
                occurrences=3,
                last_seen="2026-01-05",
                confidence=0.7,
            ),
        ]
        text = render_patterns(patterns, use_color=False)
        assert "src/auth/" in text
        assert "test failures" in text
        assert "3" in text
        assert "\x1b[" not in text

    def test_escapes_markdown_special_chars(self) -> None:
        """Issue #193: markdown special characters are backslash-escaped."""
        patterns = [
            Pattern(
                trigger="src/[auth]/",
                effect="test_*.py failures",
                occurrences=3,
                last_seen="2026-01-05",
                confidence=0.7,
            ),
        ]
        text = render_patterns(patterns, use_color=False)
        assert "src/\\[auth\\]/" in text
        assert "test\\_\\*\\.py failures" in text

    def test_render_empty_patterns(self) -> None:
        """Rendering an empty pattern list produces output without errors."""
        text = render_patterns([], use_color=False)
        assert isinstance(text, str)


class TestPatternsEmptyStore:
    """TS-13-E5: Patterns command with no knowledge store.

    Requirement: 13-REQ-5.E1
    """

    def test_empty_tables_returns_no_patterns(self) -> None:
        """An empty database yields no patterns."""
        conn = create_empty_db()
        try:
            patterns = detect_patterns(conn)
            assert len(patterns) == 0
        finally:
            conn.close()
