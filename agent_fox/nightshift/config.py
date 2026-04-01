"""Night Shift configuration models.

Requirements: 61-REQ-9.1, 61-REQ-9.2, 61-REQ-9.E1
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class NightShiftCategoryConfig(BaseModel):
    """Per-category enable/disable toggles.

    All eight built-in categories are enabled by default.

    Requirements: 61-REQ-9.2, 67-REQ-5.1
    """

    model_config = ConfigDict(extra="ignore")

    dependency_freshness: bool = True
    todo_fixme: bool = True
    test_coverage: bool = True
    deprecated_api: bool = True
    linter_debt: bool = True
    dead_code: bool = True
    documentation_drift: bool = True
    quality_gate: bool = True


class NightShiftConfig(BaseModel):
    """Night-shift daemon configuration.

    Requirements: 61-REQ-9.1, 61-REQ-9.E1
    """

    model_config = ConfigDict(extra="ignore")

    issue_check_interval: int = Field(
        default=900,
        description="Seconds between issue checks (minimum 60)",
    )
    hunt_scan_interval: int = Field(
        default=14400,
        description="Seconds between hunt scans (minimum 60)",
    )
    categories: NightShiftCategoryConfig = Field(
        default_factory=NightShiftCategoryConfig,
        description="Category enable/disable toggles",
    )
    quality_gate_timeout: int = Field(
        default=600,
        description="Per-check timeout in seconds (minimum 60)",
    )

    @field_validator("issue_check_interval", "hunt_scan_interval")
    @classmethod
    def clamp_interval_minimum(cls, v: int, info: object) -> int:
        """Clamp intervals to a minimum of 60 seconds.

        Requirements: 61-REQ-9.E1
        """
        if v < 60:
            logger.warning(
                "Config field '%s' value %d below minimum, clamped to 60",
                getattr(info, "field_name", "interval"),
                v,
            )
            return 60
        return v

    @field_validator("quality_gate_timeout")
    @classmethod
    def clamp_quality_gate_timeout(cls, v: int, info: object) -> int:
        """Clamp quality_gate_timeout to a minimum of 60 seconds.

        Requirements: 67-REQ-5.3
        """
        if v < 60:
            logger.warning(
                "Config field '%s' value %d below minimum, clamped to 60",
                getattr(info, "field_name", "quality_gate_timeout"),
                v,
            )
            return 60
        return v
