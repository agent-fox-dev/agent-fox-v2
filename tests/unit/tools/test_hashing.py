"""Hashing module unit tests.

Test Spec: TS-29-15 (xxh3_64 format), TS-29-16 (deterministic),
           TS-29-17 (different content), TS-29-E13 (blake2b fallback)
Requirements: 29-REQ-5.1, 29-REQ-5.2, 29-REQ-5.3, 29-REQ-5.E1
"""

from __future__ import annotations

import re
import sys
from unittest import mock


class TestHashFormat:
    """TS-29-15: hash_line produces 16-char lowercase hex strings."""

    def test_xxh3_format(self) -> None:
        from agent_fox.tools.hashing import hash_line

        h = hash_line(b"hello world\n")
        assert len(h) == 16
        assert re.fullmatch(r"[0-9a-f]{16}", h) is not None

    def test_empty_bytes(self) -> None:
        from agent_fox.tools.hashing import hash_line

        h = hash_line(b"")
        assert len(h) == 16
        assert re.fullmatch(r"[0-9a-f]{16}", h) is not None


class TestHashDeterminism:
    """TS-29-16: Same input produces same hash."""

    def test_deterministic(self) -> None:
        from agent_fox.tools.hashing import hash_line

        assert hash_line(b"test\n") == hash_line(b"test\n")

    def test_deterministic_multiline(self) -> None:
        from agent_fox.tools.hashing import hash_line

        content = b"line one\nline two\n"
        assert hash_line(content) == hash_line(content)


class TestHashSensitivity:
    """TS-29-17: Different inputs produce different hashes."""

    def test_different_content(self) -> None:
        from agent_fox.tools.hashing import hash_line

        assert hash_line(b"aaa\n") != hash_line(b"aab\n")

    def test_with_without_newline(self) -> None:
        from agent_fox.tools.hashing import hash_line

        assert hash_line(b"test") != hash_line(b"test\n")


class TestBlake2bFallback:
    """TS-29-E13: Falls back to blake2b when xxhash is unavailable."""

    def test_blake2b_fallback(self) -> None:
        # We need to remove xxhash from sys.modules and make it unimportable,
        # then reimport hashing to trigger fallback.
        import importlib

        # Save original module state
        original_modules = {}
        for key in list(sys.modules.keys()):
            if "xxhash" in key or "agent_fox.tools.hashing" in key:
                original_modules[key] = sys.modules.pop(key)

        try:
            with mock.patch.dict(sys.modules, {"xxhash": None}):
                # Force reimport of hashing module
                import agent_fox.tools.hashing as hashing_mod

                importlib.reload(hashing_mod)

                h = hashing_mod.hash_line(b"test\n")
                assert len(h) == 16
                assert re.fullmatch(r"[0-9a-f]{16}", h) is not None
        finally:
            # Restore original modules
            for key in list(sys.modules.keys()):
                if "agent_fox.tools.hashing" in key:
                    sys.modules.pop(key, None)
            sys.modules.update(original_modules)
