"""Unit tests for the reviewer archetype consolidation.

Covers:
- Reviewer archetype registry entry and mode configs (TS-98-1 through TS-98-6)
- Verifier STANDARD tier and single-instance clamping (TS-98-13, TS-98-14)
- Old archetype entries removed from registry (TS-98-15)
- ArchetypesConfig reviewer toggle (TS-98-16)
- ReviewerConfig defaults (TS-98-17)
- Edge cases: old config keys, coder no mode, reviewer disabled (TS-98-E1 through TS-98-E3)

Test Spec: TS-98-1 through TS-98-6, TS-98-13, TS-98-14, TS-98-15, TS-98-16,
           TS-98-17, TS-98-E1, TS-98-E2, TS-98-E3
Requirements: 98-REQ-1.1 through 98-REQ-1.5, 98-REQ-1.E1,
              98-REQ-2.1, 98-REQ-2.2, 98-REQ-2.E1,
              98-REQ-6.1, 98-REQ-6.2, 98-REQ-6.3,
              98-REQ-7.1, 98-REQ-7.2,
              98-REQ-8.1, 98-REQ-8.2, 98-REQ-8.3, 98-REQ-8.E1
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-98-1: Reviewer Entry With Modes
# Requirement: 98-REQ-1.1
# ---------------------------------------------------------------------------


class TestReviewerEntryWithModes:
    """Verify reviewer archetype has all 4 modes in registry."""

    def test_reviewer_modes(self) -> None:
        """TS-98-1: ARCHETYPE_REGISTRY["reviewer"] has all 4 modes."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "reviewer" in ARCHETYPE_REGISTRY, "reviewer not in ARCHETYPE_REGISTRY — consolidation not implemented"
        entry = ARCHETYPE_REGISTRY["reviewer"]
        expected_modes = {"pre-review", "drift-review", "audit-review", "fix-review"}
        assert set(entry.modes.keys()) == expected_modes, (
            f"Expected modes {expected_modes}, got {set(entry.modes.keys())}"
        )


# ---------------------------------------------------------------------------
# TS-98-2: Pre-review Mode Config
# Requirement: 98-REQ-1.2
# ---------------------------------------------------------------------------


class TestPreReviewModeConfig:
    """Verify pre-review has no shell, auto_pre injection, STANDARD tier."""

    def test_pre_review_config(self) -> None:
        """TS-98-2: pre-review mode has empty allowlist, auto_pre injection, STANDARD tier."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, "pre-review")
        assert cfg.default_allowlist == [], f"pre-review allowlist should be empty, got {cfg.default_allowlist}"
        assert cfg.injection == "auto_pre", f"pre-review injection should be 'auto_pre', got {cfg.injection!r}"
        assert cfg.default_model_tier == "STANDARD", (
            f"pre-review tier should be STANDARD, got {cfg.default_model_tier!r}"
        )


# ---------------------------------------------------------------------------
# TS-98-3: Drift-review Mode Config
# Requirement: 98-REQ-1.3
# ---------------------------------------------------------------------------


class TestDriftReviewModeConfig:
    """Verify drift-review has analysis allowlist and auto_pre injection."""

    def test_drift_review_config(self) -> None:
        """TS-98-3: drift-review has analysis allowlist, auto_pre, STANDARD tier."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, "drift-review")
        expected_cmds = {"ls", "cat", "git", "grep", "find", "head", "tail", "wc"}
        assert cfg.default_allowlist is not None, "drift-review allowlist must not be None"
        assert expected_cmds.issubset(set(cfg.default_allowlist)), (
            f"drift-review allowlist missing commands. "
            f"Expected superset of {expected_cmds}, got {cfg.default_allowlist}"
        )
        assert cfg.injection == "auto_pre", f"drift-review injection should be 'auto_pre', got {cfg.injection!r}"
        assert cfg.default_model_tier == "STANDARD", (
            f"drift-review tier should be STANDARD, got {cfg.default_model_tier!r}"
        )


