"""Tests for scope_guard.stub_validator module.

Test Spec: TS-87-2, TS-87-20, TS-87-E1, TS-87-E3, TS-87-P2, TS-87-P3
Requirements: 87-REQ-1.2, 87-REQ-1.3, 87-REQ-1.E1, 87-REQ-1.E3
"""

from __future__ import annotations

import pytest

from agent_fox.scope_guard.models import (
    Deliverable,
    FileChange,
    Language,
    TaskGroup,
    ViolationRecord,
)
from agent_fox.scope_guard.stub_validator import validate_stubs

# ---------------------------------------------------------------------------
# TS-87-2: Post-session stub validation detects non-stub implementations
# Requirement: 87-REQ-1.2
# ---------------------------------------------------------------------------


class TestValidateStubsDetectsNonStub:
    """TS-87-2: validate_stubs returns violations for functions with non-stub bodies."""

    def test_detects_full_implementation(self) -> None:
        file_change = FileChange(
            file_path="src/validator.rs",
            language=Language.RUST,
            diff_text="fn validate() -> bool {\n    let x = compute();\n    x > 0\n}",
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("src/validator.rs", "validate", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], task_group)
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].function_id == "validate"
        assert result.violations[0].file_path == "src/validator.rs"

    def test_passes_for_stub_only_code(self) -> None:
        file_change = FileChange(
            file_path="src/validator.rs",
            language=Language.RUST,
            diff_text="fn validate() -> bool {\n    todo!()\n}",
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("src/validator.rs", "validate", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], task_group)
        assert result.passed is True
        assert len(result.violations) == 0


# ---------------------------------------------------------------------------
# TS-87-20: Stub violation record includes prompt directive presence
# Requirement: 87-REQ-5.3
# ---------------------------------------------------------------------------


class TestViolationIncludesPromptDirective:
    """TS-87-20: ViolationRecord includes whether stub constraint directive was present."""

    def test_violation_with_directive_present(self) -> None:
        violation = ViolationRecord(
            file_path="src/foo.rs",
            function_id="bar",
            body_preview="let x = 1; x",
            prompt_directive_present=True,
        )
        assert violation.prompt_directive_present is True

    def test_violation_with_directive_absent(self) -> None:
        violation = ViolationRecord(
            file_path="src/foo.rs",
            function_id="bar",
            body_preview="let x = 1; x",
            prompt_directive_present=False,
        )
        assert violation.prompt_directive_present is False

    def test_violation_with_directive_unknown(self) -> None:
        violation = ViolationRecord(
            file_path="src/foo.rs",
            function_id="bar",
            body_preview="let x = 1; x",
            prompt_directive_present=None,
        )
        assert violation.prompt_directive_present is None


# ---------------------------------------------------------------------------
# TS-87-E1: Inline test code excluded from stub enforcement
# Requirement: 87-REQ-1.E1
# ---------------------------------------------------------------------------


class TestInlineTestCodeExcluded:
    """TS-87-E1: Stub enforcement only applies outside test-attributed blocks."""

    def test_rust_cfg_test_function_excluded(self) -> None:
        # A file with both production code (non-stub) and test code (non-stub)
        # Only the production function should be a violation
        file_change = FileChange(
            file_path="src/validator.rs",
            language=Language.RUST,
            diff_text=(
                "fn validate() -> bool {\n    let x = compute();\n    x > 0\n}\n\n"
                "#[cfg(test)]\nmod tests {\n    fn test_validate() {\n        assert!(true);\n    }\n}"
            ),
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("src/validator.rs", "validate", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], task_group)
        # test_validate inside #[cfg(test)] should not be in violations
        violation_ids = {v.function_id for v in result.violations}
        assert "test_validate" not in violation_ids

    def test_python_test_function_excluded(self) -> None:
        file_change = FileChange(
            file_path="test_helpers.py",
            language=Language.PYTHON,
            diff_text=(
                "def helper() -> int:\n    return compute()\n\ndef test_helper() -> None:\n    assert helper() == 42\n"
            ),
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("test_helpers.py", "helper", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], task_group)
        violation_ids = {v.function_id for v in result.violations}
        assert "test_helper" not in violation_ids


# ---------------------------------------------------------------------------
# TS-87-E3: Unsupported language files skipped with warning
# Requirement: 87-REQ-1.E3
# ---------------------------------------------------------------------------


class TestUnsupportedLanguageSkipped:
    """TS-87-E3: Unsupported language files are logged and skipped."""

    def test_unknown_language_skipped(self) -> None:
        file_change = FileChange(
            file_path="src/module.go",
            language=Language.UNKNOWN,
            diff_text="func validate() bool {\n    return true\n}",
        )
        task_group = TaskGroup(
            number=1,
            spec_number=4,
            archetype="test-writing",
            deliverables=[Deliverable("src/module.go", "validate", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], task_group)
        assert "src/module.go" in result.skipped_files


# ---------------------------------------------------------------------------
# TS-87-P2: Property — Test Block Exclusion
# Property 2 from design.md
# Validates: 87-REQ-1.E1
# ---------------------------------------------------------------------------


class TestPropertyTestBlockExclusion:
    """TS-87-P2: Functions inside test blocks never appear in violations."""

    @pytest.mark.property
    def test_test_block_functions_never_in_violations(self) -> None:
        # A Rust file with a function inside #[cfg(test)] — should not be a violation
        file_change = FileChange(
            file_path="src/lib.rs",
            language=Language.RUST,
            diff_text=(
                "fn production_fn() -> i32 {\n    compute()\n}\n\n"
                "#[cfg(test)]\nmod tests {\n"
                "    fn test_fn() {\n        assert_eq!(1, 1);\n    }\n"
                "}\n"
            ),
        )
        tg = TaskGroup(
            number=1,
            spec_number=1,
            archetype="test-writing",
            deliverables=[Deliverable("src/lib.rs", "production_fn", 1)],
            depends_on=[],
        )
        result = validate_stubs([file_change], tg)
        for violation in result.violations:
            # No violation should be for a test block function
            assert "test_fn" != violation.function_id


# ---------------------------------------------------------------------------
# TS-87-P3: Property — Stub Validation Completeness
# Property 3 from design.md
# Validates: 87-REQ-1.2, 87-REQ-1.3
# ---------------------------------------------------------------------------


class TestPropertyStubValidationCompleteness:
    """TS-87-P3: All non-stub non-test functions appear in violations."""

    @pytest.mark.property
    def test_all_non_stub_non_test_functions_are_violations(self) -> None:
        # File with one stub and one non-stub (both outside test block)
        file_change = FileChange(
            file_path="src/engine.rs",
            language=Language.RUST,
            diff_text=("fn stub_fn() {\n    todo!()\n}\n\nfn impl_fn() -> i32 {\n    let x = 1;\n    x + 1\n}\n"),
        )
        tg = TaskGroup(
            number=1,
            spec_number=1,
            archetype="test-writing",
            deliverables=[
                Deliverable("src/engine.rs", "stub_fn", 1),
                Deliverable("src/engine.rs", "impl_fn", 1),
            ],
            depends_on=[],
        )
        result = validate_stubs([file_change], tg)
        violation_ids = {v.function_id for v in result.violations}
        # impl_fn should be a violation (non-stub, non-test)
        assert "impl_fn" in violation_ids
        # stub_fn should NOT be a violation
        assert "stub_fn" not in violation_ids
