"""Night Shift configuration models (re-exported from core.config).

The canonical definitions now live in ``agent_fox.core.config`` to
break the circular import between core and nightshift.  This module
re-exports them for backward compatibility.

Requirements: 61-REQ-9.1, 61-REQ-9.2, 61-REQ-9.E1,
              85-REQ-9.1, 85-REQ-9.E1, 85-REQ-9.E2
"""

from agent_fox.core.config import NightShiftCategoryConfig, NightShiftConfig

__all__ = ["NightShiftCategoryConfig", "NightShiftConfig"]
