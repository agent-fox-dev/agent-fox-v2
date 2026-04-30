"""Tests for auditor-related configuration models.

Test Spec: TS-46-3, TS-46-4
Requirements: 46-REQ-2.1, 46-REQ-2.2, 46-REQ-2.E1
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# TS-46-3: Config Auditor Field Default
# Requirements: 46-REQ-2.1, 46-REQ-2.E1
# ---------------------------------------------------------------------------


class TestAuditorDefaultTrue:
    """Verify ArchetypesConfig defaults reviewer to True."""

    def test_auditor_default_true(self) -> None:
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig()
        assert config.reviewer is True


# ---------------------------------------------------------------------------
# TS-46-4: Config Instance Count Clamping
# Requirement: 46-REQ-2.2
# ---------------------------------------------------------------------------


class TestInstanceClamping:
    """Verify reviewer instance count is clamped to [1, 5]."""

    def test_instance_clamping(self) -> None:
        from agent_fox.core.config import ArchetypeInstancesConfig

        assert ArchetypeInstancesConfig(reviewer=0).reviewer == 1
        assert ArchetypeInstancesConfig(reviewer=6).reviewer == 5
        assert ArchetypeInstancesConfig(reviewer=3).reviewer == 3