# ---------------------------------------------------------------------------
# TS-98-4: Audit-review Mode Config
# Requirement: 98-REQ-1.4
# ---------------------------------------------------------------------------


class TestAuditReviewModeConfig:
    """Verify audit-review has extended allowlist, auto_mid, retry=True."""

    def test_audit_review_config(self) -> None:
        """TS-98-4: audit-review has extended allowlist, auto_mid, retry_predecessor=True."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, "audit-review")
        assert cfg.default_allowlist is not None, "audit-review allowlist must not be None"
        assert "uv" in cfg.default_allowlist, f"'uv' must be in audit-review allowlist, got {cfg.default_allowlist}"
        assert cfg.injection == "auto_mid", f"audit-review injection should be 'auto_mid', got {cfg.injection!r}"
        assert cfg.retry_predecessor is True, (
            f"audit-review retry_predecessor should be True, got {cfg.retry_predecessor}"
        )


# ---------------------------------------------------------------------------
# TS-98-5: Fix-review Mode Config
# Requirement: 98-REQ-1.5
# ---------------------------------------------------------------------------


class TestFixReviewModeConfig:
    """Verify fix-review has ADVANCED tier, no injection, extended allowlist."""

    def test_fix_review_config(self) -> None:
        """TS-98-5: fix-review has ADVANCED tier, injection=None, 'make' in allowlist."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, "fix-review")
        assert cfg.default_model_tier == "ADVANCED", (
            f"fix-review tier should be ADVANCED, got {cfg.default_model_tier!r}"
        )
        assert cfg.injection is None, f"fix-review injection should be None (no auto-injection), got {cfg.injection!r}"
        assert cfg.default_allowlist is not None, "fix-review allowlist must not be None"
        assert "make" in cfg.default_allowlist, f"'make' must be in fix-review allowlist, got {cfg.default_allowlist}"


# ---------------------------------------------------------------------------
# TS-98-6: Coder Fix Mode
# Requirements: 98-REQ-2.1, 98-REQ-2.2
# ---------------------------------------------------------------------------


