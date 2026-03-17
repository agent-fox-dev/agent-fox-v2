"""Tests for oracle archetype registry and config enablement.

Test Spec: TS-32-1, TS-32-2, TS-32-E1
Requirements: 32-REQ-1.1, 32-REQ-1.2, 32-REQ-1.3, 32-REQ-1.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-32-1: Oracle Archetype Registry Entry
# Requirements: 32-REQ-1.1, 32-REQ-1.3
# ---------------------------------------------------------------------------


class TestOracleRegistryEntry:
    """Verify the oracle entry exists in the archetype registry with correct fields."""

    def test_oracle_registry_entry(self) -> None:
        """TS-32-1: Oracle entry has correct name, injection, model tier, etc."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        assert "oracle" in ARCHETYPE_REGISTRY
        entry = ARCHETYPE_REGISTRY["oracle"]
        assert entry.name == "oracle"
        assert entry.injection == "auto_pre"
        assert entry.task_assignable is True
        assert entry.default_model_tier == "STANDARD"
        assert "oracle.md" in entry.templates
        assert set(entry.default_allowlist) == {
            "ls",
            "cat",
            "git",
            "grep",
            "find",
            "head",
            "tail",
            "wc",
        }


# ---------------------------------------------------------------------------
# TS-32-2: Oracle Enabled via Config
# Requirement: 32-REQ-1.2
# ---------------------------------------------------------------------------


class TestOracleEnabledConfig:
    """Verify oracle is recognized as enabled when config sets oracle=True."""

    def test_oracle_enabled_config(self) -> None:
        """TS-32-2: _is_archetype_enabled returns True when oracle=True."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import is_archetype_enabled as _is_archetype_enabled

        config = ArchetypesConfig(oracle=True)
        assert _is_archetype_enabled("oracle", config) is True

    def test_oracle_enabled_by_default(self) -> None:
        """Oracle is enabled by default."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import is_archetype_enabled as _is_archetype_enabled

        config = ArchetypesConfig()
        assert _is_archetype_enabled("oracle", config) is True


# ---------------------------------------------------------------------------
# TS-32-E1: Oracle Disabled
# Requirement: 32-REQ-1.E1
# ---------------------------------------------------------------------------


class TestOracleDisabled:
    """No oracle nodes when oracle is disabled."""

    def test_oracle_disabled(self) -> None:
        """TS-32-E1: No oracle nodes injected when oracle=False."""
        from pathlib import Path

        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph
        from agent_fox.spec.discovery import SpecInfo
        from agent_fox.spec.parser import TaskGroupDef

        config = ArchetypesConfig(oracle=False)
        specs = [
            SpecInfo(
                name="spec",
                prefix=0,
                path=Path(".specs/spec"),
                has_tasks=True,
                has_prd=False,
            )
        ]
        task_groups = {
            "spec": [
                TaskGroupDef(
                    number=1,
                    title="T1",
                    optional=False,
                    completed=False,
                    subtasks=(),
                    body="",
                ),
            ]
        }

        graph = build_graph(specs, task_groups, [], archetypes_config=config)
        oracle_nodes = [n for n in graph.nodes.values() if n.archetype == "oracle"]
        assert len(oracle_nodes) == 0
