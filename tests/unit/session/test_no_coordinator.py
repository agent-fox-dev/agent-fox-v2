"""Tests asserting coordinator archetype removal from session modules.

Test Spec: TS-62-1, TS-62-2, TS-62-6, TS-62-7
Requirements: 62-REQ-1.1, 62-REQ-1.2, 62-REQ-4.1, 62-REQ-5.1
"""

from __future__ import annotations

import logging

import pytest

# -------------------------------------------------------------------
# TS-62-1: Coordinator Absent from Registry
# Requirement: 62-REQ-1.1
# -------------------------------------------------------------------


class TestCoordinatorAbsentFromRegistry:
    """TS-62-1: Verify coordinator is not in ARCHETYPE_REGISTRY."""

    def test_coordinator_absent_from_registry(self) -> None:
        """ARCHETYPE_REGISTRY must not contain 'coordinator' key."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "coordinator" not in ARCHETYPE_REGISTRY


# -------------------------------------------------------------------
# TS-62-2: get_archetype Falls Back for Coordinator
# Requirement: 62-REQ-1.2
# -------------------------------------------------------------------


class TestGetArchetypeCoordinatorFallback:
    """TS-62-2: Verify get_archetype('coordinator') returns coder with warning."""

    def test_get_archetype_coordinator_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_archetype('coordinator') must return the coder entry."""
        from agent_fox.archetypes import get_archetype

        with caplog.at_level(logging.WARNING):
            result = get_archetype("coordinator")

        assert result.name == "coder"

    def test_get_archetype_coordinator_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_archetype('coordinator') must emit a warning log."""
        from agent_fox.archetypes import get_archetype

        with caplog.at_level(logging.WARNING):
            get_archetype("coordinator")

        assert any("coordinator" in record.message for record in caplog.records), (
            "Expected a warning log containing 'coordinator'"
        )


# -------------------------------------------------------------------
# TS-62-7: Parser Known Archetypes Excludes Coordinator
# Requirement: 62-REQ-5.1
# -------------------------------------------------------------------


class TestParserKnownArchetypesExcludesCoordinator:
    """TS-62-7: Verify spec parser's _KNOWN_ARCHETYPES excludes coordinator."""

    def test_parser_known_archetypes_excludes_coordinator(self) -> None:
        """The parser's known archetypes set must not include 'coordinator'."""
        from agent_fox.spec.parser import _KNOWN_ARCHETYPES

        assert "coordinator" not in _KNOWN_ARCHETYPES