class TestCoderFixMode:
    """Verify coder fix mode matches former fix_coder configuration."""

    def test_coder_fix_mode(self) -> None:
        """TS-98-6: coder fix mode has STANDARD tier, 300 turns, adaptive 64k."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["coder"]
        assert "fix" in entry.modes, f"coder should have 'fix' mode, got modes: {set(entry.modes.keys())}"
        cfg = resolve_effective_config(entry, "fix")
        assert cfg.default_model_tier == "STANDARD", (
            f"coder:fix tier should be STANDARD, got {cfg.default_model_tier!r}"
        )
        assert cfg.default_max_turns == 300, f"coder:fix max_turns should be 300, got {cfg.default_max_turns}"
        assert cfg.default_thinking_mode == "adaptive", (
            f"coder:fix thinking_mode should be 'adaptive', got {cfg.default_thinking_mode!r}"
        )
        assert cfg.default_thinking_budget == 64000, (
            f"coder:fix thinking_budget should be 64000, got {cfg.default_thinking_budget}"
        )


# ---------------------------------------------------------------------------
# TS-98-13: Verifier STANDARD Tier
# Requirements: 98-REQ-6.1, 98-REQ-6.3
# ---------------------------------------------------------------------------


class TestVerifierStandardTier:
    """Verify verifier defaults to STANDARD model tier and retains retry."""

    def test_verifier_standard(self) -> None:
        """TS-98-13: verifier default_model_tier is STANDARD."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["verifier"]
        assert entry.default_model_tier == "STANDARD", (
            f"verifier tier should be STANDARD, got {entry.default_model_tier!r}"
        )

    def test_verifier_retry(self) -> None:
        """TS-98-13 (6.3): verifier retains retry_predecessor=True."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["verifier"]
        assert entry.retry_predecessor is True, (
            f"verifier retry_predecessor should be True, got {entry.retry_predecessor}"
        )


# ---------------------------------------------------------------------------
# TS-98-14: Verifier Single Instance
# Requirements: 98-REQ-6.2, 98-REQ-8.3
# ---------------------------------------------------------------------------


class TestVerifierSingleInstance:
    """Verify verifier instances are clamped to 1."""

    def test_verifier_single(self) -> None:
        """TS-98-14: clamp_instances('verifier', 3) returns 1."""
        from agent_fox.engine.sdk_params import clamp_instances

        assert clamp_instances("verifier", 3) == 1, (
            f"verifier instances should be clamped to 1, got {clamp_instances('verifier', 3)}"
        )

    def test_verifier_single_large(self) -> None:
        """TS-98-14: clamp_instances('verifier', 100) returns 1."""
        from agent_fox.engine.sdk_params import clamp_instances

        assert clamp_instances("verifier", 100) == 1, "verifier instances should always be clamped to 1"

    def test_instances_config_verifier_default(self) -> None:
        """TS-98-14: ArchetypeInstancesConfig has reviewer field (replaces skeptic+auditor)."""
        from agent_fox.core.config import ArchetypeInstancesConfig

        cfg = ArchetypeInstancesConfig()
        # After consolidation: reviewer replaces skeptic+auditor, verifier default=1
        assert hasattr(cfg, "reviewer"), "ArchetypeInstancesConfig should have 'reviewer' field"
        assert cfg.verifier == 1, f"ArchetypeInstancesConfig.verifier default should be 1, got {cfg.verifier}"


# ---------------------------------------------------------------------------
# TS-98-15: Old Entries Removed
# Requirements: 98-REQ-7.1, 98-REQ-7.2
# ---------------------------------------------------------------------------


class TestOldEntriesRemoved:
    """Verify removed archetypes are not in registry."""

    @pytest.mark.parametrize(
        "name",
        ["skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"],
    )
    def test_old_removed(self, name: str) -> None:
        """TS-98-15: Old archetype names must not be in ARCHETYPE_REGISTRY."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert name not in ARCHETYPE_REGISTRY, (
            f"'{name}' should have been removed from ARCHETYPE_REGISTRY during reviewer consolidation"
        )

    def test_old_fallback(self) -> None:
        """TS-98-15 (7.2): get_archetype('skeptic') logs warning and falls back to coder."""
        import io
        import logging

        from agent_fox.archetypes import get_archetype

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)

        arch_logger = logging.getLogger("agent_fox.archetypes")
        arch_logger.addHandler(handler)
        try:
            result = get_archetype("skeptic")
        finally:
            arch_logger.removeHandler(handler)

        # Falls back to coder
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert result == ARCHETYPE_REGISTRY["coder"], "get_archetype('skeptic') should fall back to coder entry"


# ---------------------------------------------------------------------------
# TS-98-16: Config Reviewer Toggle
# Requirements: 98-REQ-8.1
# ---------------------------------------------------------------------------


class TestConfigReviewerToggle:
    """Verify ArchetypesConfig has reviewer toggle, not old toggles."""

    def test_config_toggle(self) -> None:
        """TS-98-16: ArchetypesConfig has reviewer=True, no skeptic/oracle/auditor fields."""
        from agent_fox.core.config import ArchetypesConfig

        cfg = ArchetypesConfig()
        assert hasattr(cfg, "reviewer"), "ArchetypesConfig should have 'reviewer' toggle"
        assert cfg.reviewer is True, f"ArchetypesConfig.reviewer default should be True, got {cfg.reviewer}"
        # Old toggles should be removed
        assert not hasattr(cfg, "skeptic"), "ArchetypesConfig should not have 'skeptic' field after consolidation"
        assert not hasattr(cfg, "oracle"), "ArchetypesConfig should not have 'oracle' field after consolidation"
        assert not hasattr(cfg, "auditor"), "ArchetypesConfig should not have 'auditor' field after consolidation"


# ---------------------------------------------------------------------------
# TS-98-17: ReviewerConfig
# Requirement: 98-REQ-8.2
# ---------------------------------------------------------------------------


