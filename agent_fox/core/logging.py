"""Logging configuration for agent-fox.

Configures Python's logging module with a consistent format and
level control via --verbose, --quiet, and --trace flags. Uses named
loggers per module for component-based log filtering.

When a Rich Live display is active (e.g. the progress spinner),
log messages are routed through Rich's console so they appear
cleanly above the spinner instead of corrupting it.

Log level hierarchy (low → high):
  TRACE (5) — bulk AI payload dumps (prompts, raw responses)
  DEBUG (10) — standard debug output
  INFO (20) — progress and informational messages
  WARNING (30) — default level
  ERROR (40) — errors only (--quiet)

Requirements: 01-REQ-6.1, 01-REQ-6.2, 01-REQ-6.3, 01-REQ-6.E1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

_LOG_FORMAT = "[%(levelname)s] %(name)s: %(message)s"

# Custom level below DEBUG for bulk AI payload dumps (full prompts, raw responses).
# Use logger.log(TRACE, ...) for multi-KB payloads that would drown --verbose output.
TRACE: int = logging.DEBUG - 5  # 5
logging.addLevelName(TRACE, "TRACE")


class LiveAwareHandler(logging.Handler):
    """Log handler that routes output through a Rich Live console when active.

    When a Rich ``Live`` display is running, writing to stderr via a normal
    ``StreamHandler`` corrupts the spinner line. This handler detects whether
    a Live console has been registered and, if so, prints log messages through
    ``console.print()`` which correctly renders them above the Live area.

    When no Live console is registered, it falls back to normal stderr output.
    """

    def __init__(self) -> None:
        super().__init__()
        self._live_console: Console | None = None
        self._fallback = logging.StreamHandler()

    def set_live_console(self, console: Console | None) -> None:
        """Register or unregister the Rich Live console."""
        self._live_console = console

    def setFormatter(self, fmt: logging.Formatter | None) -> None:  # noqa: N802
        """Set formatter on both this handler and the fallback."""
        super().setFormatter(fmt)
        self._fallback.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._live_console is not None:
                msg = self.format(record)
                style = _level_style(record.levelno)
                self._live_console.print(msg, style=style, highlight=False)
            else:
                self._fallback.emit(record)
        except Exception:
            self.handleError(record)


def _level_style(levelno: int) -> str:
    """Map log level to a Rich style string."""
    if levelno >= logging.ERROR:
        return "bold red"
    if levelno >= logging.WARNING:
        return "yellow"
    return "dim"


# Module-level singleton so ProgressDisplay can register itself.
_live_handler: LiveAwareHandler | None = None


def get_live_handler() -> LiveAwareHandler | None:
    """Return the singleton LiveAwareHandler, if logging has been set up."""
    return _live_handler


def setup_logging(*, verbose: bool = False, quiet: bool = False, trace: bool = False) -> None:
    """Configure Python logging for agent-fox.

    Sets the root ``agent_fox`` logger level and format.

    Args:
        verbose: If True, set level to DEBUG (standard debug output).
        quiet: If True, set level to ERROR (errors only).
        trace: If True, set level to TRACE (includes bulk AI payload dumps).
            Implies verbose — all DEBUG messages are also shown.

    Note:
        When both ``verbose`` and ``quiet`` are True, ``verbose`` wins
        (01-REQ-6.E1: most information wins). ``trace`` takes highest
        precedence and implies verbose.
    """
    global _live_handler  # noqa: PLW0603

    # 01-REQ-6.E1: verbose wins when both flags are set; trace wins over verbose
    if trace:
        level = TRACE
    elif verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING

    # Configure the agent_fox logger (not the root logger)
    agent_logger = logging.getLogger("agent_fox")
    agent_logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if not agent_logger.handlers:
        handler = LiveAwareHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(_LOG_FORMAT)
        handler.setFormatter(formatter)
        agent_logger.addHandler(handler)
        _live_handler = handler
    else:
        # Update existing handler levels
        for h in agent_logger.handlers:
            h.setLevel(level)
            if isinstance(h, LiveAwareHandler):
                _live_handler = h
