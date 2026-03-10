"""Error auto-fix system.

Detects quality checks, collects failures, clusters them by root cause,
generates fix specifications, and runs an iterative fix loop.
"""

from agent_fox.fix.checks import (  # noqa: F401
    CheckCategory,
    CheckDescriptor,
    FailureRecord,
)
