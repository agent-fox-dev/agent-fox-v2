"""Tests for triage archetype registration.

Test Spec: TS-82-1, TS-82-2
Requirements: 82-REQ-1.1, 82-REQ-1.2
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-82-1: Triage archetype registered in registry
# Requirement: 82-REQ-1.1
# ---------------------------------------------------------------------------


class TestTriageArchetypeRegistered:
    """Verify the registry contains a 'triage' entry with correct config."""

    def test_triage_entry_exists(self) -> None:
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "triage" in ARCHETYPE_REGISTRY

    def test_triage_template(self) -> None:
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["triage"]
        assert entry.templates == ["triage.md"]

    def test_triage_model_tier(self) -> None:
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["triage"]
        assert entry.default_model_tier == "ADVANCED"

    def test_triage_read_only_allowlist(self) -> None:
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["triage"]
        assert entry.default_allowlist is not None
        assert "git" in entry.default_allowlist
        # Must NOT include write/execute commands
        assert "uv" not in entry.default_allowlist
        assert "make" not in entry.default_allowlist


# ---------------------------------------------------------------------------
# TS-82-2: Triage system prompt loads template
# Requirement: 82-REQ-1.2
# ---------------------------------------------------------------------------


class TestTriageSystemPrompt:
    """Verify build_system_prompt loads triage.md and interpolates."""

    def test_prompt_contains_spec_name(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        prompt = build_system_prompt(
            context="issue body",
            task_group=0,
            spec_name="fix-issue-42",
            archetype="triage",
        )
        assert "fix-issue-42" in prompt

    def test_prompt_contains_context(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        prompt = build_system_prompt(
            context="issue body",
            task_group=0,
            spec_name="fix-issue-42",
            archetype="triage",
        )
        assert "issue body" in prompt

    def test_prompt_references_triage_or_acceptance_criteria(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        prompt = build_system_prompt(
            context="issue body",
            task_group=0,
            spec_name="fix-issue-42",
            archetype="triage",
        )
        prompt_lower = prompt.lower()
        assert "triage" in prompt_lower or "acceptance criteria" in prompt_lower


# TestFixReviewerArchetypeRegistered and TestFixReviewerSystemPrompt removed:
# fix_reviewer consolidated into reviewer archetype with mode="fix-review".
