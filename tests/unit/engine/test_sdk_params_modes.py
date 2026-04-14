"""Unit tests for SDK resolution functions with mode support.

Test Spec: TS-97-9, TS-97-10, TS-97-11, TS-97-12, TS-97-13, TS-97-E5, TS-97-E6,
           TS-97-SMOKE-1, TS-97-SMOKE-2
Requirements: 97-REQ-4.1, 97-REQ-4.2, 97-REQ-4.3, 97-REQ-4.4, 97-REQ-4.5,
              97-REQ-4.E1, 97-REQ-5.1, 97-REQ-5.2, 97-REQ-5.3, 97-REQ-5.E1
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig, SecurityConfig
from agent_fox.knowledge.db import KnowledgeDB

_MOCK_KB = MagicMock(spec=KnowledgeDB)


# ---------------------------------------------------------------------------
# TS-97-9: resolve_model_tier With Mode
# Requirement: 97-REQ-4.1
# ---------------------------------------------------------------------------


class TestResolveModelTierWithMode:
    """Verify mode-specific model tier takes precedence."""

    def test_mode_level_override_takes_precedence(self) -> None:
        """TS-97-9: Mode-level model_tier overrides archetype-level."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        model_tier="ADVANCED",
                        modes={"pre-review": PerArchetypeConfig(model_tier="SIMPLE")},
                    )
                }
            )
        )
        result = resolve_model_tier(config, "reviewer", mode="pre-review")
        assert result == "SIMPLE"

    def test_mode_level_override_standard(self) -> None:
        """Mode-level override returning STANDARD takes precedence over ADVANCED archetype."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        model_tier="ADVANCED",
                        modes={"fast": PerArchetypeConfig(model_tier="STANDARD")},
                    )
                }
            )
        )
        result = resolve_model_tier(config, "reviewer", mode="fast")
        assert result == "STANDARD"


# ---------------------------------------------------------------------------
# TS-97-10: resolve_model_tier Mode Fallback
# Requirement: 97-REQ-3.3
# ---------------------------------------------------------------------------


class TestResolveModelTierModeFallback:
    """Verify fallback to archetype-level when mode has no override."""

    def test_falls_back_to_archetype_level_when_mode_has_no_override(self) -> None:
        """TS-97-10: Falls back to archetype-level model_tier when mode config missing."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(overrides={"reviewer": PerArchetypeConfig(model_tier="ADVANCED", modes={})})
        )
        result = resolve_model_tier(config, "reviewer", mode="pre-review")
        assert result == "ADVANCED"

    def test_falls_back_to_registry_when_no_config_override(self) -> None:
        """Falls back to registry default when no config override for archetype."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        # coder registry default is STANDARD
        result = resolve_model_tier(config, "coder", mode="some-mode")
        assert result == "STANDARD"

    def test_mode_with_no_model_tier_field_falls_back(self) -> None:
        """Mode with no model_tier in its config falls back to archetype-level."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        model_tier="ADVANCED",
                        modes={"pre-review": PerArchetypeConfig(max_turns=60)},
                    )
                }
            )
        )
        result = resolve_model_tier(config, "reviewer", mode="pre-review")
        assert result == "ADVANCED"


# ---------------------------------------------------------------------------
# Additional: resolve_max_turns with mode (97-REQ-4.2)
# ---------------------------------------------------------------------------


class TestResolveMaxTurnsWithMode:
    """Verify resolve_max_turns accepts and uses mode parameter."""

    def test_mode_level_max_turns_overrides_archetype_level(self) -> None:
        """Mode-level max_turns takes precedence over archetype-level."""
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        max_turns=200,
                        modes={"pre-review": PerArchetypeConfig(max_turns=60)},
                    )
                }
            )
        )
        result = resolve_max_turns(config, "reviewer", mode="pre-review")
        assert result == 60

    def test_mode_without_max_turns_falls_back_to_archetype(self) -> None:
        """Mode with no max_turns falls back to archetype-level."""
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(overrides={"reviewer": PerArchetypeConfig(max_turns=100, modes={})})
        )
        result = resolve_max_turns(config, "reviewer", mode="pre-review")
        assert result == 100


