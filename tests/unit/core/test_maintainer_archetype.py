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
        assert set(entry.modes.keys()) == {"hunt", "extraction"}, (
            f"Expected modes {{'hunt', 'extraction'}}, got {set(entry.modes.keys())} (100-REQ-1.1)"
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
# TS-100-8: ExtractionInput Dataclass
# Requirement: 100-REQ-4.1
# ===========================================================================


class TestExtractionInput:
    """Verify ExtractionInput dataclass has required fields and is frozen."""

    def test_extraction_input_fields(self) -> None:
        """TS-100-8: ExtractionInput must have session_id, transcript, spec_name, archetype, mode."""
        from agent_fox.nightshift.extraction import ExtractionInput

        ei = ExtractionInput(
            session_id="s1",
            transcript="hello world",
            spec_name="test_spec",
            archetype="coder",
        )
        assert ei.session_id == "s1", "session_id field not accessible"
        assert ei.transcript == "hello world", "transcript field not accessible"
        assert ei.spec_name == "test_spec", "spec_name field not accessible"
        assert ei.archetype == "coder", "archetype field not accessible"

    def test_extraction_input_mode_defaults_none(self) -> None:
        """TS-100-8: ExtractionInput.mode should default to None."""
        from agent_fox.nightshift.extraction import ExtractionInput

        ei = ExtractionInput(
            session_id="s1",
            transcript="hello",
            spec_name="test",
            archetype="coder",
        )
        assert ei.mode is None, f"Expected mode=None, got {ei.mode!r}"

    def test_extraction_input_mode_settable(self) -> None:
        """TS-100-8: ExtractionInput.mode can be set to a string."""
        from agent_fox.nightshift.extraction import ExtractionInput

        ei = ExtractionInput(
            session_id="s1",
            transcript="hello",
            spec_name="test",
            archetype="coder",
            mode="hunt",
        )
        assert ei.mode == "hunt"

    def test_extraction_input_is_frozen(self) -> None:
        """TS-100-8: ExtractionInput must be a frozen dataclass."""
        import pytest

        from agent_fox.nightshift.extraction import ExtractionInput

        ei = ExtractionInput(
            session_id="s1",
            transcript="hello",
            spec_name="test",
            archetype="coder",
        )
        assert dataclasses.is_dataclass(ei)
        with pytest.raises((TypeError, AttributeError)):
            ei.session_id = "changed"  # type: ignore[misc]


# ===========================================================================
# TS-100-9: ExtractionResult Dataclass
# Requirement: 100-REQ-4.2
# ===========================================================================


class TestExtractionResult:
    """Verify ExtractionResult dataclass has required fields with correct defaults."""

    def test_extraction_result_defaults(self) -> None:
        """TS-100-9: ExtractionResult() should have facts=[], session_id='', status='not_implemented'."""
        from agent_fox.nightshift.extraction import ExtractionResult

        er = ExtractionResult()
        assert er.facts == [], f"Expected facts=[], got {er.facts!r}"
        assert er.session_id == "", f"Expected session_id='', got {er.session_id!r}"
        assert er.status == "not_implemented", f"Expected status='not_implemented', got {er.status!r}"

    def test_extraction_result_facts_is_list(self) -> None:
        """TS-100-9: ExtractionResult.facts must be a list."""
        from agent_fox.nightshift.extraction import ExtractionResult

        er = ExtractionResult()
        assert isinstance(er.facts, list)

    def test_extraction_result_fields_assignable(self) -> None:
        """TS-100-9: ExtractionResult fields can be set at construction."""
        from agent_fox.nightshift.extraction import ExtractionResult

        er = ExtractionResult(
            facts=[{"key": "value"}],
            session_id="s1",
            status="success",
        )
        assert er.facts == [{"key": "value"}]
        assert er.session_id == "s1"
        assert er.status == "success"


# ===========================================================================
# TS-100-10: extract_knowledge Stub
# Requirements: 100-REQ-4.3, 100-REQ-4.E1
# ===========================================================================


class TestExtractKnowledgeStub:
    """Verify extract_knowledge stub returns empty result without error."""

    def test_returns_extraction_result(self) -> None:
        """TS-100-10: extract_knowledge must return an ExtractionResult."""
        from agent_fox.nightshift.extraction import (
            ExtractionInput,
            ExtractionResult,
            extract_knowledge,
        )

        inp = ExtractionInput(
            session_id="s1",
            transcript="session content here",
            spec_name="spec100",
            archetype="coder",
        )
        result = extract_knowledge(inp)
        assert isinstance(result, ExtractionResult), (
            f"extract_knowledge should return ExtractionResult, got {type(result)}"
        )

    def test_status_not_implemented(self) -> None:
        """TS-100-10: extract_knowledge must return status='not_implemented'."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        inp = ExtractionInput(
            session_id="s1",
            transcript="...",
            spec_name="spec",
            archetype="coder",
        )
        result = extract_knowledge(inp)
        assert result.status == "not_implemented", f"Expected status='not_implemented', got {result.status!r}"

    def test_facts_empty(self) -> None:
        """TS-100-10: extract_knowledge must return empty facts list."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        inp = ExtractionInput(
            session_id="s1",
            transcript="...",
            spec_name="spec",
            archetype="coder",
        )
        result = extract_knowledge(inp)
        assert result.facts == [], f"Expected facts=[], got {result.facts!r}"

    def test_session_id_propagated(self) -> None:
        """TS-100-10: extract_knowledge must propagate session_id into result."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        inp = ExtractionInput(
            session_id="my-session-42",
            transcript="...",
            spec_name="spec",
            archetype="coder",
        )
        result = extract_knowledge(inp)
        assert result.session_id == "my-session-42", f"Expected session_id='my-session-42', got {result.session_id!r}"

    def test_logs_info_message(self, caplog: object) -> None:
        """TS-100-10: extract_knowledge must log an info message when called."""

        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        inp = ExtractionInput(
            session_id="s1",
            transcript="...",
            spec_name="spec",
            archetype="coder",
        )
        with caplog.at_level(logging.INFO, logger="agent_fox.nightshift.extraction"):  # type: ignore[union-attr]
            extract_knowledge(inp)
        assert len(caplog.records) > 0, (  # type: ignore[union-attr]
            "extract_knowledge should log an INFO message when called (100-REQ-4.3)"
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

    def test_triage_logs_warning(self, caplog: object) -> None:
        """TS-100-E1: get_archetype('triage') must log a warning."""

        from agent_fox.archetypes import get_archetype

        with caplog.at_level(logging.WARNING):  # type: ignore[union-attr]
            get_archetype("triage")
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]  # type: ignore[union-attr]
        assert any("triage" in msg.lower() for msg in warning_messages), (
            f"Expected a warning mentioning 'triage', got: {warning_messages} (100-REQ-1.E1)"
        )


# ===========================================================================
# TS-100-E3: Extraction Stub No Exception
# Requirement: 100-REQ-4.E1
# ===========================================================================


class TestExtractionNoException:
    """Verify extract_knowledge never raises for any input."""

    def test_empty_strings_no_exception(self) -> None:
        """TS-100-E3: extract_knowledge with empty string fields must not raise."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        result = extract_knowledge(
            ExtractionInput(
                session_id="",
                transcript="",
                spec_name="",
                archetype="",
            )
        )
        assert result.status == "not_implemented"

    def test_large_transcript_no_exception(self) -> None:
        """TS-100-E3: extract_knowledge with large transcript must not raise."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        result = extract_knowledge(
            ExtractionInput(
                session_id="large",
                transcript="x" * 100_000,
                spec_name="spec",
                archetype="coder",
            )
        )
        assert result.status == "not_implemented"

    def test_special_chars_no_exception(self) -> None:
        """TS-100-E3: extract_knowledge with special chars must not raise."""
        from agent_fox.nightshift.extraction import ExtractionInput, extract_knowledge

        result = extract_knowledge(
            ExtractionInput(
                session_id="s\x00p\x01e\ncial",
                transcript="こんにちは\n<script>alert(1)</script>\n{}[]",
                spec_name="🤖spec",
                archetype="coder",
            )
        )
        assert result.status == "not_implemented"
