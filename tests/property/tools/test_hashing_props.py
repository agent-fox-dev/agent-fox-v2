"""Property tests for hashing module.

Test Spec: TS-29-P1 (determinism), TS-29-P2 (sensitivity)
Requirements: 29-REQ-5.1, 29-REQ-5.2, 29-REQ-5.3
"""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from agent_fox.tools.hashing import hash_line


class TestHashDeterminismProperty:
    """TS-29-P1: Same byte content always produces the same hash."""

    @given(content=st.binary(min_size=0, max_size=10000))
    def test_determinism(self, content: bytes) -> None:
        h1 = hash_line(content)
        h2 = hash_line(content)
        assert h1 == h2
        assert re.fullmatch(r"[0-9a-f]{16}", h1) is not None


class TestHashSensitivityProperty:
    """TS-29-P2: Different byte content produces different hashes."""

    @given(
        a=st.binary(min_size=1, max_size=1000),
        b=st.binary(min_size=1, max_size=1000),
    )
    def test_sensitivity(self, a: bytes, b: bytes) -> None:
        if a == b:
            return  # skip identical inputs
        assert hash_line(a) != hash_line(b)