# ---------------------------------------------------------------------------
# Additional: resolve_thinking with mode (97-REQ-4.3)
# ---------------------------------------------------------------------------


class TestResolveThinkingWithMode:
    """Verify resolve_thinking accepts and uses mode parameter."""

    def test_mode_level_thinking_overrides_archetype(self) -> None:
        """Mode-level thinking_mode takes precedence over archetype-level."""
        from agent_fox.engine.sdk_params import resolve_thinking

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        thinking_mode="disabled",
                        modes={"think": PerArchetypeConfig(thinking_mode="enabled", thinking_budget=16000)},
                    )
                }
            )
        )
        result = resolve_thinking(config, "reviewer", mode="think")
        assert result is not None
        assert result["type"] == "enabled"
        assert result["budget_tokens"] == 16000

    def test_mode_with_no_thinking_falls_back_to_archetype(self) -> None:
        """Mode with no thinking config falls back to archetype-level."""
        from agent_fox.engine.sdk_params import resolve_thinking

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        thinking_mode="adaptive",
                        thinking_budget=20000,
                        modes={},
                    )
                }
            )
        )
        result = resolve_thinking(config, "reviewer", mode="pre-review")
        assert result is not None
        assert result["type"] == "adaptive"


# ---------------------------------------------------------------------------
# TS-97-11: resolve_security_config With Empty Allowlist Mode
# Requirements: 97-REQ-4.4, 97-REQ-5.2
# ---------------------------------------------------------------------------


class TestResolveSecurityConfigWithMode:
    """Verify resolve_security_config respects mode-specific allowlist."""

    def test_mode_empty_allowlist_returns_security_config_with_empty_list(self) -> None:
        """TS-97-11: Mode with empty allowlist returns SecurityConfig(bash_allowlist=[])."""
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"reviewer": PerArchetypeConfig(modes={"pre-review": PerArchetypeConfig(allowlist=[])})}
            )
        )
        result = resolve_security_config(config, "reviewer", mode="pre-review")
        assert result is not None
        assert result.bash_allowlist == []

    def test_mode_allowlist_overrides_archetype_allowlist(self) -> None:
        """Mode-level allowlist takes precedence over archetype-level."""
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        allowlist=["ls", "cat", "git"],
                        modes={"restricted": PerArchetypeConfig(allowlist=["ls"])},
                    )
                }
            )
        )
        result = resolve_security_config(config, "reviewer", mode="restricted")
        assert result is not None
        assert result.bash_allowlist == ["ls"]

    def test_mode_without_allowlist_falls_back_to_archetype(self) -> None:
        """Mode with no allowlist falls back to archetype-level (TS-97-E6 related)."""
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "reviewer": PerArchetypeConfig(
                        allowlist=["ls", "cat"],
                        modes={"no-override": PerArchetypeConfig(max_turns=60)},
                    )
                }
            )
        )
        result = resolve_security_config(config, "reviewer", mode="no-override")
        assert result is not None
        assert result.bash_allowlist == ["ls", "cat"]


# ---------------------------------------------------------------------------
# TS-97-12: Security Hook Blocks All Bash With Empty Allowlist
# Requirement: 97-REQ-5.2
# ---------------------------------------------------------------------------


