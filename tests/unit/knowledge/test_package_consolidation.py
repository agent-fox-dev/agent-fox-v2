"""Tests for package consolidation.

Covers module existence, deletion, re-exports, stale imports.

Test Spec: TS-39-1, TS-39-2, TS-39-3, TS-39-15
Requirements: 39-REQ-1.1, 39-REQ-1.2, 39-REQ-1.3, 39-REQ-1.4, 39-REQ-1.5,
              39-REQ-1.E1, 39-REQ-5.1, 39-REQ-5.3
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest


class TestModuleExistence:
    """TS-39-1: Assert consolidated modules are importable with expected symbols."""

    def test_facts_module(self) -> None:
        """agent_fox.knowledge.facts contains Fact, Category, ConfidenceLevel, etc."""
        from agent_fox.knowledge.facts import (
            CONFIDENCE_MAP,
            DEFAULT_CONFIDENCE,
            Category,
            ConfidenceLevel,
            Fact,
            parse_confidence,
        )

        assert Fact is not None
        assert Category is not None
        assert ConfidenceLevel is not None
        assert parse_confidence is not None
        assert isinstance(CONFIDENCE_MAP, dict)
        assert isinstance(DEFAULT_CONFIDENCE, float)

    def test_store_module(self) -> None:
        """agent_fox.knowledge.store contains MemoryStore, load funcs, etc."""
        from agent_fox.knowledge.store import (
            DEFAULT_MEMORY_PATH,
            MemoryStore,
            append_facts,
            export_facts_to_jsonl,
            load_all_facts,
            load_facts_by_spec,
            write_facts,
        )

        assert MemoryStore is not None
        assert load_all_facts is not None
        assert load_facts_by_spec is not None
        assert append_facts is not None
        assert write_facts is not None
        assert export_facts_to_jsonl is not None
        assert DEFAULT_MEMORY_PATH is not None

    def test_filtering_module(self) -> None:
        """agent_fox.knowledge.filtering contains select_relevant_facts."""
        from agent_fox.knowledge.filtering import select_relevant_facts

        assert select_relevant_facts is not None

    def test_rendering_module(self) -> None:
        """agent_fox.knowledge.rendering contains render_summary."""
        from agent_fox.knowledge.rendering import render_summary

        assert render_summary is not None

    def test_extraction_module(self) -> None:
        """agent_fox.knowledge.extraction contains extract_facts."""
        from agent_fox.knowledge.extraction import extract_facts

        assert extract_facts is not None

    def test_compaction_module(self) -> None:
        """agent_fox.knowledge.compaction contains compact."""
        from agent_fox.knowledge.compaction import compact

        assert compact is not None

    def test_state_machine_module(self) -> None:
        """agent_fox.knowledge.state_machine contains KnowledgeStateMachine."""
        from agent_fox.knowledge.state_machine import KnowledgeStateMachine

        assert KnowledgeStateMachine is not None


class TestPackageDeletion:
    """TS-39-2: Assert agent_fox.memory package no longer exists."""

    def test_import_memory_raises(self) -> None:
        """import agent_fox.memory raises ImportError."""
        # Remove from sys.modules cache if present
        for key in list(sys.modules):
            if key.startswith("agent_fox.memory"):
                del sys.modules[key]

        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.memory")

    def test_import_memory_types_raises(self) -> None:
        """from agent_fox.memory.types import Fact raises ImportError."""
        for key in list(sys.modules):
            if key.startswith("agent_fox.memory"):
                del sys.modules[key]

        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("agent_fox.memory.types")


class TestNoStaleImports:
    """TS-39-15: No remaining imports from agent_fox.memory in the codebase."""

    def test_no_stale_imports_in_agent_fox(self) -> None:
        """grep for 'from agent_fox.memory' in agent_fox/ returns nothing."""
        result = subprocess.run(
            ["grep", "-r", "from agent_fox.memory", "agent_fox/"],
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "", (
            f"Found stale imports from agent_fox.memory:\n{result.stdout}"
        )

    def test_no_stale_imports_in_tests(self) -> None:
        """grep for 'from agent_fox.memory' in tests/ returns nothing."""
        result = subprocess.run(
            [
                "grep",
                "-rI",
                "--include=*.py",
                "--exclude=test_package_consolidation.py",
                "from agent_fox.memory",
                "tests/",
            ],
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "", (
            f"Found stale imports from agent_fox.memory:\n{result.stdout}"
        )
