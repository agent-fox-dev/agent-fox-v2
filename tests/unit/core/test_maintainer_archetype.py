"""Unit tests for the maintainer archetype definition and extraction types.

Covers registry structure, mode configuration, triage removal,
template existence, extraction dataclasses, and edge cases.

Test Spec: TS-100-1 through TS-100-10, TS-100-E1, TS-100-E3
Requirements: 100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3, 100-REQ-1.4,
              100-REQ-1.E1, 100-REQ-2.1, 100-REQ-2.3,
              100-REQ-3.1, 100-REQ-3.2, 100-REQ-3.3,
              100-REQ-4.1, 100-REQ-4.2, 100-REQ-4.3, 100-REQ-4.E1
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Template helper (mirrors test_reviewer_template.py pattern)
# ---------------------------------------------------------------------------


def _template_path(name: str) -> Path:
    """Return the absolute path to a profile template file."""
    import agent_fox

    package_root = Path(agent_fox.__file__).resolve().parent
    return package_root / "_templates" / "profiles" / name


# ===========================================================================
# TS-100-1: Maintainer Entry With Modes
# Requirement: 100-REQ-1.1
# ===========================================================================


class TestMaintainerModes:
    """Verify maintainer archetype has hunt and extraction modes."""

    def test_maintainer_in_registry(self) -> None:
        """TS-100-1: ARCHETYPE_REGISTRY must contain a 'maintainer' entry."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "maintainer" in ARCHETYPE_REGISTRY, (
            "'maintainer' not found in ARCHETYPE_REGISTRY — add the entry (100-REQ-1.1)"
        )

    def test_maintainer_has_hunt_and_extraction_modes(self) -> None:
        """TS-100-1: Maintainer entry must have 'hunt' and 'extraction' modes."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["maintainer"]
        assert set(entry.modes.keys()) == {"hunt", "fix-triage", "extraction"}, (
            f"Expected modes {{'hunt', 'fix-triage', 'extraction'}}, got {set(entry.modes.keys())} (100-REQ-1.1)"
        )


# ===========================================================================
# TS-100-2: Hunt Mode Config
# Requirement: 100-REQ-1.2
# ===========================================================================


class TestHuntModeConfig:
    """Verify hunt mode has the correct allowlist and model tier."""

    def test_hunt_allowlist(self) -> None:
        """TS-100-2: Hunt mode allowlist contains read-only analysis commands."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "hunt")
        expected = {"ls", "cat", "git", "wc", "head", "tail"}
        actual = set(cfg.default_allowlist or [])
        assert actual == expected, f"Hunt mode allowlist mismatch: expected {expected}, got {actual} (100-REQ-1.2)"

    def test_hunt_model_tier(self) -> None:
        """TS-100-2: Hunt mode model tier is STANDARD."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "hunt")
        assert cfg.default_model_tier == "STANDARD", (
            f"Expected STANDARD tier, got {cfg.default_model_tier!r} (100-REQ-1.2)"
        )

    def test_hunt_not_task_assignable(self) -> None:
        """TS-100-2: Hunt mode base archetype is not task assignable."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "hunt")
        assert cfg.task_assignable is False, "Maintainer:hunt should not be task assignable (100-REQ-1.2)"


# ===========================================================================
# TS-100-3: Extraction Mode Config
# Requirement: 100-REQ-1.3
# ===========================================================================


class TestExtractionModeConfig:
    """Verify extraction mode has no shell access and STANDARD tier."""

    def test_extraction_empty_allowlist(self) -> None:
        """TS-100-3: Extraction mode allowlist must be empty (no shell access)."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "extraction")
        assert cfg.default_allowlist == [], (
            f"Extraction mode must have empty allowlist, got {cfg.default_allowlist!r} (100-REQ-1.3)"
        )

    def test_extraction_model_tier(self) -> None:
        """TS-100-3: Extraction mode model tier is STANDARD."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["maintainer"]
        cfg = resolve_effective_config(entry, "extraction")
        assert cfg.default_model_tier == "STANDARD", (
            f"Expected STANDARD tier, got {cfg.default_model_tier!r} (100-REQ-1.3)"
        )


# ===========================================================================
# TS-100-4: Maintainer Not Task Assignable
# Requirement: 100-REQ-1.4
# ===========================================================================


