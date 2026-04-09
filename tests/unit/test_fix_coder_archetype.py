"""Tests for fix_coder archetype registration and fix_coding.md template.

Test Spec: TS-88-1 through TS-88-9, TS-88-E1, TS-88-E2
Requirements: 88-REQ-1.1 through 88-REQ-1.6, 88-REQ-1.E1,
              88-REQ-2.1 through 88-REQ-2.3, 88-REQ-2.E1, 88-REQ-3.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-88-1: fix_coding.md template exists and loads
# Requirement: 88-REQ-1.1
# ---------------------------------------------------------------------------


class TestFixCodingTemplateExists:
    """Verify the fix_coding.md template exists and can be loaded."""

    def test_template_loads_successfully(self) -> None:
        """_load_template("fix_coding.md") returns a non-empty string."""
        from agent_fox.session.prompt import _load_template

        result = _load_template("fix_coding.md")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_template_does_not_raise(self) -> None:
        """Loading fix_coding.md does not raise ConfigError."""
        from agent_fox.core.errors import ConfigError
        from agent_fox.session.prompt import _load_template

        try:
            _load_template("fix_coding.md")
        except ConfigError:
            raise AssertionError("fix_coding.md template not found; ConfigError raised")


# ---------------------------------------------------------------------------
# TS-88-2: fix_coding.md contains no .specs/ references
# Requirement: 88-REQ-1.2
# ---------------------------------------------------------------------------


class TestFixCodingNoSpecsReferences:
    """Verify the template has no .specs/ path references."""

    def test_no_specs_path_in_template(self) -> None:
        """Template does not contain the string '.specs/'."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert ".specs/" not in content

    def test_no_tasks_md_reference(self) -> None:
        """Template does not contain 'tasks.md'."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert "tasks.md" not in content


# ---------------------------------------------------------------------------
# TS-88-3: fix_coding.md includes nightshift commit format
# Requirement: 88-REQ-1.3
# ---------------------------------------------------------------------------


class TestFixCodingCommitFormat:
    """Verify the template instructs the agent to use the nightshift commit format."""

    def test_commit_format_pattern_present(self) -> None:
        """Template contains the 'fix(#' commit format pattern."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert "fix(#" in content

    def test_nightshift_in_commit_context(self) -> None:
        """Template contains 'nightshift' in the commit format context."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert "nightshift" in content


# ---------------------------------------------------------------------------
# TS-88-4: fix_coding.md includes git workflow instructions
# Requirement: 88-REQ-1.4
# ---------------------------------------------------------------------------


class TestFixCodingGitWorkflow:
    """Verify the template includes standard git workflow constraints."""

    def test_no_branch_switching_instruction(self) -> None:
        """Template instructs agent not to switch branches."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        content_lower = content.lower()
        # Must mention both "branch" and some prohibition
        assert "branch" in content_lower
        assert "do not" in content_lower or "never" in content_lower

    def test_conventional_commits_mentioned(self) -> None:
        """Template mentions conventional commits."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert "conventional commit" in content.lower()

    def test_no_co_authored_by(self) -> None:
        """Template instructs agent not to add Co-Authored-By lines."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert "Co-Authored-By" in content

    def test_no_push_to_remote(self) -> None:
        """Template instructs agent never to push to remote."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        content_lower = content.lower()
        assert "push" in content_lower


# ---------------------------------------------------------------------------
# TS-88-5: fix_coding.md includes quality gate instructions
# Requirement: 88-REQ-1.5
# ---------------------------------------------------------------------------


class TestFixCodingQualityGates:
    """Verify the template instructs the agent to run quality checks."""

    def test_quality_or_test_mentioned(self) -> None:
        """Template references quality gates or tests."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        content_lower = content.lower()
        assert "quality" in content_lower or "test" in content_lower

    def test_linter_mentioned(self) -> None:
        """Template references linter or lint."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        content_lower = content.lower()
        assert "linter" in content_lower or "lint" in content_lower


# ---------------------------------------------------------------------------
# TS-88-6: fix_coding.md omits session artifact instructions
# Requirement: 88-REQ-1.6
# ---------------------------------------------------------------------------


class TestFixCodingNoSessionArtifacts:
    """Verify the template does not instruct creation of session artifacts."""

    def test_no_session_summary_json(self) -> None:
        """Template does not reference .session-summary.json."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert ".session-summary.json" not in content

    def test_no_session_learnings_md(self) -> None:
        """Template does not reference .session-learnings.md."""
        from agent_fox.session.prompt import _load_template

        content = _load_template("fix_coding.md")
        assert ".session-learnings.md" not in content


# ---------------------------------------------------------------------------
# TS-88-7: fix_coder archetype is registered
# Requirement: 88-REQ-2.1
# ---------------------------------------------------------------------------


class TestFixCoderArchetypeRegistered:
    """Verify the archetype registry contains a fix_coder entry."""

    def test_fix_coder_entry_exists(self) -> None:
        """ARCHETYPE_REGISTRY contains 'fix_coder'."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "fix_coder" in ARCHETYPE_REGISTRY

    def test_fix_coder_template(self) -> None:
        """fix_coder entry has templates=['fix_coding.md']."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["fix_coder"]
        assert entry.templates == ["fix_coding.md"]


# ---------------------------------------------------------------------------
# TS-88-8: fix_coder defaults match coder
# Requirement: 88-REQ-2.2
# ---------------------------------------------------------------------------


class TestFixCoderDefaultsMatchCoder:
    """Verify fix_coder entry has the same defaults as coder."""

    def test_model_tier_matches_coder(self) -> None:
        """fix_coder.default_model_tier matches coder.default_model_tier."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_model_tier == coder.default_model_tier

    def test_max_turns_matches_coder(self) -> None:
        """fix_coder.default_max_turns matches coder.default_max_turns."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_max_turns == coder.default_max_turns

    def test_thinking_mode_matches_coder(self) -> None:
        """fix_coder.default_thinking_mode matches coder.default_thinking_mode."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_thinking_mode == coder.default_thinking_mode

    def test_thinking_budget_matches_coder(self) -> None:
        """fix_coder.default_thinking_budget matches coder.default_thinking_budget."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_thinking_budget == coder.default_thinking_budget


# ---------------------------------------------------------------------------
# TS-88-9: fix_coder is not task-assignable
# Requirement: 88-REQ-2.3
# ---------------------------------------------------------------------------


class TestFixCoderNotTaskAssignable:
    """Verify the fix_coder entry has task_assignable=False."""

    def test_task_assignable_is_false(self) -> None:
        """fix_coder entry has task_assignable=False."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["fix_coder"]
        assert entry.task_assignable is False


# ---------------------------------------------------------------------------
# TS-88-E1: Interpolation with adversarial spec_name
# Requirement: 88-REQ-1.E1
# ---------------------------------------------------------------------------


class TestFixCodingInterpolationEdge:
    """Verify the raw template has no .specs/ reference regardless of spec_name."""

    def test_raw_template_has_no_specs_reference(self) -> None:
        """The raw fix_coding.md template contains no .specs/ literal."""
        from agent_fox.session.prompt import _load_template

        template = _load_template("fix_coding.md")
        assert ".specs/" not in template


# ---------------------------------------------------------------------------
# TS-88-E2: get_archetype fallback for unknown archetype
# Requirement: 88-REQ-2.E1, 88-REQ-3.E1
# ---------------------------------------------------------------------------


class TestGetArchetypeFallback:
    """Verify get_archetype falls back to coder for unknown names."""

    def test_fallback_to_coder_when_fix_coder_missing(self) -> None:
        """If fix_coder is removed from registry, get_archetype returns coder."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, get_archetype

        saved = ARCHETYPE_REGISTRY.pop("fix_coder", None)
        try:
            entry = get_archetype("fix_coder")
            assert entry.name == "coder"
        finally:
            if saved is not None:
                ARCHETYPE_REGISTRY["fix_coder"] = saved

    def test_fallback_does_not_raise(self) -> None:
        """get_archetype('fix_coder') with missing entry does not raise."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, get_archetype

        saved = ARCHETYPE_REGISTRY.pop("fix_coder", None)
        try:
            result = get_archetype("fix_coder")
            assert result is not None
        finally:
            if saved is not None:
                ARCHETYPE_REGISTRY["fix_coder"] = saved
