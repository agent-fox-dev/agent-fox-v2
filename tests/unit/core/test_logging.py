"""Tests for agent_fox.core.logging — TRACE level and setup_logging().

Requirements: 01-REQ-6.1, 01-REQ-6.2, 01-REQ-6.3, 01-REQ-6.E1
"""

from __future__ import annotations

import logging

import pytest

from agent_fox.core.logging import TRACE, setup_logging


class TestTRACELevel:
    """TRACE custom log level is defined correctly."""

    def test_trace_is_below_debug(self) -> None:
        """TRACE level must be numerically below DEBUG."""
        assert TRACE < logging.DEBUG

    def test_trace_value(self) -> None:
        """TRACE level value is DEBUG - 5 = 5."""
        assert TRACE == logging.DEBUG - 5

    def test_trace_name_registered(self) -> None:
        """TRACE level name is registered with the logging module."""
        assert logging.getLevelName(TRACE) == "TRACE"


class TestSetupLoggingTrace:
    """setup_logging(trace=True) sets level to TRACE."""

    def test_trace_sets_logger_to_trace_level(self) -> None:
        """Passing trace=True sets agent_fox logger level to TRACE."""
        setup_logging(trace=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == TRACE

    def test_verbose_sets_logger_to_debug(self) -> None:
        """Passing verbose=True sets agent_fox logger level to DEBUG."""
        setup_logging(verbose=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == logging.DEBUG

    def test_quiet_sets_logger_to_error(self) -> None:
        """Passing quiet=True sets agent_fox logger level to ERROR."""
        setup_logging(quiet=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == logging.ERROR

    def test_default_sets_logger_to_warning(self) -> None:
        """Default (no flags) sets agent_fox logger level to WARNING."""
        setup_logging()
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == logging.WARNING

    def test_trace_takes_precedence_over_verbose(self) -> None:
        """trace=True wins over verbose=True."""
        setup_logging(verbose=True, trace=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == TRACE

    def test_trace_takes_precedence_over_quiet(self) -> None:
        """trace=True wins over quiet=True."""
        setup_logging(quiet=True, trace=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == TRACE

    def test_verbose_wins_over_quiet(self) -> None:
        """01-REQ-6.E1: verbose wins when both verbose and quiet are set."""
        setup_logging(verbose=True, quiet=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.level == logging.DEBUG

    def test_trace_implies_debug_messages_visible(self) -> None:
        """With trace=True, DEBUG-level records pass the level filter."""
        setup_logging(trace=True)
        agent_logger = logging.getLogger("agent_fox")
        # TRACE < DEBUG, so DEBUG records are also enabled
        assert agent_logger.isEnabledFor(logging.DEBUG)

    def test_verbose_does_not_show_trace_records(self) -> None:
        """With verbose=True, TRACE-level records are filtered out."""
        setup_logging(verbose=True)
        agent_logger = logging.getLogger("agent_fox")
        assert not agent_logger.isEnabledFor(TRACE)

    def test_trace_shows_trace_records(self) -> None:
        """With trace=True, TRACE-level records are enabled."""
        setup_logging(trace=True)
        agent_logger = logging.getLogger("agent_fox")
        assert agent_logger.isEnabledFor(TRACE)
