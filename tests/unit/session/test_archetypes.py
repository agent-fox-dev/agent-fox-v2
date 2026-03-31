"""Tests for archetype registry.

Test Spec: TS-26-9 through TS-26-11, TS-26-E3, TS-26-E4, TS-26-P3, TS-26-P4
Requirements: 26-REQ-3.1, 26-REQ-3.2, 26-REQ-3.3, 26-REQ-3.4, 26-REQ-3.E1, 26-REQ-3.E2
"""

from __future__ import annotations

import logging

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ---------------------------------------------------------------------------
# TS-26-9: Registry contains all roster archetypes
# Requirements: 26-REQ-3.1, 26-REQ-3.2
# ---------------------------------------------------------------------------


class TestRegistryCompleteness:
    """Verify registry contains all archetypes with valid fields."""

    def test_all_archetypes_present(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        expected = {
            "coder",
            "skeptic",
            "verifier",
            "librarian",
            "cartographer",
            "oracle",
            "auditor",
        }
        assert set(ARCHETYPE_REGISTRY.keys()) == expected

    def test_each_entry_has_valid_fields(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        valid_tiers = {"SIMPLE", "STANDARD", "ADVANCED"}
        for name, entry in ARCHETYPE_REGISTRY.items():
            assert entry.name == name
            assert len(entry.templates) >= 1, f"{name} has no templates"
            assert entry.default_model_tier in valid_tiers, (
                f"{name} has invalid model tier: {entry.default_model_tier}"
            )


# ---------------------------------------------------------------------------
# TS-26-11: Per-archetype allowlist override
# Requirement: 26-REQ-3.4
# ---------------------------------------------------------------------------


class TestPerArchetypeAllowlist:
    """Verify archetype allowlist override is used instead of global."""

    def test_skeptic_has_default_allowlist(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["skeptic"]
        assert entry.default_allowlist is not None
        assert isinstance(entry.default_allowlist, list)
        assert len(entry.default_allowlist) > 0

    def test_coder_has_no_allowlist_override(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["coder"]
        assert entry.default_allowlist is None


# ---------------------------------------------------------------------------
# TS-26-E3: Unknown archetype fallback
# Requirement: 26-REQ-3.E1
# ---------------------------------------------------------------------------


class TestUnknownArchetypeFallback:
    """Verify unknown archetype names fall back to coder with warning."""

    def test_unknown_returns_coder(self, caplog: pytest.LogCaptureFixture) -> None:
        from agent_fox.session.archetypes import get_archetype

        with caplog.at_level(logging.WARNING):
            entry = get_archetype("nonexistent_archetype")

        assert entry.name == "coder"
        assert any("nonexistent_archetype" in r.message for r in caplog.records)

    def test_known_archetype_returns_self(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("skeptic")
        assert entry.name == "skeptic"


# ---------------------------------------------------------------------------
# TS-26-P3: Registry Completeness (Property)
# Property 3: All roster archetypes plus coordinator are in registry
# Validates: 26-REQ-3.1, 26-REQ-3.2
# ---------------------------------------------------------------------------


class TestPropertyRegistryCompleteness:
    """All roster archetypes have valid fields."""

    def test_prop_all_entries_valid(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        roster = {
            "coder",
            "skeptic",
            "verifier",
            "librarian",
            "cartographer",
        }
        valid_tiers = {"SIMPLE", "STANDARD", "ADVANCED"}

        for name in roster:
            assert name in ARCHETYPE_REGISTRY, f"Missing: {name}"
            entry = ARCHETYPE_REGISTRY[name]
            assert len(entry.templates) >= 1
            assert entry.default_model_tier in valid_tiers


# ---------------------------------------------------------------------------
# TS-26-P4: Archetype Fallback (Property)
# Property 4: Unknown archetype names always fall back to coder
# Validates: 26-REQ-3.E1, 26-REQ-4.3
# ---------------------------------------------------------------------------


class TestPropertyArchetypeFallback:
    """Unknown archetype names always fall back to coder."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS,
        reason="hypothesis not installed",
    )
    @given(
        name=st.text(min_size=1, max_size=50).filter(
            lambda s: (
                s
                not in {
                    "coder",
                    "skeptic",
                    "verifier",
                    "librarian",
                    "cartographer",
                }
            )
        )
    )
    @settings(max_examples=50)
    def test_prop_unknown_falls_back_to_coder(self, name: str) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype(name)
        assert entry.name == "coder"
