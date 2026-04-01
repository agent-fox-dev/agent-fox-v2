"""Spec fixer: auto-fix functions for mechanically fixable lint findings.

Backward compatibility shim -- all public symbols are re-exported from the
``agent_fox.spec.fixers`` package.

Requirements: 20-REQ-6.*
"""

# Backward compatibility -- all public symbols re-exported from fixers package.
from agent_fox.spec.fixers import *  # noqa: F401, F403
