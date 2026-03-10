"""Tests for feature vector extraction.

Test Spec: TS-30-1, TS-30-E3, TS-30-P5
Requirements: 30-REQ-1.2, 30-REQ-1.E3
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_fox.routing.features import extract_features
from agent_fox.routing.types import FeatureVector
from hypothesis import given, settings
from hypothesis import strategies as st


class TestFeatureExtraction:
    """TS-30-1: Feature vector extraction from spec content."""

    def test_feature_extraction(self, spec_dir: Path) -> None:
        """TS-30-1: Verify feature extraction produces correct values.

        Requirement: 30-REQ-1.2
        """
        result = extract_features(spec_dir, task_group=2, archetype="coder")

        assert isinstance(result, FeatureVector)
        assert result.subtask_count == 4
        assert result.spec_word_count > 100  # ~150 words in spec
        assert result.has_property_tests is True
        assert result.edge_case_count == 2
        assert result.dependency_count == 2
        assert result.archetype == "coder"


class TestFeatureExtractionEdgeCases:
    """TS-30-E3: Bad spec directory produces default features."""

    def test_bad_spec_dir(self) -> None:
        """TS-30-E3: Non-existent spec directory returns defaults.

        Requirement: 30-REQ-1.E3
        """
        result = extract_features(Path("/nonexistent"), task_group=1, archetype="coder")

        assert result.subtask_count == 0
        assert result.spec_word_count == 0
        assert result.has_property_tests is False
        assert result.edge_case_count == 0
        assert result.dependency_count == 0
        assert result.archetype == "coder"


class TestFeatureDeterminism:
    """TS-30-P5: Feature extraction is deterministic."""

    @pytest.mark.property
    @given(
        task_group=st.integers(min_value=1, max_value=10),
        archetype=st.sampled_from(["coder", "skeptic", "verifier"]),
    )
    @settings(max_examples=20)
    def test_p5_determinism(
        self, spec_dir: Path, task_group: int, archetype: str
    ) -> None:
        """TS-30-P5: Two calls with identical inputs produce identical results.

        Requirement: 30-REQ-1.2
        """
        v1 = extract_features(spec_dir, task_group, archetype)
        v2 = extract_features(spec_dir, task_group, archetype)
        assert v1 == v2
