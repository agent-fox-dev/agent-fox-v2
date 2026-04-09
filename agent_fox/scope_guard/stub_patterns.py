"""Language-specific stub placeholder patterns and test-block detection rules.

Requirements: 87-REQ-1.4, 87-REQ-1.E1, 87-REQ-1.E2
"""

from __future__ import annotations

import re

from agent_fox.scope_guard.models import Language


def is_stub_body(body: str, language: Language) -> bool:
    """Check if a function body is a stub placeholder.

    Returns True iff the body, after stripping comments and whitespace,
    consists entirely of a single recognized stub placeholder for the language.
    """
    raise NotImplementedError


def detect_language(file_path: str) -> Language:
    """Detect programming language from file extension."""
    raise NotImplementedError


def get_stub_patterns(language: Language) -> list[re.Pattern[str]]:
    """Return compiled regex patterns for stub placeholders in the given language."""
    raise NotImplementedError


def is_test_block(body: str, file_path: str, language: Language) -> bool:
    """Determine if a code block is inside a test-attributed region."""
    raise NotImplementedError