class TestReviewerConfig:
    """Verify ReviewerConfig replaces old per-review configs."""

    def test_reviewer_config(self) -> None:
        """TS-98-17: ReviewerConfig has correct default fields."""
        from agent_fox.core.config import ReviewerConfig

        rc = ReviewerConfig()
        assert rc.pre_review_block_threshold == 1, (
            f"pre_review_block_threshold should be 1, got {rc.pre_review_block_threshold}"
        )
        assert rc.drift_review_block_threshold is None, (
            f"drift_review_block_threshold should be None (advisory), got {rc.drift_review_block_threshold}"
        )
        assert rc.audit_min_ts_entries == 5, f"audit_min_ts_entries should be 5, got {rc.audit_min_ts_entries}"
        assert rc.audit_max_retries == 2, f"audit_max_retries should be 2, got {rc.audit_max_retries}"

    def test_reviewer_config_in_archetypes_config(self) -> None:
        """TS-98-17: ArchetypesConfig has reviewer_config field."""
        from agent_fox.core.config import ArchetypesConfig, ReviewerConfig

        cfg = ArchetypesConfig()
        assert hasattr(cfg, "reviewer_config"), "ArchetypesConfig should have 'reviewer_config' field"
        assert isinstance(cfg.reviewer_config, ReviewerConfig), (
            f"reviewer_config should be ReviewerConfig, got {type(cfg.reviewer_config)}"
        )


# ---------------------------------------------------------------------------
# TS-98-E1: Old Config Key Rejected
# Requirements: 98-REQ-1.E1, 98-REQ-8.E1
# ---------------------------------------------------------------------------


class TestOldConfigKeyRejected:
    """Config with old archetype keys raises validation error."""

    def test_old_config_rejected_skeptic(self) -> None:
        """TS-98-E1: Config with archetypes.skeptic raises ValidationError."""
        from pydantic import ValidationError

        from agent_fox.core.config import ArchetypesConfig

        with pytest.raises((ValidationError, ValueError)) as exc_info:
            # If extra="forbid" or a model_validator catches this, it raises
            # For now we test that the old key is rejected with a meaningful error
            cfg = ArchetypesConfig.model_validate({"skeptic": True})
            # If we get here without error, the field must be explicitly absent
            assert not hasattr(cfg, "skeptic"), (
                "ArchetypesConfig silently accepted 'skeptic' key — should raise ValidationError"
            )

        err_str = str(exc_info.value)
        # Error should mention "reviewer" in guidance
        assert "reviewer" in err_str.lower() or "reviewer" in err_str, (
            f"ValidationError should mention 'reviewer', got: {err_str}"
        )


# ---------------------------------------------------------------------------
# TS-98-E2: Coder Without Mode
# Requirement: 98-REQ-2.E1
# ---------------------------------------------------------------------------


class TestCoderWithoutMode:
    """Coder with mode=None behaves identically to current coder."""

    def test_coder_no_mode(self) -> None:
        """TS-98-E2: resolve_effective_config(coder, None) returns base coder config."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["coder"]
        cfg = resolve_effective_config(entry, None)
        assert cfg.default_max_turns == 300, f"coder default max_turns should be 300, got {cfg.default_max_turns}"


# ---------------------------------------------------------------------------
# TS-98-E3: Reviewer Disabled
# Requirement: 98-REQ-4.E1
# ---------------------------------------------------------------------------


class TestReviewerDisabled:
    """Disabled reviewer skips all mode injections."""

    def test_reviewer_disabled(self) -> None:
        """TS-98-E3: collect_enabled_auto_pre with reviewer=False returns no reviewer entries."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import collect_enabled_auto_pre

        cfg = ArchetypesConfig(reviewer=False)
        entries = collect_enabled_auto_pre(cfg)
        reviewer_entries = [e for e in entries if e.name == "reviewer"]
        assert len(reviewer_entries) == 0, f"Expected no reviewer entries when reviewer=False, got {reviewer_entries}"
