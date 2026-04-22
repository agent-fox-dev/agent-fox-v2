"""Quality gate hunt category.

Discovers project quality checks (tests, linters, type checkers, build tools)
from project configuration files, executes them, and uses AI analysis to
produce structured findings for each failing check.

Requirements: 67-REQ-1.1, 67-REQ-1.2, 67-REQ-1.E1, 67-REQ-2.1, 67-REQ-2.2,
              67-REQ-2.3, 67-REQ-2.4, 67-REQ-2.E1, 67-REQ-2.E2, 67-REQ-3.1,
              67-REQ-3.2, 67-REQ-3.3, 67-REQ-3.4, 67-REQ-3.E1, 67-REQ-4.1,
              67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_fox.fix.checks import CheckCategory, CheckDescriptor, detect_checks
from agent_fox.nightshift.categories.base import BaseHuntCategory
from agent_fox.nightshift.finding import Finding

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)

# Maximum characters of check output to include per check to avoid token exhaustion
MAX_OUTPUT_CHARS = 8000

# Severity mapping from CheckCategory to Finding severity
SEVERITY_MAP: dict[CheckCategory, str] = {
    CheckCategory.TEST: "critical",
    CheckCategory.BUILD: "critical",
    CheckCategory.TYPE: "major",
    CheckCategory.LINT: "minor",
}

QUALITY_GATE_PROMPT = """\
You are a code quality analyst. The following quality checks have failed in the
project. Analyse the failure output and produce a JSON array with exactly one
object per failing check.

Important context for type-checker and linter errors in test files:
- Errors in test files (paths starting with "tests/") that are tagged
  "[TEST FILE — may be intentional]" are often DELIBERATE. Tests frequently use
  constructs like `pytest.raises(ImportError)` to verify that removed modules
  stay removed. A type-checker like mypy will flag the import as missing, but
  the test is working as designed.
- Do NOT create findings for import-not-found or similar errors in test files
  unless there is additional evidence that the test itself is broken (e.g. the
  test runner also reports it as a failure).
- When in doubt about a test-file error, omit it from your analysis rather than
  flagging it as a real issue.

Each object must have these fields:
- "check_name": the name of the check (e.g. "pytest", "ruff", "mypy")
- "title": a short descriptive title of the failure (under 80 chars)
- "description": root-cause analysis of why the check failed
- "suggested_fix": actionable steps to fix the failures
- "affected_files": list of file paths mentioned in the output (may be empty)

Return ONLY the JSON array, no other text.

