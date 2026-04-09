"""Tests for scope_guard.stub_patterns module.

Test Spec: TS-87-4, TS-87-E2, TS-87-P1
Requirements: 87-REQ-1.4, 87-REQ-1.E2
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_fox.scope_guard.models import Language
from agent_fox.scope_guard.stub_patterns import is_stub_body

# ---------------------------------------------------------------------------
# TS-87-4: Stub detection for Rust, Python, TypeScript/JavaScript
# Requirement: 87-REQ-1.4
# ---------------------------------------------------------------------------


class TestIsStubBodyAllLanguages:
    """TS-87-4: Verifies is_stub_body correctly identifies stub placeholders for each supported language."""

    def test_rust_todo(self) -> None:
        assert is_stub_body("todo!()", Language.RUST) is True

    def test_rust_unimplemented(self) -> None:
        assert is_stub_body("unimplemented!()", Language.RUST) is True

    def test_rust_panic_not_implemented(self) -> None:
        assert is_stub_body('panic!("not implemented")', Language.RUST) is True

    def test_rust_non_stub(self) -> None:
        assert is_stub_body("return 42", Language.RUST) is False

    def test_rust_todo_with_message(self) -> None:
        assert is_stub_body('todo!("implement later")', Language.RUST) is True

    def test_rust_unimplemented_with_message(self) -> None:
        assert is_stub_body('unimplemented!("not done")', Language.RUST) is True

    def test_python_raise_not_implemented_error(self) -> None:
        assert is_stub_body("raise NotImplementedError", Language.PYTHON) is True

    def test_python_raise_not_implemented_error_with_message(self) -> None:
        assert is_stub_body('raise NotImplementedError("todo")', Language.PYTHON) is True

    def test_python_pass(self) -> None:
        assert is_stub_body("pass", Language.PYTHON) is True

    def test_python_non_stub(self) -> None:
        assert is_stub_body("x = 1\nreturn x", Language.PYTHON) is False

    def test_typescript_throw_error(self) -> None:
        assert is_stub_body('throw new Error("not implemented")', Language.TYPESCRIPT) is True

    def test_typescript_non_stub(self) -> None:
        assert is_stub_body("console.log('hi')", Language.TYPESCRIPT) is False

    def test_javascript_throw_error(self) -> None:
        assert is_stub_body('throw new Error("not implemented")', Language.JAVASCRIPT) is True

    def test_javascript_non_stub(self) -> None:
        assert is_stub_body("console.log('hi')", Language.JAVASCRIPT) is False

    def test_stub_with_surrounding_whitespace(self) -> None:
        assert is_stub_body("  todo!()  ", Language.RUST) is True

    def test_stub_with_newlines(self) -> None:
        assert is_stub_body("\n  todo!()\n", Language.RUST) is True


# ---------------------------------------------------------------------------
# TS-87-E2: Stub with additional statements is classified as non-stub
# Requirement: 87-REQ-1.E2
# ---------------------------------------------------------------------------


class TestStubWithAdditionalStatements:
    """TS-87-E2: A todo!() preceded by setup logic is classified as non-stub."""

    def test_rust_todo_with_setup(self) -> None:
        body = "let x = setup();\ntodo!()"
        assert is_stub_body(body, Language.RUST) is False

    def test_python_raise_with_setup(self) -> None:
        body = "x = setup()\nraise NotImplementedError"
        assert is_stub_body(body, Language.PYTHON) is False

    def test_typescript_throw_with_setup(self) -> None:
        body = 'const x = setup();\nthrow new Error("not implemented")'
        assert is_stub_body(body, Language.TYPESCRIPT) is False

    def test_rust_todo_followed_by_code(self) -> None:
        body = "todo!()\nlet x = 1;"
        assert is_stub_body(body, Language.RUST) is False

    def test_multiple_stubs_is_non_stub(self) -> None:
        body = "todo!()\ntodo!()"
        assert is_stub_body(body, Language.RUST) is False


# ---------------------------------------------------------------------------
# TS-87-P1: Property — Stub Body Purity
# Property 1 from design.md
# Validates: 87-REQ-1.2, 87-REQ-1.4, 87-REQ-1.E2
# ---------------------------------------------------------------------------


# Known stub patterns per language
RUST_STUBS = [
    "todo!()",
    'todo!("msg")',
    "unimplemented!()",
    'unimplemented!("msg")',
    'panic!("not implemented")',
]

PYTHON_STUBS = [
    "raise NotImplementedError",
    'raise NotImplementedError("msg")',
    "pass",
]

TS_STUBS = [
    'throw new Error("not implemented")',
]

NON_STUB_CODE = st.sampled_from([
    "return 42",
    "let x = 1;\nx",
    "x = compute()\nreturn x",
    "console.log('hello')",
    "if True:\n    return 1",
    "for i in range(10):\n    pass",
    "match x { _ => 0 }",
])


class TestPropertyStubBodyPurity:
    """TS-87-P1: is_stub_body is True iff body is exactly one stub placeholder."""

    @pytest.mark.property
    @given(stub=st.sampled_from(RUST_STUBS), whitespace=st.sampled_from(["", " ", "\n", "  \n  "]))
    def test_rust_stubs_with_whitespace_are_stubs(self, stub: str, whitespace: str) -> None:
        body = whitespace + stub + whitespace
        assert is_stub_body(body, Language.RUST) is True

    @pytest.mark.property
    @given(stub=st.sampled_from(PYTHON_STUBS), whitespace=st.sampled_from(["", " ", "\n", "  \n  "]))
    def test_python_stubs_with_whitespace_are_stubs(self, stub: str, whitespace: str) -> None:
        body = whitespace + stub + whitespace
        assert is_stub_body(body, Language.PYTHON) is True

    @pytest.mark.property
    @given(stub=st.sampled_from(TS_STUBS), whitespace=st.sampled_from(["", " ", "\n", "  \n  "]))
    def test_ts_stubs_with_whitespace_are_stubs(self, stub: str, whitespace: str) -> None:
        body = whitespace + stub + whitespace
        assert is_stub_body(body, Language.TYPESCRIPT) is True

    @pytest.mark.property
    @given(non_stub=NON_STUB_CODE)
    def test_non_stub_code_is_not_stub_rust(self, non_stub: str) -> None:
        assert is_stub_body(non_stub, Language.RUST) is False

    @pytest.mark.property
    @given(
        stub=st.sampled_from(RUST_STUBS),
        prefix=st.sampled_from(["let x = 1;\n", "setup();\n", "// prep\nlet y = 2;\n"]),
    )
    def test_stub_with_prefix_is_non_stub(self, stub: str, prefix: str) -> None:
        body = prefix + stub
        assert is_stub_body(body, Language.RUST) is False

    @pytest.mark.property
    @given(
        stub=st.sampled_from(PYTHON_STUBS),
        suffix=st.sampled_from(["\nreturn x", "\nprint('done')", "\nx = 1"]),
    )
    def test_stub_with_suffix_is_non_stub(self, stub: str, suffix: str) -> None:
        body = stub + suffix
        assert is_stub_body(body, Language.PYTHON) is False