class TestSecurityHookWithEmptyAllowlist:
    """Verify hook blocks any Bash command when allowlist is empty."""

    def test_hook_blocks_ls_with_empty_allowlist(self) -> None:
        """TS-97-12: Hook with empty allowlist blocks 'ls'."""
        from agent_fox.security.security import make_pre_tool_use_hook

        hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
        result = hook(tool_name="Bash", tool_input={"command": "ls"})
        assert result["decision"] == "block"

    def test_hook_blocks_git_with_empty_allowlist(self) -> None:
        """Hook with empty allowlist blocks 'git status'."""
        from agent_fox.security.security import make_pre_tool_use_hook

        hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
        result = hook(tool_name="Bash", tool_input={"command": "git status"})
        assert result["decision"] == "block"

    def test_hook_allows_non_bash_tools(self) -> None:
        """Non-Bash tools pass through even with empty allowlist."""
        from agent_fox.security.security import make_pre_tool_use_hook

        hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
        result = hook(tool_name="Read", tool_input={"file_path": "/some/file"})
        assert result["decision"] == "allow"

    def test_hook_mode_parameter_accepted(self) -> None:
        """TS-97-5.1: make_pre_tool_use_hook mode parameter is accepted (if added)."""
        from agent_fox.security.security import make_pre_tool_use_hook

        # Per design, mode is resolved upstream — hook still takes SecurityConfig only.
        # This test verifies the hook blocks all Bash when SecurityConfig.bash_allowlist=[].
        hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
        result = hook(tool_name="Bash", tool_input={"command": "any_command"})
        assert result["decision"] == "block"


# ---------------------------------------------------------------------------
# TS-97-13: NodeSessionRunner Passes Mode
# Requirements: 97-REQ-5.3
# ---------------------------------------------------------------------------


class TestNodeSessionRunnerMode:
    """Verify NodeSessionRunner stores and uses mode for resolution."""

    def test_node_session_runner_accepts_mode_parameter(self) -> None:
        """TS-97-13: NodeSessionRunner accepts mode keyword argument."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="coder",
            mode="pre-review",
            knowledge_db=_MOCK_KB,
        )
        assert runner._mode == "pre-review"

    def test_node_session_runner_mode_defaults_to_none(self) -> None:
        """NodeSessionRunner mode defaults to None when not specified."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="coder",
            knowledge_db=_MOCK_KB,
        )
        assert runner._mode is None

    def test_node_session_runner_stores_mode(self) -> None:
        """TS-97-13: NodeSessionRunner stores mode as _mode attribute."""
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="coder",
            mode="drift-review",
            knowledge_db=_MOCK_KB,
        )
        assert runner._mode == "drift-review"


# ---------------------------------------------------------------------------
# Additional: clamp_instances with mode (97-REQ-4.5)
# ---------------------------------------------------------------------------


class TestClampInstancesWithMode:
    """Verify clamp_instances accepts optional mode parameter."""

    def test_coder_clamped_to_one_regardless_of_mode(self) -> None:
        """97-REQ-4.5: coder archetype always clamped to 1 regardless of mode."""
        from agent_fox.engine.sdk_params import clamp_instances

        result = clamp_instances("coder", 3, mode="fast")
        assert result == 1

    def test_non_coder_with_mode_still_clamped(self) -> None:
        """Non-coder archetype with mode is still clamped to max 5."""
        from agent_fox.engine.sdk_params import clamp_instances

        result = clamp_instances("reviewer", 10, mode="pre-review")
        assert result == 5

    def test_mode_none_same_as_no_mode(self) -> None:
        """mode=None behaves the same as omitting mode."""
        from agent_fox.engine.sdk_params import clamp_instances

        result_with_none = clamp_instances("coder", 3, mode=None)
        result_without = clamp_instances("coder", 3)
        assert result_with_none == result_without == 1


# ---------------------------------------------------------------------------
# TS-97-E5: None Mode Resolution Identity
# Requirement: 97-REQ-4.E1
# ---------------------------------------------------------------------------


