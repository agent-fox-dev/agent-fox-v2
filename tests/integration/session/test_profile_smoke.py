"""Integration smoke tests for archetype profiles (spec 99).

Traces execution paths from design.md end-to-end with real function calls.
No mocking of load_profile, build_system_prompt, init_profiles, or
get_archetype.

Test Spec: TS-99-SMOKE-1, TS-99-SMOKE-2, TS-99-SMOKE-3
Requirements: 99-REQ-1.1, 99-REQ-1.2, 99-REQ-3.1, 99-REQ-4.1, 99-REQ-4.2,
              99-REQ-4.4, 99-REQ-5.1, 99-REQ-5.2
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# TS-99-SMOKE-1: Prompt assembly with project profile
# Execution Path 1 from design.md
# Requirements: 99-REQ-1.1, 99-REQ-1.2, 99-REQ-1.3
# ---------------------------------------------------------------------------


class TestPromptWithProjectProfile:
    """Smoke test: end-to-end 3-layer prompt assembly with project-level profile.

    Must NOT satisfy with mocking load_profile or build_system_prompt.
    """

    def test_project_profile_overrides_default(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-1: Prompt contains project profile content, not default.

        Verifies the full path:
          NodeSessionRunner._build_prompts → build_system_prompt → load_profile
          → reads project .agent-fox/profiles/coder.md → returns custom content
          → concatenated into prompt in layer order.
        """
        from agent_fox.session.prompt import build_system_prompt

        # Setup: project agent_base and custom coder profile
        base_content = "PROJECT RULES FOR SMOKE TEST"
        profile_content = "CUSTOM CODER IDENTITY FOR SMOKE TEST"

        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "agent_base.md").write_text(base_content, encoding="utf-8")
        (profiles_dir / "coder.md").write_text(profile_content, encoding="utf-8")

        task_context = "TASK CONTEXT MARKER"

        # Trigger: real build_system_prompt, real load_profile
        prompt = build_system_prompt(
            context=task_context,
            archetype="coder",
            project_dir=tmp_path,
        )

        # Expected: all three layers present in order
        assert base_content in prompt, "Layer 1 (agent_base) missing from prompt"
        assert profile_content in prompt, "Layer 2 (profile) missing from prompt"
        assert task_context in prompt, "Layer 3 (task context) missing from prompt"

        # Verify order: agent_base < profile < task context
        idx_base = prompt.index(base_content)
        idx_profile = prompt.index(profile_content)
        idx_task = prompt.index(task_context)
        assert idx_base < idx_profile, "agent_base must appear before profile"
        assert idx_profile < idx_task, "Profile must appear before task context"

    def test_default_agent_base_always_loads(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-1 edge: Package-default agent_base loads when no project override.

        Requirement: 99-REQ-1.E1
        """
        from agent_fox.session.prompt import build_system_prompt

        # No project-level agent_base — package default should load
        profile_content = "CODER IDENTITY CUSTOM"
        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "coder.md").write_text(profile_content, encoding="utf-8")

        prompt = build_system_prompt(
            context="some task context",
            archetype="coder",
            project_dir=tmp_path,
        )

        assert len(prompt) > 0
        assert profile_content in prompt
        # Package-default agent_base content should be present
        assert "agent-fox session agent" in prompt


# ---------------------------------------------------------------------------
# TS-99-SMOKE-2: Custom archetype session
# Execution Path 3 from design.md
# Requirements: 99-REQ-4.1, 99-REQ-4.2, 99-REQ-4.4
# ---------------------------------------------------------------------------


class TestCustomArchetypeSession:
    """Smoke test: end-to-end custom archetype resolution and prompt assembly.

    Must NOT satisfy with mocking get_archetype or load_profile.
    """

    def test_custom_archetype_inherits_coder_permissions(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-2: Custom archetype gets coder permissions from config.

        Verifies the full path:
          get_archetype("deployer") → no registry entry → has_custom_profile
          → True → _resolve_custom_preset → "coder" → returns coder entry
          with name="deployer".
        """
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, get_archetype
        from agent_fox.core.config import AgentFoxConfig

        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "deployer.md").write_text("# Deployer Profile", encoding="utf-8")

        cfg = AgentFoxConfig.model_validate(
            {
                "archetypes": {
                    "custom": {
                        "deployer": {"permissions": "coder"},
                    }
                }
            }
        )

        # Real get_archetype — no mocking
        entry = get_archetype("deployer", project_dir=tmp_path, config=cfg)
        coder = ARCHETYPE_REGISTRY["coder"]

        assert entry.default_allowlist == coder.default_allowlist, "Custom archetype should inherit coder allowlist"

    def test_custom_archetype_prompt_uses_custom_profile(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-2: Prompt for custom archetype contains custom profile content.

        Verifies the full path:
          build_system_prompt("deployer", project_dir) → load_profile("deployer")
          → finds deployer.md in project → returns content → included in prompt.
        """
        from agent_fox.session.prompt import build_system_prompt

        profiles_dir = tmp_path / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        deployer_content = "# Deployer Profile\nDeploy all the things."
        (profiles_dir / "deployer.md").write_text(deployer_content, encoding="utf-8")

        # Real build_system_prompt — no mocking
        prompt = build_system_prompt(
            context="deployment task context",
            archetype="deployer",
            project_dir=tmp_path,
        )

        assert "Deployer Profile" in prompt, "Deployer profile content should appear in prompt"
        assert "deployment task context" in prompt, "Task context should appear in prompt"


# ---------------------------------------------------------------------------
# TS-99-SMOKE-3: Init then load
# Execution Path 4 + Path 2 from design.md
# Requirements: 99-REQ-3.1, 99-REQ-5.1, 99-REQ-5.2
# ---------------------------------------------------------------------------


class TestInitThenLoad:
    """Smoke test: init creates profiles that are then loadable.

    Must NOT satisfy with mocking init_profiles or load_profile.
    """

    def test_init_profiles_then_load_returns_default_content(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-3: init_profiles creates files; load_profile reads them.

        Verifies the full chain:
          init_profiles(tmp) → copies _templates/profiles/coder.md to disk
          → load_profile("coder", project_dir=tmp) → finds project file
          → returns same content as package default.
        """
        from agent_fox.cli.init import init_profiles
        from agent_fox.session.profiles import load_profile

        # Empty project dir — no .agent-fox/ exists
        assert not (tmp_path / ".agent-fox").exists()

        # Real init_profiles — no mocking
        created_paths = init_profiles(project_dir=tmp_path)

        # Directory must be created
        assert (tmp_path / ".agent-fox" / "profiles").is_dir()

        # All built-in profiles created
        assert len(created_paths) >= 4
        names = {p.name for p in created_paths}
        for archetype in ("coder.md", "reviewer.md", "verifier.md", "maintainer.md"):
            assert archetype in names, f"{archetype} not created by init_profiles"

        # Real load_profile — project file should match package default
        loaded = load_profile("coder", project_dir=tmp_path)
        default = load_profile("coder", project_dir=None)

        assert loaded == default, "Profile loaded from project dir should match package default after init"

    def test_init_profiles_idempotent(self, tmp_path: Path) -> None:
        """TS-99-SMOKE-3 + TS-99-P4: Second init call preserves existing files.

        Requirement: 99-REQ-3.2
        """
        from agent_fox.cli.init import init_profiles
        from agent_fox.session.profiles import load_profile

        # First init
        init_profiles(project_dir=tmp_path)

        # Mutate coder.md to simulate customization
        coder_path = tmp_path / ".agent-fox" / "profiles" / "coder.md"
        custom_content = "MY CUSTOM CODER PROFILE"
        coder_path.write_text(custom_content, encoding="utf-8")

        # Second init — must NOT overwrite coder.md
        second_created = init_profiles(project_dir=tmp_path)

        assert coder_path.read_text(encoding="utf-8") == custom_content, (
            "Second init_profiles call must not overwrite existing coder.md"
        )
        # coder.md should NOT appear in the second created list
        assert "coder.md" not in {p.name for p in second_created}, (
            "coder.md must not be listed as created on second init call"
        )

        # load_profile returns the customized content (project overrides default)
        loaded = load_profile("coder", project_dir=tmp_path)
        assert loaded == custom_content
