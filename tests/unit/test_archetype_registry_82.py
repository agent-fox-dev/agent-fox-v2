"""Tests for triage archetype migration to maintainer:hunt.

Spec 82 originally defined a standalone "triage" archetype. Spec 100
absorbed triage into the maintainer:hunt mode. These tests have been
updated to verify the post-migration state.

See docs/errata/100_triage_archetype_absorption.md for details.

Test Spec: TS-82-1, TS-82-2
Requirements: 82-REQ-1.1, 82-REQ-1.2 (superseded by 100-REQ-2.1, 100-REQ-1.2)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-82-1: Triage archetype migration (updated for spec 100)
# Requirement: 82-REQ-1.1 → superseded by 100-REQ-2.1
# ---------------------------------------------------------------------------


class TestTriageArchetypeRegistered:
    """Verify triage has been absorbed into maintainer:hunt (spec 100 migration)."""

    def test_triage_entry_removed(self) -> None:
        """Post-migration: 'triage' must not be in ARCHETYPE_REGISTRY (100-REQ-2.1)."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "triage" not in ARCHETYPE_REGISTRY, (
            "'triage' should have been removed from ARCHETYPE_REGISTRY (spec 100)"
        )

    def test_maintainer_entry_exists(self) -> None:
        """Post-migration: 'maintainer' must be in ARCHETYPE_REGISTRY (100-REQ-1.1)."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "maintainer" in ARCHETYPE_REGISTRY, (
            "'maintainer' must exist in ARCHETYPE_REGISTRY after triage absorption (spec 100)"
        )

    def test_maintainer_has_hunt_mode_with_triage_allowlist(self) -> None:
        """Post-migration: maintainer:hunt has the triage-equivalent allowlist (100-REQ-1.2)."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "hunt")
        assert cfg.default_allowlist is not None
        assert "git" in (cfg.default_allowlist or [])
        # Must NOT include write/execute commands
        assert "uv" not in (cfg.default_allowlist or [])
        assert "make" not in (cfg.default_allowlist or [])

    def test_maintainer_model_tier_standard(self) -> None:
        """Post-migration: maintainer:hunt uses STANDARD tier (see errata for ADVANCED→STANDARD).

        NOTE: The original triage archetype used ADVANCED tier (82-REQ-1.1).
        Spec 100 defines maintainer:hunt with STANDARD tier. See errata for rationale.
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "hunt")
        assert cfg.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-82-2: Triage system prompt migration
# Requirement: 82-REQ-1.2 — updated for spec 100 maintainer template
# ---------------------------------------------------------------------------


class TestTriageSystemPrompt:
    """Verify build_system_prompt falls back gracefully for removed 'triage' archetype.

    The maintainer.md template will be verified once created in task group 4.
    """

    def test_prompt_contains_context_with_triage_fallback(self) -> None:
        """TS-82-2: Context is included in prompt even after triage fallback."""
        from agent_fox.session.prompt import build_system_prompt

        prompt = build_system_prompt(
            context="issue body",
            archetype="triage",
        )
        assert "issue body" in prompt

    def test_prompt_has_context_with_triage_fallback(self) -> None:
        """TS-82-2: Prompt contains context even when triage profile is missing."""
        from agent_fox.session.prompt import build_system_prompt

        prompt = build_system_prompt(
            context="issue body",
            archetype="triage",
        )
        assert "issue body" in prompt

    def test_triage_archetype_falls_back_to_coder(self) -> None:
        """TS-82-2: get_archetype('triage') returns coder entry (100-REQ-1.E1)."""
        from agent_fox.archetypes import get_archetype

        entry = get_archetype("triage")
        assert entry.name == "coder"


# TestFixReviewerArchetypeRegistered and TestFixReviewerSystemPrompt removed:
# fix_reviewer consolidated into reviewer archetype with mode="fix-review".
