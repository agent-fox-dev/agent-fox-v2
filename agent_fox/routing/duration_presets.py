"""Configurable default duration estimates per archetype and complexity tier.

Provides preset durations used when historical execution data is insufficient
for duration prediction.

Requirements: 39-REQ-1.3
"""

from __future__ import annotations

# Archetype -> tier -> estimated duration in milliseconds.
# Conservative estimates: better to overestimate (task starts earlier)
# than to underestimate.
DURATION_PRESETS: dict[str, dict[str, int]] = {
    "coder": {
        "STANDARD": 180_000,  # 3 minutes
        "ADVANCED": 600_000,  # 10 minutes
        "MAX": 1_200_000,  # 20 minutes
    },
    "skeptic": {
        "STANDARD": 120_000,  # 2 minutes
        "ADVANCED": 300_000,  # 5 minutes
        "MAX": 600_000,  # 10 minutes
    },
    "oracle": {
        "STANDARD": 90_000,  # 1.5 minutes
        "ADVANCED": 180_000,  # 3 minutes
        "MAX": 300_000,  # 5 minutes
    },
    "verifier": {
        "STANDARD": 180_000,  # 3 minutes
        "ADVANCED": 600_000,  # 10 minutes
        "MAX": 1_200_000,  # 20 minutes
    },
    "librarian": {
        "STANDARD": 120_000,  # 2 minutes
        "ADVANCED": 300_000,  # 5 minutes
        "MAX": 600_000,  # 10 minutes
    },
    "cartographer": {
        "STANDARD": 120_000,  # 2 minutes
        "ADVANCED": 300_000,  # 5 minutes
        "MAX": 600_000,  # 10 minutes
    },
}

# Fallback when archetype/tier combination is not in DURATION_PRESETS.
DEFAULT_DURATION_MS: int = 300_000  # 5 minutes