class TestNoneModeResolutionIdentity:
    """Verify mode=None produces identical results to current behavior."""

    def test_resolve_model_tier_none_mode_same_as_no_mode(self) -> None:
        """TS-97-E5: resolve_model_tier(config, arch, mode=None) == resolve_model_tier(config, arch)."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig()
        result_with_none = resolve_model_tier(config, "coder", mode=None)
        result_without = resolve_model_tier(config, "coder")
        assert result_with_none == result_without

    def test_resolve_max_turns_none_mode_same_as_no_mode(self) -> None:
        """mode=None produces same result as current (modeless) API for resolve_max_turns."""
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig()
        result_with_none = resolve_max_turns(config, "coder", mode=None)
        result_without = resolve_max_turns(config, "coder")
        assert result_with_none == result_without

    def test_resolve_thinking_none_mode_same_as_no_mode(self) -> None:
        """mode=None produces same result as current (modeless) API for resolve_thinking."""
        from agent_fox.engine.sdk_params import resolve_thinking

        config = AgentFoxConfig()
        result_with_none = resolve_thinking(config, "coder", mode=None)
        result_without = resolve_thinking(config, "coder")
        assert result_with_none == result_without

    def test_resolve_security_config_none_mode_same_as_no_mode(self) -> None:
        """mode=None produces same result as current (modeless) API for resolve_security_config."""
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig()
        result_with_none = resolve_security_config(config, "coder", mode=None)
        result_without = resolve_security_config(config, "coder")
        assert result_with_none == result_without


# ---------------------------------------------------------------------------
# TS-97-E6: Mode Allowlist None Inherits Base
# Requirement: 97-REQ-5.E1
# ---------------------------------------------------------------------------


class TestModeAllowlistNoneInheritsBase:
    """Verify mode with None allowlist inherits base archetype allowlist."""

    def test_mode_with_none_allowlist_inherits_archetype_allowlist(self) -> None:
        """TS-97-E6: Mode with None allowlist uses archetype's allowlist.

        Uses maintainer:hunt as the concrete example (replaces triage which was
        removed in spec 100). maintainer:hunt has an explicit allowlist, and
        using a non-existent mode falls back to the base entry's allowlist via
        resolve_effective_config.
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config
        from agent_fox.engine.sdk_params import resolve_security_config

        # maintainer:hunt has allowlist=["ls", "cat", "git", "wc", "head", "tail"]
        config = AgentFoxConfig()
        entry = ARCHETYPE_REGISTRY["maintainer"]
        hunt_cfg = resolve_effective_config(entry, "hunt")
        assert hunt_cfg.default_allowlist is not None

        result = resolve_security_config(config, "maintainer", mode="hunt")
        # Should return maintainer:hunt allowlist
        assert result is not None
        assert set(result.bash_allowlist) == set(hunt_cfg.default_allowlist)

    def test_mode_with_none_allowlist_from_registry_mode_inherits(self) -> None:
        """Mode ModeConfig(allowlist=None) means inherit from base archetype."""

        from agent_fox.engine.sdk_params import resolve_security_config

        # Build a config where mode has no allowlist override
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={
                    "test_arch": PerArchetypeConfig(
                        allowlist=["ls", "cat"],
                        modes={"m": PerArchetypeConfig()},  # no allowlist set
                    )
                }
            )
        )
        result = resolve_security_config(config, "test_arch", mode="m")
        # Falls back to the archetype-level allowlist
        assert result is not None
        assert result.bash_allowlist == ["ls", "cat"]


# ---------------------------------------------------------------------------
# Integration Smoke Tests
# Test Spec: TS-97-SMOKE-1, TS-97-SMOKE-2
# Requirements: 97-REQ-5.3 (all resolution paths end-to-end)
# ---------------------------------------------------------------------------


