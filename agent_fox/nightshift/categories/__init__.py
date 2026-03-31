"""Built-in hunt category implementations.

Each category follows a two-phase detection pattern:
1. Static tooling (linters, test runners, dependency checkers)
2. AI-powered analysis using the static tool output

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from agent_fox.nightshift.categories.base import BaseHuntCategory
from agent_fox.nightshift.categories.dead_code import DeadCodeCategory
from agent_fox.nightshift.categories.dependency_freshness import (
    DependencyFreshnessCategory,
)
from agent_fox.nightshift.categories.deprecated_api import DeprecatedAPICategory
from agent_fox.nightshift.categories.documentation_drift import (
    DocumentationDriftCategory,
)
from agent_fox.nightshift.categories.linter_debt import LinterDebtCategory
from agent_fox.nightshift.categories.test_coverage import TestCoverageCategory
from agent_fox.nightshift.categories.todo_fixme import TodoFixmeCategory

__all__ = [
    "BaseHuntCategory",
    "DeadCodeCategory",
    "DependencyFreshnessCategory",
    "DeprecatedAPICategory",
    "DocumentationDriftCategory",
    "LinterDebtCategory",
    "TestCoverageCategory",
    "TodoFixmeCategory",
]
