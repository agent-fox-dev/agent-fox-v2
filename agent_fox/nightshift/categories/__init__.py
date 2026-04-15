"""Built-in hunt category implementations.

Each category follows a two-phase detection pattern:
1. Static tooling (linters, test runners, dependency checkers)
2. AI-powered analysis using the static tool output

Requirements: 61-REQ-3.1, 61-REQ-4.1, 61-REQ-4.2, 61-REQ-4.3
"""

from agent_fox.nightshift.categories.base import BaseHuntCategory
from agent_fox.nightshift.categories.builtins import (
    DeadCodeCategory,
    DependencyFreshnessCategory,
    DeprecatedAPICategory,
    DocumentationDriftCategory,
    LinterDebtCategory,
    TestCoverageCategory,
    TodoFixmeCategory,
)
from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

__all__ = [
    "BaseHuntCategory",
    "DeadCodeCategory",
    "DependencyFreshnessCategory",
    "DeprecatedAPICategory",
    "DocumentationDriftCategory",
    "LinterDebtCategory",
    "QualityGateCategory",
    "TestCoverageCategory",
    "TodoFixmeCategory",
]
