"""Property tests for outline tool.

Test Spec: TS-29-P6 (Python completeness)
Requirements: 29-REQ-1.1, 29-REQ-1.4
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


def _python_identifier() -> st.SearchStrategy[str]:
    """Generate valid Python identifiers (lowercase, 3-10 chars)."""
    return st.from_regex(r"[a-z][a-z0-9_]{2,9}", fullmatch=True)


@given(
    names=st.lists(
        _python_identifier(),
        min_size=1,
        max_size=10,
        unique=True,
    ),
    use_class=st.lists(st.booleans(), min_size=1, max_size=10),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_python_completeness(
    names: list[str], use_class: list[bool], tmp_path: Path
) -> None:
    """TS-29-P6: All top-level def/class declarations are detected in Python files.

    For any Python file with N declarations (1-10), generated with random
    valid names, fox_outline returns at least N symbols with matching names.
    """
    from agent_fox.tools.outline import fox_outline
    from agent_fox.tools.types import OutlineResult

    # Pad use_class to match names length
    flags = (use_class * ((len(names) // len(use_class)) + 1))[: len(names)]

    # Generate Python source
    source_lines: list[str] = []
    for name, is_class in zip(names, flags):
        if is_class:
            source_lines.append(f"class {name}:")
            source_lines.append("    pass")
            source_lines.append("")
        else:
            source_lines.append(f"def {name}():")
            source_lines.append("    pass")
            source_lines.append("")

    source = "\n".join(source_lines) + "\n"

    # Write to temp file (use a unique name to avoid collisions)
    file_path = tmp_path / "generated.py"
    file_path.write_text(source)

    result = fox_outline(str(file_path))
    assert isinstance(result, OutlineResult)

    found_names = {s.name for s in result.symbols if s.kind != "import_block"}
    expected_names = set(names)
    assert expected_names.issubset(found_names), (
        f"Missing symbols: {expected_names - found_names}"
    )
