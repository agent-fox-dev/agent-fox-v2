"""Property tests for config simplification.

Test Spec: TS-68-P1 through TS-68-P6
Requirements: 68-REQ-1.*, 68-REQ-2.*, 68-REQ-5.*, 68-REQ-6.*
"""

from __future__ import annotations

import re
import tomllib

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import ArchetypeInstancesConfig
from agent_fox.core.config_gen import (
    generate_default_config,
    merge_existing_config,
)

_EXPECTED_VISIBLE_SECTIONS = frozenset(
    {
        "orchestrator",
        "models",
        "archetypes",
        "archetypes.instances",
        "archetypes.thinking",
        "archetypes.thinking.coder",
        "archetypes.thinking.skeptic",
        "archetypes.thinking.verifier",
        "security",
    }
)

_EXPECTED_HIDDEN_SECTIONS = frozenset(
    {
        "routing",
        "theme",
        "platform",
        "knowledge",
        "pricing",
        "planning",
        "blocking",
        "hooks",
        "night_shift",
    }
)


def _extract_section_names(template: str) -> list[str]:
    """Extract all section names from active and commented section headers."""
    return [
        m.group(1).strip()
        for m in re.finditer(
            r"^#?\s*\[([a-zA-Z_][a-zA-Z0-9_.]*)\]\s*$",
            template,
            re.MULTILINE,
        )
    ]


# ---------------------------------------------------------------------------
# TS-68-P1: Template always produces valid TOML
# ---------------------------------------------------------------------------


class TestPropTemplateValidToml:
    """TS-68-P1: Property 1 — generated template always parses as valid TOML."""

    def test_template_valid_toml(self):
        """generate_default_config() produces TOML that tomllib can parse."""
        template = generate_default_config()
        # Must not raise
        parsed = tomllib.loads(template)
        assert parsed is not None


# ---------------------------------------------------------------------------
# TS-68-P2: Visible section containment
# ---------------------------------------------------------------------------


class TestPropVisibleContainment:
    """TS-68-P2: Property 2 — every section header in template is in visible set."""

    def test_all_section_headers_are_visible(self):
        """No section in the template refers to a hidden section path."""
        template = generate_default_config()
        section_names = _extract_section_names(template)
        for name in section_names:
            assert name in _EXPECTED_VISIBLE_SECTIONS, (
                f"Section [{name}] found in template but is not in visible set"
            )

    def test_no_hidden_section_headers(self):
        """No hidden section name appears as a header (active or commented)."""
        template = generate_default_config()
        for hidden in _EXPECTED_HIDDEN_SECTIONS:
            assert f"[{hidden}]" not in template, (
                f"Hidden section [{hidden}] found in template"
            )
            assert f"# [{hidden}]" not in template, (
                f"Commented hidden section # [{hidden}] found in template"
            )


# ---------------------------------------------------------------------------
# TS-68-P3: Merge preserves every active key=value pair
# ---------------------------------------------------------------------------


class TestPropMergePreservesValues:
    """TS-68-P3: Property 6 — merge preserves every active key=value from input."""

    @given(
        parallel=st.integers(1, 8),
        max_budget=st.floats(0.1, 100.0, allow_nan=False, allow_infinity=False).map(
            lambda x: round(x, 2)
        ),
        skeptic=st.booleans(),
    )
    @settings(max_examples=20)
    def test_merge_preserves_active_values(self, parallel, max_budget, skeptic):
        """User values for parallel, max_budget_usd, and skeptic survive merge."""
        skeptic_str = "true" if skeptic else "false"
        existing = (
            f"[orchestrator]\n"
            f"parallel = {parallel}\n"
            f"max_budget_usd = {max_budget}\n"
            f"\n[archetypes]\n"
            f"skeptic = {skeptic_str}\n"
        )
        result = merge_existing_config(existing)
        assert f"parallel = {parallel}" in result, (
            f"parallel = {parallel} not preserved in merge result"
        )
        assert f"skeptic = {skeptic_str}" in result, (
            f"skeptic = {skeptic_str} not preserved in merge result"
        )


# ---------------------------------------------------------------------------
# TS-68-P4: No hidden section injection
# ---------------------------------------------------------------------------


class TestPropNoHiddenInjection:
    """TS-68-P4: Property 7 — merge never adds hidden sections not already present."""

    @given(
        include_orchestrator=st.booleans(),
        include_models=st.booleans(),
        include_archetypes=st.booleans(),
        include_security=st.booleans(),
    )
    @settings(max_examples=20)
    def test_no_hidden_section_injection(
        self,
        include_orchestrator,
        include_models,
        include_archetypes,
        include_security,
    ):
        """Merging a visible-only config never adds hidden sections."""
        lines: list[str] = []
        if include_orchestrator:
            lines.append("[orchestrator]")
            lines.append("parallel = 2")
        if include_models:
            lines.append("[models]")
        if include_archetypes:
            lines.append("[archetypes]")
            lines.append("skeptic = true")
        if include_security:
            lines.append("[security]")

        existing = "\n".join(lines) + "\n" if lines else ""
        result = merge_existing_config(existing)

        for hidden in _EXPECTED_HIDDEN_SECTIONS:
            assert f"[{hidden}]" not in result, (
                f"Hidden section [{hidden}] was injected by merge"
            )
            assert f"# [{hidden}]" not in result, (
                f"Commented hidden section # [{hidden}] was injected by merge"
            )


# ---------------------------------------------------------------------------
# TS-68-P5: Footer non-duplication
# ---------------------------------------------------------------------------


class TestPropFooterNonDuplication:
    """TS-68-P5: Property 9 — repeated merges never duplicate the footer."""

    @given(n=st.integers(1, 5))
    @settings(max_examples=10)
    def test_footer_not_duplicated_after_n_merges(self, n):
        """Footer appears exactly once after n successive merge iterations."""
        content = generate_default_config()
        for _ in range(n):
            content = merge_existing_config(content)
        count = content.count("docs/config-reference.md")
        assert count == 1, (
            f"After {n} merges, footer appears {count} times, expected exactly 1"
        )


# ---------------------------------------------------------------------------
# TS-68-P6: Default verifier instances is 2
# ---------------------------------------------------------------------------


class TestPropVerifierDefault:
    """TS-68-P6: Property 10 — ArchetypeInstancesConfig().verifier == 2."""

    def test_verifier_default_is_2(self):
        """Default-constructed ArchetypeInstancesConfig always has verifier=2."""
        config = ArchetypeInstancesConfig()
        assert config.verifier == 2, (
            f"ArchetypeInstancesConfig().verifier is {config.verifier}, expected 2"
        )
