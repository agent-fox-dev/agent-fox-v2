"""Tests for auditor-related configuration models.

Test Spec: TS-46-3 through TS-46-6, TS-46-P7
Requirements: 46-REQ-2.1, 46-REQ-2.2, 46-REQ-2.3, 46-REQ-2.4,
              46-REQ-2.E1, 46-REQ-2.E2
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ---------------------------------------------------------------------------
# TS-46-3: Config Auditor Field Default
# Requirements: 46-REQ-2.1, 46-REQ-2.E1
# ---------------------------------------------------------------------------


class TestAuditorDefaultTrue:
    """Verify ArchetypesConfig defaults auditor to True."""

    def test_auditor_default_true(self) -> None:
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig()
        assert config.auditor is True


# ---------------------------------------------------------------------------
# TS-46-4: Config Instance Count Clamping
# Requirement: 46-REQ-2.2
# ---------------------------------------------------------------------------


class TestInstanceClamping:
    """Verify auditor instance count is clamped to [1, 5]."""

    def test_instance_clamping(self) -> None:
        from agent_fox.core.config import ArchetypeInstancesConfig

        assert ArchetypeInstancesConfig(auditor=0).auditor == 1
        assert ArchetypeInstancesConfig(auditor=6).auditor == 5
        assert ArchetypeInstancesConfig(auditor=3).auditor == 3


# ---------------------------------------------------------------------------
# TS-46-5: AuditorConfig Defaults and Clamping
# Requirements: 46-REQ-2.3, 46-REQ-2.4
# ---------------------------------------------------------------------------


class TestAuditorConfigDefaults:
    """Verify AuditorConfig defaults and clamping behavior."""

    def test_auditor_config_defaults(self) -> None:
        from agent_fox.core.config import AuditorConfig

        default = AuditorConfig()
        assert default.min_ts_entries == 5
        assert default.max_retries == 2

    def test_min_ts_entries_clamped(self) -> None:
        from agent_fox.core.config import AuditorConfig

        assert AuditorConfig(min_ts_entries=0).min_ts_entries == 1

    def test_max_retries_clamped(self) -> None:
        from agent_fox.core.config import AuditorConfig

        assert AuditorConfig(max_retries=-1).max_retries == 0


# ---------------------------------------------------------------------------
# TS-46-6: Max Retries Zero Means No Retry
# Requirement: 46-REQ-2.E2
# ---------------------------------------------------------------------------


class TestMaxRetriesZero:
    """Verify max_retries=0 is a valid config (auditor runs once)."""

    def test_max_retries_zero(self) -> None:
        from agent_fox.core.config import AuditorConfig

        config = AuditorConfig(max_retries=0)
        assert config.max_retries == 0


# ---------------------------------------------------------------------------
# TS-46-P7: Config Clamping (Property)
# Property 7: Config values are always within valid ranges.
# Validates: 46-REQ-2.2, 46-REQ-2.3
# ---------------------------------------------------------------------------


class TestPropertyConfigClamping:
    """Config values are always within valid ranges."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS,
        reason="hypothesis not installed",
    )
    @given(
        min_ts=st.integers(min_value=-100, max_value=100),
        max_r=st.integers(min_value=-100, max_value=100),
        inst=st.integers(min_value=-100, max_value=100),
    )
    @settings(max_examples=50)
    def test_prop_config_clamping(
        self,
        min_ts: int,
        max_r: int,
        inst: int,
    ) -> None:
        from agent_fox.core.config import (
            ArchetypeInstancesConfig,
            AuditorConfig,
        )

        ac = AuditorConfig(min_ts_entries=min_ts, max_retries=max_r)
        ic = ArchetypeInstancesConfig(auditor=inst)

        assert ac.min_ts_entries >= 1
        assert ac.max_retries >= 0
        assert 1 <= ic.auditor <= 5