Failing checks:
{static_output}
"""


_TEST_FILE_ERROR_RE = re.compile(
    r"^(tests/.+?:\d+:.*(?:error|warning).*)$",
    re.MULTILINE,
)


def _annotate_test_file_errors(output: str) -> str:
    """Append '[TEST FILE — may be intentional]' to errors in test files.

    Matches lines like:
        tests/unit/security/test_relocation.py:58: error: Cannot find ...
    and annotates them so the LLM prompt can recognise intentional errors.
    """

    def _tag(m: re.Match[str]) -> str:
        return m.group(1) + "  [TEST FILE — may be intentional]"

    return _TEST_FILE_ERROR_RE.sub(_tag, output)


def _format_failures(
    failures: list[tuple[CheckDescriptor, str, int]],
) -> str:
    """Format failure records into a structured string for AI analysis."""
    sections: list[str] = []
    for check, output, exit_code in failures:
        truncated = output[:MAX_OUTPUT_CHARS]
        if check.category in (CheckCategory.TYPE, CheckCategory.LINT):
            truncated = _annotate_test_file_errors(truncated)
        section = f"=== {check.name} ({check.category}) ===\nExit code: {exit_code}\nOutput:\n{truncated}"
        sections.append(section)
    return "\n\n".join(sections)


def _mechanical_finding(check: CheckDescriptor, output: str) -> Finding:
    """Create a mechanical fallback Finding when AI analysis is unavailable."""
    severity = SEVERITY_MAP.get(check.category, "major")
    return Finding(
        category="quality_gate",
        title=f"Quality gate failure: {check.name}",
        description=output[:MAX_OUTPUT_CHARS],
        severity=severity,
        affected_files=[],
        suggested_fix=f"Fix the {check.name} failures reported above.",
        evidence=output[:MAX_OUTPUT_CHARS],
        group_key=f"quality_gate:{check.name}",
    )


class QualityGateCategory(BaseHuntCategory):
    """Detects failing quality gates (tests, linters, type checkers, builds).

    Requirements: 67-REQ-1.1, 67-REQ-2.1, 67-REQ-3.1, 67-REQ-4.1
    """

    _name = "quality_gate"
    _prompt_template = QUALITY_GATE_PROMPT

    # Track failure records between phases so AI phase has access to raw output
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._failures: list[tuple[CheckDescriptor, str, int]] = []

    async def detect(
        self,
        project_root: Path,
        config: object,
        *,
        sink: SinkDispatcher | None = None,
        run_id: str = "",
    ) -> list[Finding]:
        """Override to catch detect_checks() exceptions at the top level.

        Requirements: 67-REQ-1.E1
        """
        timeout = getattr(getattr(config, "night_shift", None), "quality_gate_timeout", 600)
        self._timeout = timeout
        self._failures = []
        try:
            return await super().detect(project_root, config, sink=sink, run_id=run_id)
        except Exception:
            logger.warning(
                "quality_gate category failed during detection",
                exc_info=True,
            )
            return []

    async def _run_static_tool(self, project_root: Path) -> str:
        """Detect and run quality checks, returning formatted failure output.

        Requirements: 67-REQ-1.1, 67-REQ-1.2, 67-REQ-2.1, 67-REQ-2.2,
                      67-REQ-2.3, 67-REQ-2.4, 67-REQ-2.E1, 67-REQ-2.E2
        """
        try:
            checks = detect_checks(project_root)
        except Exception:
            logger.warning(
                "quality_gate: detect_checks() raised an exception",
                exc_info=True,
            )
            raise  # Re-raise to be caught by detect() override

        if not checks:
            logger.debug("quality_gate: no checks detected, skipping")
            return ""

        timeout = getattr(self, "_timeout", 600)
        failures: list[tuple[CheckDescriptor, str, int]] = []

        for check in checks:
            logger.debug("quality_gate: running check '%s'", check.name)
            try:
                result = subprocess.run(
                    check.command,
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                combined = (result.stdout or "") + (result.stderr or "")
                if result.returncode != 0:
                    failures.append((check, combined, result.returncode))
            except subprocess.TimeoutExpired:
                logger.warning(
                    "quality_gate: check '%s' timed out after %ds",
                    check.name,
                    timeout,
                )
                timeout_msg = f"timeout: check '{check.name}' timed out after {timeout}s"
                failures.append((check, timeout_msg, -1))

        self._failures = failures

        if not failures:
            return ""

        return _format_failures(failures)

    async def _run_ai_analysis(
        self,
        project_root: Path,
        static_output: str,
        *,
        sink: SinkDispatcher | None = None,
        run_id: str = "",
    ) -> list[Finding]:
        """Analyse failure output with AI, returning one Finding per check.

        Requirements: 67-REQ-3.1, 67-REQ-3.2, 67-REQ-3.3, 67-REQ-3.4, 67-REQ-3.E1
        """
        if not static_output:
            return []

        # Build lookup for raw output by check name
        failure_by_name: dict[str, tuple[CheckDescriptor, str, int]] = {
            check.name: (check, output, exit_code) for check, output, exit_code in self._failures
        }

        _model_id = "claude-opus-4-5"

        try:
            from agent_fox.core.json_extraction import extract_json_array

            backend = self._backend
            owns_backend = backend is None
            if owns_backend:
                from agent_fox.core.client import create_async_anthropic_client

                backend = create_async_anthropic_client()
            # At this point backend is always non-None: either passed in (not None)
            # or just created above. Assert narrows the type for mypy.
            assert backend is not None

            try:
                prompt = QUALITY_GATE_PROMPT.format(static_output=static_output)
                response = await backend.messages.create(
                    model=_model_id,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )

                # Emit cost for this auxiliary AI call (91-REQ-4.4)
                from agent_fox.core.config import PricingConfig
                from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost

                emit_auxiliary_cost(sink, run_id, "quality_gate", response, _model_id, PricingConfig())

                response_text = response.content[0].text  # type: ignore[union-attr]

                items = extract_json_array(response_text)
                if items is None:
                    raise ValueError("AI returned unparseable JSON")
            finally:
                if owns_backend:
                    await backend.close()

            findings: list[Finding] = []
            for item in items:
                check_name = item.get("check_name", "unknown")
                lookup = failure_by_name.get(check_name)
                if lookup is None:
                    # Check name not found; use fallback severity
                    severity = "major"
                    raw_output = ""
                    check_desc = None
                else:
                    check_desc, raw_output, _ = lookup
                    severity = SEVERITY_MAP.get(check_desc.category, "major")

                finding = Finding(
                    category="quality_gate",
                    title=item.get("title", f"Quality gate failure: {check_name}"),
                    description=item.get("description", raw_output[:MAX_OUTPUT_CHARS]),
                    severity=severity,
                    affected_files=item.get("affected_files", []),
                    suggested_fix=item.get("suggested_fix", ""),
                    evidence=raw_output[:MAX_OUTPUT_CHARS],
                    group_key=f"quality_gate:{check_name}",
                )
                findings.append(finding)

            return findings

        except Exception as _exc:
            logger.warning(
                "quality_gate: AI analysis failed, falling back to mechanical findings",
                exc_info=True,
            )
            # Emit session.fail for the failed auxiliary AI call (91-REQ-4.5)
            from agent_fox.nightshift.cost_helpers import emit_auxiliary_cost_fail

            emit_auxiliary_cost_fail(sink, run_id, "quality_gate", _exc, _model_id)
            # Mechanical fallback: one Finding per failure
            return [_mechanical_finding(check, output) for check, output, _ in self._failures]