class TestMaintainerNotAssignable:
    """Verify maintainer base entry is not task assignable."""

    def test_base_not_task_assignable(self) -> None:
        """TS-100-4: ARCHETYPE_REGISTRY['maintainer'].task_assignable is False."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["maintainer"]
        assert entry.task_assignable is False, "Maintainer base entry must have task_assignable=False (100-REQ-1.4)"


# ===========================================================================
# TS-100-5: Triage Removed From Registry
# Requirement: 100-REQ-2.1
# ===========================================================================


class TestTriageRemovedFromRegistry:
    """Verify triage archetype is not in the registry."""

    def test_triage_not_in_registry(self) -> None:
        """TS-100-5: ARCHETYPE_REGISTRY must not contain 'triage'."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "triage" not in ARCHETYPE_REGISTRY, (
            "'triage' should not be in ARCHETYPE_REGISTRY after migration to maintainer:hunt (100-REQ-2.1)"
        )


# ===========================================================================
# TS-100-7: Maintainer Template Exists
# Requirements: 100-REQ-3.1, 100-REQ-3.2, 100-REQ-3.3, 100-REQ-2.3
# ===========================================================================


class TestMaintainerTemplate:
    """Verify maintainer.md template exists and contains mode-specific sections."""

    def test_template_exists(self) -> None:
        """TS-100-7: maintainer.md template must exist in prompts directory."""
        template = _template_path("maintainer.md")
        assert template.exists(), (
            f"maintainer.md template not found at {template} — "
            "create agent_fox/_templates/profiles/maintainer.md (100-REQ-3.1)"
        )

    def test_template_contains_hunt_section(self) -> None:
        """TS-100-7: maintainer.md must contain a hunt mode section."""
        template = _template_path("maintainer.md")
        if not template.exists():
            import pytest

            pytest.skip("maintainer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "hunt" in content, "maintainer.md should contain a 'hunt' section (100-REQ-3.1, 100-REQ-3.2)"

    def test_template_contains_extraction_section(self) -> None:
        """TS-100-7: maintainer.md must contain an extraction mode section."""
        template = _template_path("maintainer.md")
        if not template.exists():
            import pytest

            pytest.skip("maintainer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "extraction" in content, (
            "maintainer.md should contain an 'extraction' section (100-REQ-3.1, 100-REQ-3.3)"
        )

    def test_template_hunt_has_triage_content(self) -> None:
        """TS-100-7: Hunt section must include triage guidance (issue ordering, dependency detection).

        Requirements: 100-REQ-3.2, 100-REQ-2.3
        """
        template = _template_path("maintainer.md")
        if not template.exists():
            import pytest

            pytest.skip("maintainer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        # Must have content about ordering/dependencies (triage absorption per 100-REQ-2.3)
        has_triage_content = any(
            keyword in content for keyword in ("ordering", "dependency", "dependencies", "supersession", "priorit")
        )
        assert has_triage_content, (
            "maintainer.md hunt section should include triage guidance "
            "(issue ordering, dependency detection) per 100-REQ-2.3, 100-REQ-3.2"
        )

    def test_template_extraction_has_transcript_content(self) -> None:
        """TS-100-7: Extraction section must include transcript/fact guidance.

        Requirement: 100-REQ-3.3
        """
        template = _template_path("maintainer.md")
        if not template.exists():
            import pytest

            pytest.skip("maintainer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        has_extraction_content = any(
            keyword in content for keyword in ("transcript", "fact", "facts", "causal", "knowledge")
        )
        assert has_extraction_content, (
            "maintainer.md extraction section should include guidance on "
            "reading transcripts and extracting facts (100-REQ-3.3)"
        )


# ===========================================================================
# TS-100-E1: Triage Fallback
# Requirement: 100-REQ-1.E1
# ===========================================================================


class TestTriageFallback:
    """Verify get_archetype('triage') warns and falls back to coder."""

    def test_triage_returns_coder_entry(self) -> None:
        """TS-100-E1: get_archetype('triage') must return the coder entry."""
        from agent_fox.archetypes import get_archetype

        entry = get_archetype("triage")
        assert entry.name == "coder", (
            f"get_archetype('triage') should fall back to 'coder', got {entry.name!r} (100-REQ-1.E1)"
        )

    def test_triage_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-100-E1: get_archetype('triage') must log a warning."""

        from agent_fox.archetypes import get_archetype

        with caplog.at_level(logging.WARNING):
            get_archetype("triage")
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("triage" in msg.lower() for msg in warning_messages), (
            f"Expected a warning mentioning 'triage', got: {warning_messages} (100-REQ-1.E1)"
        )
