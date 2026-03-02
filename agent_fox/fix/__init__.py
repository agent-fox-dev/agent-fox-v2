"""Error auto-fix system.

Detects quality checks, collects failures, clusters them by root cause,
generates fix specifications, and runs an iterative fix loop.
"""

from agent_fox.fix.collector import FailureRecord  # noqa: F401
from agent_fox.fix.detector import CheckCategory, CheckDescriptor  # noqa: F401
