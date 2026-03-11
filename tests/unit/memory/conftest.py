"""Fixtures for structured memory tests.

Provides sample Fact objects, temporary memory paths, and mock LLM responses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.memory.types import Fact

# -- Sample facts for testing ------------------------------------------------


def make_fact(
    *,
    id: str = "test-uuid-1",
    content: str = "Test fact content.",
    category: str = "pattern",
    spec_name: str = "01_core_foundation",
    keywords: list[str] | None = None,
    confidence: float = 0.9,
    created_at: str = "2026-03-01T10:00:00+00:00",
    supersedes: str | None = None,
) -> Fact:
    """Create a Fact with sensible defaults for testing."""
    return Fact(
        id=id,
        content=content,
        category=category,
        spec_name=spec_name,
        keywords=keywords if keywords is not None else ["test"],
        confidence=confidence,
        created_at=created_at,
        supersedes=supersedes,
    )


@pytest.fixture
def sample_fact() -> Fact:
    """A single sample fact with default values."""
    return make_fact()


@pytest.fixture
def sample_facts() -> list[Fact]:
    """Three sample facts with different spec names and categories."""
    return [
        make_fact(
            id="fact-1",
            content="Fact from spec_01.",
            category="gotcha",
            spec_name="spec_01",
            keywords=["pytest", "config"],
            created_at="2026-01-01T00:00:00+00:00",
        ),
        make_fact(
            id="fact-2",
            content="Fact from spec_02.",
            category="pattern",
            spec_name="spec_02",
            keywords=["testing", "mock"],
            created_at="2026-02-01T00:00:00+00:00",
        ),
        make_fact(
            id="fact-3",
            content="Fact from spec_03.",
            category="decision",
            spec_name="spec_03",
            keywords=["architecture", "design"],
            created_at="2026-03-01T00:00:00+00:00",
        ),
    ]


@pytest.fixture
def tmp_memory_path(tmp_path: Path) -> Path:
    """Return a path to a temporary memory.jsonl file (not yet created)."""
    return tmp_path / "memory.jsonl"


# -- Mock LLM responses for extraction tests --------------------------------

VALID_LLM_RESPONSE = """[
  {
    "content": "The pytest-asyncio plugin requires mode='auto' in pyproject.toml.",
    "category": "gotcha",
    "confidence": "high",
    "keywords": ["pytest", "asyncio", "configuration"]
  },
  {
    "content": "Using tmp_path fixture provides reliable filesystem isolation.",
    "category": "pattern",
    "confidence": "medium",
    "keywords": ["pytest", "tmp_path", "testing"]
  }
]"""

EMPTY_LLM_RESPONSE = "[]"

INVALID_JSON_LLM_RESPONSE = "not valid json {{"

UNKNOWN_CATEGORY_LLM_RESPONSE = """[
  {
    "content": "Some learning about testing.",
    "category": "unknown_cat",
    "confidence": "high",
    "keywords": ["testing"]
  }
]"""

# -- Markdown-fenced LLM responses ------------------------------------------

FENCED_JSON_LLM_RESPONSE = """```json
[
  {
    "content": "Always pin dependency versions in requirements.txt.",
    "category": "convention",
    "confidence": "high",
    "keywords": ["dependencies", "pinning"]
  }
]
```"""

FENCED_NO_LANG_LLM_RESPONSE = """```
[
  {
    "content": "Use structured logging for production services.",
    "category": "pattern",
    "confidence": "medium",
    "keywords": ["logging", "structured"]
  }
]
```"""

PROSE_WRAPPED_JSON_LLM_RESPONSE = """Here are the learnings I extracted:

[
  {
    "content": "Mock external APIs at the HTTP boundary.",
    "category": "pattern",
    "confidence": "high",
    "keywords": ["mocking", "api", "testing"]
  }
]

I hope this helps!"""
