"""Multi-language entity graph analyzer package.

Exports the LanguageAnalyzer protocol, LanguageRegistry, and all
public registry functions for use by the static analysis orchestrator.

Requirements: 102-REQ-1.1, 102-REQ-1.2, 102-REQ-1.3, 102-REQ-1.4
"""

from agent_fox.knowledge.lang.base import LanguageAnalyzer
from agent_fox.knowledge.lang.registry import (
    LanguageRegistry,
    _scan_files,
    detect_languages,
    get_default_registry,
)

__all__ = [
    "LanguageAnalyzer",
    "LanguageRegistry",
    "detect_languages",
    "get_default_registry",
    "_scan_files",
]
