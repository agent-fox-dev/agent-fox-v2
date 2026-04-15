"""Unit tests for agent-fox logging configuration.

Covers the TRACE custom level and setup_logging() verbosity tiers.

Requirements: 01-REQ-6.1, 01-REQ-6.2, 01-REQ-6.3, 01-REQ-6.E1
"""

from __future__ import annotations

import logging

import pytest


# ---------------------------------------------------------------------------
# TRACE level constant
# ---------------------------------------------------------------------------


class TestTraceLevelConstant:
    """TRACE is defined at level 5 (below DEBUG=10)."""

    def test_trace_value_is_5(self) -> None:
        """TRACE must equal 5."""
        from agent_fox.core.logging import TRACE

        assert TRACE == 5

    def test_trace_below_debug(self) -> None:
        """TRACE must be strictly below logging.DEBUG."""
        from agent_fox.core.logging import TRACE

        assert TRACE < logging.DEBUG

    def test_trace_level_name_registered(self) -> None:
        """logging.getLevelName(TRACE) must return 'TRACE'."""
        from agent_fox.core.logging import TRACE

        assert logging.getLevelName(TRACE) == "TRACE"


# ---------------------------------------------------------------------------
# setup_logging() verbosity tiers
# ---------------------------------------------------------------------------


class TestSetupLoggingTiers:
    """setup_logging() sets the correct level for each verbosity tier."""

    def _get_agent_fox_level(self) -> int:
        return logging.getLogger("agent_fox").level

    def test_default_level_is_warning(self) -> None:
        """No flags → WARNING level."""
        from agent_fox.core.logging import setup_logging

        setup_logging(verbose=False, quiet=False, trace=False)
        assert self._get_agent_fox_level() == logging.WARNING

    def test_verbose_sets_debug(self) -> None:
        """--verbose → DEBUG level."""
        from agent_fox.core.logging import setup_logging

        setup_logging(verbose=True, quiet=False, trace=False)
        assert self._get_agent_fox_level() == logging.DEBUG

    def test_quiet_sets_error(self) -> None:
        """--quiet → ERROR level."""
        from agent_fox.core.logging import setup_logging

        setup_logging(verbose=False, quiet=True, trace=False)
        assert self._get_agent_fox_level() == logging.ERROR

    def test_trace_sets_trace_level(self) -> None:
        """--trace → TRACE level (5)."""
        from agent_fox.core.logging import TRACE, setup_logging

        setup_logging(verbose=False, quiet=False, trace=True)
        assert self._get_agent_fox_level() == TRACE

    def test_trace_wins_over_verbose(self) -> None:
        """--trace --verbose → TRACE level (most verbose wins)."""
        from agent_fox.core.logging import TRACE, setup_logging

        setup_logging(verbose=True, quiet=False, trace=True)
        assert self._get_agent_fox_level() == TRACE

    def test_trace_wins_over_quiet(self) -> None:
        """--trace --quiet → TRACE level (01-REQ-6.E1: most info wins)."""
        from agent_fox.core.logging import TRACE, setup_logging

        setup_logging(verbose=False, quiet=True, trace=True)
        assert self._get_agent_fox_level() == TRACE

    def test_verbose_wins_over_quiet(self) -> None:
        """--verbose --quiet → DEBUG level (01-REQ-6.E1: most info wins)."""
        from agent_fox.core.logging import setup_logging

        setup_logging(verbose=True, quiet=True, trace=False)
        assert self._get_agent_fox_level() == logging.DEBUG


# ---------------------------------------------------------------------------
# TRACE emission gating
# ---------------------------------------------------------------------------


class TestTraceLevelEmission:
    """TRACE records are only emitted when the logger level is TRACE."""

    def test_trace_not_emitted_at_debug_level(self, caplog: pytest.LogCaptureFixture) -> None:
        """At DEBUG level, TRACE records must not be captured."""
        from agent_fox.core.logging import TRACE, setup_logging

        setup_logging(verbose=True, quiet=False, trace=False)

        with caplog.at_level(logging.DEBUG, logger="agent_fox"):
            logging.getLogger("agent_fox.test_sentinel").log(TRACE, "bulk payload dump")

        trace_records = [r for r in caplog.records if r.levelno == TRACE]
        assert trace_records == [], "TRACE records must not be emitted at DEBUG level"

    def test_trace_emitted_at_trace_level(self, caplog: pytest.LogCaptureFixture) -> None:
        """At TRACE level, TRACE records must be captured."""
        from agent_fox.core.logging import TRACE, setup_logging

        setup_logging(verbose=False, quiet=False, trace=True)

        with caplog.at_level(TRACE, logger="agent_fox"):
            logging.getLogger("agent_fox.test_sentinel").log(TRACE, "bulk payload dump")

        trace_records = [r for r in caplog.records if r.levelno == TRACE]
        assert len(trace_records) == 1
        assert "bulk payload dump" in trace_records[0].message