class TestIntegrationSmoke:
    """End-to-end mode resolution smoke tests.

    These tests exercise the full resolution chain without mocking internal
    components — NodeSessionRunner through resolve_* functions through
    resolve_effective_config.

    Test Spec: TS-97-SMOKE-1, TS-97-SMOKE-2
    """

    def test_smoke1_node_mode_flows_to_model_resolution(self, monkeypatch: object) -> None:
        """TS-97-SMOKE-1: End-to-end mode resolution from NodeSessionRunner.

        Verifies that a mode-specific model tier override in the registry flows
        through NodeSessionRunner.__init__ → resolve_model_tier → resolve_effective_config
        to produce a mode-specific model ID.

        Must NOT be satisfied by mocking resolve_model_tier or resolve_effective_config.
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, ArchetypeEntry, ModeConfig
        from agent_fox.core.models import resolve_model
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        # Register a test archetype with a mode that overrides model_tier to SIMPLE.
        test_arch = ArchetypeEntry(
            name="test_smoke1",
            templates=[],
            default_model_tier="STANDARD",
            modes={"fast": ModeConfig(model_tier="SIMPLE")},
        )

        # Monkeypatch the registry at its canonical location (agent_fox.archetypes).
        # get_archetype() reads from this dict, so patching here covers all callers.
        patched_registry = {**ARCHETYPE_REGISTRY, "test_smoke1": test_arch}
        monkeypatch.setattr("agent_fox.archetypes.ARCHETYPE_REGISTRY", patched_registry)
        # Also patch the re-exported reference in session.archetypes (used by sdk_params).
        monkeypatch.setattr("agent_fox.session.archetypes.ARCHETYPE_REGISTRY", patched_registry)

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="test_smoke1",
            mode="fast",
            knowledge_db=_MOCK_KB,
        )

        expected_model_id = resolve_model("SIMPLE").model_id
        assert runner._resolved_model_id == expected_model_id

    def test_smoke2_empty_allowlist_mode_blocks_bash(self, monkeypatch: object) -> None:
        """TS-97-SMOKE-2: Security hook with mode having empty allowlist blocks all Bash.

        Verifies that a mode with allowlist=[] in the registry produces a hook
        that blocks every Bash command — exercises the full chain:
        NodeSessionRunner → resolve_security_config → make_pre_tool_use_hook.

        Must NOT be satisfied by mocking make_pre_tool_use_hook or
        build_effective_allowlist.
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, ArchetypeEntry, ModeConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        from agent_fox.security.security import make_pre_tool_use_hook

        # Register a test archetype with a mode that has no shell access.
        test_arch = ArchetypeEntry(
            name="test_smoke2",
            templates=[],
            default_model_tier="STANDARD",
            default_allowlist=["ls", "cat"],  # base has allowlist
            modes={"no-shell": ModeConfig(allowlist=[])},  # mode blocks all
        )

        patched_registry = {**ARCHETYPE_REGISTRY, "test_smoke2": test_arch}
        monkeypatch.setattr("agent_fox.archetypes.ARCHETYPE_REGISTRY", patched_registry)
        monkeypatch.setattr("agent_fox.session.archetypes.ARCHETYPE_REGISTRY", patched_registry)

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="test_smoke2",
            mode="no-shell",
            knowledge_db=_MOCK_KB,
        )

        # The resolved security config should have an empty allowlist.
        assert runner._resolved_security is not None
        assert runner._resolved_security.bash_allowlist == []

        # The hook created from that config should block all Bash commands.
        hook = make_pre_tool_use_hook(runner._resolved_security)
        result = hook(tool_name="Bash", tool_input={"command": "ls -la"})
        assert result["decision"] == "block"

    def test_smoke2_non_bash_tools_not_blocked(self, monkeypatch: object) -> None:
        """TS-97-SMOKE-2 corollary: Non-Bash tools are not affected by empty allowlist."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, ArchetypeEntry, ModeConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner
        from agent_fox.security.security import make_pre_tool_use_hook

        test_arch = ArchetypeEntry(
            name="test_smoke2b",
            templates=[],
            default_model_tier="STANDARD",
            modes={"no-shell": ModeConfig(allowlist=[])},
        )

        patched_registry = {**ARCHETYPE_REGISTRY, "test_smoke2b": test_arch}
        monkeypatch.setattr("agent_fox.archetypes.ARCHETYPE_REGISTRY", patched_registry)
        monkeypatch.setattr("agent_fox.session.archetypes.ARCHETYPE_REGISTRY", patched_registry)

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "s:0",
            config,
            archetype="test_smoke2b",
            mode="no-shell",
            knowledge_db=_MOCK_KB,
        )

        hook = make_pre_tool_use_hook(runner._resolved_security)
        # Non-Bash tools should not be blocked
        result = hook(tool_name="Read", tool_input={"file_path": "/tmp/foo"})
        # Should not return a block decision (None means allow)
        assert result is None or result.get("decision") != "block"
