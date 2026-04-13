"""Unit tests for default profile files (spec 99).

Covers: TS-99-4, TS-99-5
"""

from __future__ import annotations

BUILTIN_ARCHETYPES = ["coder", "reviewer", "verifier", "maintainer"]


def test_defaults_exist() -> None:
    """TS-99-4: All built-in archetypes have default profiles.

    Requirement: 99-REQ-2.1, 99-REQ-2.3
    """
    from agent_fox.session.profiles import load_profile

    for name in BUILTIN_ARCHETYPES:
        content = load_profile(name, project_dir=None)
        assert len(content) > 0, f"No default profile for {name!r}"


def test_profile_structure() -> None:
    """TS-99-5: Default profiles contain 4 required sections.

    Requirement: 99-REQ-2.2
    """
    from agent_fox.session.profiles import load_profile

    for name in BUILTIN_ARCHETYPES:
        content = load_profile(name, project_dir=None)
        assert "## Identity" in content, f"{name}: missing Identity section"
        assert "## Rules" in content, f"{name}: missing Rules section"
        assert "## Focus" in content, f"{name}: missing Focus section"
        assert "## Output" in content, f"{name}: missing Output section"
