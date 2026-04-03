"""Tests for duration preset configuration.

Test Spec: TS-41-9
Requirements: 41-REQ-3.1, 41-REQ-3.2
"""

from __future__ import annotations


class TestDurationPresets:
    """TS-41-9: Verify preset durations exist for all archetypes and tiers.

    Requirements: 41-REQ-3.1, 41-REQ-3.2
    """

    def test_all_archetypes_and_tiers_present(self) -> None:
        """Every archetype x tier combination has a positive integer preset."""
        from agent_fox.routing.duration import DURATION_PRESETS

        archetypes = [
            "coder",
            "skeptic",
            "oracle",
            "verifier",
            "librarian",
            "cartographer",
        ]
        tiers = ["STANDARD", "ADVANCED", "MAX"]

        for archetype in archetypes:
            assert archetype in DURATION_PRESETS, f"Missing archetype: {archetype}"
            for tier in tiers:
                assert tier in DURATION_PRESETS[archetype], f"Missing tier {tier} for archetype {archetype}"
                value = DURATION_PRESETS[archetype][tier]
                assert isinstance(value, int), f"Preset for {archetype}/{tier} is not int: {type(value)}"
                assert value > 0, f"Preset for {archetype}/{tier} must be positive: {value}"

    def test_default_duration_ms(self) -> None:
        """DEFAULT_DURATION_MS is 300,000 ms."""
        from agent_fox.routing.duration import DEFAULT_DURATION_MS

        assert DEFAULT_DURATION_MS == 300_000
