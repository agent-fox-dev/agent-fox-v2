"""Logging configuration for agent-fox.

Configures Python's logging module with a consistent format and
level control via --verbose and --quiet flags. Uses named loggers
per module for component-based log filtering.

Requirements: 01-REQ-6.1, 01-REQ-6.2, 01-REQ-6.3, 01-REQ-6.E1
"""

import logging

_LOG_FORMAT = "[%(levelname)s] %(name)s: %(message)s"


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure Python logging for agent-fox.

    Sets the root ``agent_fox`` logger level and format.

    Args:
        verbose: If True, set level to DEBUG (most information).
        quiet: If True, set level to ERROR (errors only).

    Note:
        When both ``verbose`` and ``quiet`` are True, ``verbose`` wins
        (01-REQ-6.E1: most information wins).
    """
    # 01-REQ-6.E1: verbose wins when both flags are set
    if verbose:
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
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(_LOG_FORMAT)
        handler.setFormatter(formatter)
        agent_logger.addHandler(handler)
    else:
        # Update existing handler levels
        for h in agent_logger.handlers:
            h.setLevel(level)
