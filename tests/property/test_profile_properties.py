"""Property tests for archetype profiles (spec 99).

Covers: TS-99-P1 through TS-99-P5
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

BUILTIN_ARCHETYPES = ["coder", "reviewer", "verifier", "maintainer"]


@given(st.sampled_from(BUILTIN_ARCHETYPES))
@settings(max_examples=4)
def test_layer_order(archetype: str) -> None:
    """TS-99-P1: Agent base always precedes profile precedes task context.

    Property: For any archetype, the three prompt layers appear in order.
    Requirement: 99-REQ-1.1
    """
    from agent_fox.session.prompt import build_system_prompt

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        profiles_dir = tmp_dir / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "agent.md").write_text("BASE_CONTEXT_CONTENT")
        marker = f"PROFILE_{archetype.upper()}_CONTENT"
        (profiles_dir / f"{archetype}.md").write_text(marker)

        prompt = build_system_prompt(
            "TASK_CONTEXT_MARKER",
            archetype=archetype,
            project_dir=tmp_dir,
        )

        assert "BASE_CONTEXT_CONTENT" in prompt
        assert marker in prompt
        assert "TASK_CONTEXT_MARKER" in prompt

        idx_base = prompt.index("BASE_CONTEXT_CONTENT")
        idx_profile = prompt.index(marker)
        idx_task = prompt.index("TASK_CONTEXT_MARKER")
        assert idx_base < idx_profile < idx_task
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@given(st.sampled_from(BUILTIN_ARCHETYPES))
@settings(max_examples=4)
def test_override_precedence(archetype: str) -> None:
    """TS-99-P2: Project profile always takes precedence over package default.

    Property: load_profile returns project content when both exist.
    Requirement: 99-REQ-1.2, 99-REQ-1.3
    """
    from agent_fox.session.profiles import load_profile

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        profiles_dir = tmp_dir / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / f"{archetype}.md").write_text(f"CUSTOM:{archetype}")

        content = load_profile(archetype, project_dir=tmp_dir)

        assert content.startswith(f"CUSTOM:{archetype}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@given(st.sampled_from(BUILTIN_ARCHETYPES))
@settings(max_examples=4)
def test_default_completeness(archetype: str) -> None:
    """TS-99-P3: Every built-in archetype has a non-empty default profile.

    Property: load_profile(name, project_dir=None) returns non-empty string.
    Requirement: 99-REQ-2.1
    """
    from agent_fox.session.profiles import load_profile

    content = load_profile(archetype, project_dir=None)

    assert len(content) > 0


def test_init_idempotence(tmp_path: Path) -> None:
    """TS-99-P4: Repeated init_profiles calls never overwrite existing files.

    Property: Pre-existing profile content is unchanged after multiple inits.
    Requirement: 99-REQ-3.2
    """
    from agent_fox.cli.init import init_profiles

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder.md").write_text("ORIGINAL")

    init_profiles(tmp_path)
    init_profiles(tmp_path)  # second call

    assert (profiles_dir / "coder.md").read_text() == "ORIGINAL"


@given(st.sampled_from(["coder", "verifier"]))
@settings(max_examples=2)
def test_permission_inheritance(preset: str) -> None:
    """TS-99-P5: Custom archetype inherits preset's permission allowlist.

    Property: Resolved entry has same allowlist as the preset archetype.
    Requirement: 99-REQ-4.2, 99-REQ-4.4

    Note: Uses only coder and verifier since reviewer/maintainer are added
    by later specs (97, 98, 100). The property holds for all presets once
    those archetypes are registered.
    """
    from agent_fox.archetypes import ARCHETYPE_REGISTRY, get_archetype
    from agent_fox.core.config import AgentFoxConfig

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        profiles_dir = tmp_dir / ".agent-fox" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "custom_arch.md").write_text("# Custom Arch Profile")

        cfg = AgentFoxConfig.model_validate(
            {
                "archetypes": {
                    "custom": {
                        "custom_arch": {"permissions": preset},
                    }
                }
            }
        )

        entry = get_archetype("custom_arch", project_dir=tmp_dir, config=cfg)
        preset_entry = ARCHETYPE_REGISTRY[preset]

        assert entry.default_allowlist == preset_entry.default_allowlist
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
