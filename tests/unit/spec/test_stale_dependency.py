"""Unit tests for stale-dependency validation and auto-fix.

Test Spec: TS-21-1 through TS-21-18
Requirements: 21-REQ-1.*, 21-REQ-2.*, 21-REQ-3.*, 21-REQ-4.*, 21-REQ-5.*
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.validator import Finding, sort_findings

# -- Constants ----------------------------------------------------------------

_MOCK_CLIENT = "agent_fox.spec.validator.create_async_anthropic_client"


# -- Helpers ------------------------------------------------------------------


def _write_prd(tmp_path: Path, relationship_text: str) -> Path:
    """Write a prd.md with an alt-format dependency table."""
    content = (
        "# PRD: Test\n\n"
        "## Dependencies\n\n"
        "| Spec | From Group | To Group | Relationship |\n"
        "|------|-----------|----------|---------------|\n"
        f"| 01_core | 1 | 1 | {relationship_text} |\n"
    )
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(content)
    return prd_path


def _write_prd_multi_upstream(tmp_path: Path) -> Path:
    """Write a prd.md referencing two different upstream specs."""
    content = (
        "# PRD: Test\n\n"
        "## Dependencies\n\n"
        "| Spec | From Group | To Group | Relationship |\n"
        "|------|-----------|----------|---------------|\n"
        "| 01_core | 1 | 1 | Uses `Config` for settings |\n"
        "| 02_store | 1 | 2 | Uses `Store` for persistence |\n"
    )
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(content)
    return prd_path


def _write_prd_no_backticks(tmp_path: Path) -> Path:
    """Write a prd.md with plain-text Relationship cells (no backticks)."""
    content = (
        "# PRD: Test\n\n"
        "## Dependencies\n\n"
        "| Spec | From Group | To Group | Relationship |\n"
        "|------|-----------|----------|---------------|\n"
        "| 01_core | 1 | 1 | General configuration support |\n"
    )
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(content)
    return prd_path


def _make_spec(
    name: str,
    path: Path,
    has_prd: bool = True,
) -> SpecInfo:
    """Create a SpecInfo for testing."""
    return SpecInfo(
        name=name,
        prefix=int(name.split("_")[0]),
        path=path,
        has_tasks=True,
        has_prd=has_prd,
    )


def _make_mock_ai_response(results: list[dict]) -> MagicMock:
    """Create a mock AI response with structured JSON results."""
    response_text = json.dumps({"results": results})
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_text)]
    return mock_response


# -- TS-21-1: Extract backtick identifiers from Relationship text -------------


class TestExtractBacktickIdentifiers:
    """TS-21-1: Verify backtick-delimited tokens are extracted.

    Requirement: 21-REQ-1.1
    """

    def test_extracts_two_identifiers(self, tmp_path: Path) -> None:
        """Two backtick-delimited tokens produce two DependencyRef objects."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(
            tmp_path,
            "Uses `config.Config` for settings and `store.Store` for persistence",
        )
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)
        ids = [r.identifier for r in refs]

        assert len(refs) == 2
        assert "config.Config" in ids
        assert "store.Store" in ids

    def test_declaring_spec_set(self, tmp_path: Path) -> None:
        """DependencyRef.declaring_spec is set to the calling spec name."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(tmp_path, "Uses `Config` for settings")
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)

        assert refs[0].declaring_spec == "my_spec"

    def test_upstream_spec_set(self, tmp_path: Path) -> None:
        """DependencyRef.upstream_spec is set from the Spec column."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(tmp_path, "Uses `Config` for settings")
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)

        assert refs[0].upstream_spec == "01_core"


# -- TS-21-2: Strip trailing parentheses from identifiers --------------------


class TestStripTrailingParentheses:
    """TS-21-2: Verify `Delete()` becomes `Delete` after normalization.

    Requirement: 21-REQ-1.2
    """

    def test_parentheses_stripped(self, tmp_path: Path) -> None:
        """Trailing parentheses are removed from identifiers."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(
            tmp_path,
            "Calls `store.Store.Delete()` to remove",
        )
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)

        assert refs[0].identifier == "store.Store.Delete"


# -- TS-21-3: Preserve dotted paths ------------------------------------------


class TestPreserveDottedPaths:
    """TS-21-3: Verify dotted identifiers are preserved as-is.

    Requirement: 21-REQ-1.3
    """

    def test_dotted_path_preserved(self, tmp_path: Path) -> None:
        """Dotted paths remain unchanged."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(
            tmp_path,
            "Uses `store.SnippetStore.Delete`",
        )
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)

        assert refs[0].identifier == "store.SnippetStore.Delete"


# -- TS-21-4: Skip rows with no backtick tokens ------------------------------


class TestSkipRowsNoBacticks:
    """TS-21-4: Verify rows without backtick-delimited tokens produce nothing.

    Requirement: 21-REQ-1.E1
    """

    def test_no_backticks_returns_empty(self, tmp_path: Path) -> None:
        """Plain-text Relationship produces no DependencyRef objects."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd_no_backticks(tmp_path)
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)

        assert len(refs) == 0


# -- TS-21-5: Standard library tokens are extracted ---------------------------


class TestStdlibTokensExtracted:
    """TS-21-5: Verify standard library references are still extracted.

    Requirement: 21-REQ-1.E2
    """

    def test_stdlib_extracted(self, tmp_path: Path) -> None:
        """Standard library tokens like `slog` and `context.Context` are extracted."""
        from agent_fox.spec.validator import extract_relationship_identifiers

        _write_prd(
            tmp_path,
            "Uses `slog` for logging and `context.Context` for cancellation",
        )
        prd_path = tmp_path / "prd.md"

        refs = extract_relationship_identifiers("my_spec", prd_path)
        ids = [r.identifier for r in refs]

        assert "slog" in ids
        assert "context.Context" in ids


# -- TS-21-6: AI validates identifiers against design.md ----------------------


class TestAIValidatesFound:
    """TS-21-6: Verify AI cross-reference produces no findings for found identifiers.

    Requirements: 21-REQ-2.1, 21-REQ-2.3
    """

    @pytest.mark.asyncio
    async def test_found_identifier_no_findings(self) -> None:
        """Identifiers found in design produce no findings."""
        from agent_fox.spec.validator import (
            DependencyRef,
            validate_dependency_interfaces,
        )

        ref = DependencyRef(
            declaring_spec="my_spec",
            upstream_spec="01_core",
            identifier="Config",
            raw_relationship="Uses `Config` for settings",
        )

        mock_response = _make_mock_ai_response(
            [
                {
                    "identifier": "Config",
                    "found": True,
                    "explanation": "Defined as a dataclass",
                    "suggestion": None,
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await validate_dependency_interfaces(
                "01_core", "# Design\n\nConfig is a dataclass.", [ref], "STANDARD"
            )

            assert len(findings) == 0


# -- TS-21-7: AI flags unresolved identifiers ---------------------------------


class TestAIFlagsUnresolved:
    """TS-21-7: Verify unresolved identifiers produce Warning findings.

    Requirements: 21-REQ-2.4, 21-REQ-2.5
    """

    @pytest.mark.asyncio
    async def test_unfound_produces_warning(self) -> None:
        """Unresolved identifier produces a warning finding."""
        from agent_fox.spec.validator import (
            DependencyRef,
            validate_dependency_interfaces,
        )

        ref = DependencyRef(
            declaring_spec="my_spec",
            upstream_spec="01_core",
            identifier="SnippetStore",
            raw_relationship="Uses `SnippetStore`",
        )

        mock_response = _make_mock_ai_response(
            [
                {
                    "identifier": "SnippetStore",
                    "found": False,
                    "explanation": "Design defines Store, not SnippetStore",
                    "suggestion": "Did you mean Store?",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await validate_dependency_interfaces(
                "01_core", "# Design\n\nStore is the main type.", [ref], "STANDARD"
            )

            assert len(findings) == 1
            assert findings[0].severity == "warning"
            assert findings[0].rule == "stale-dependency"
            assert "SnippetStore" in findings[0].message
            assert "Store" in findings[0].message


# -- TS-21-8: Missing design.md skips validation ------------------------------


class TestMissingDesignSkips:
    """TS-21-8: Verify no findings when upstream spec has no design.md.

    Requirement: 21-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_missing_design_no_findings(self, tmp_path: Path) -> None:
        """Missing design.md produces no findings and no AI call."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        # Create spec with prd.md referencing 01_core, but 01_core has no design.md
        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd(spec_dir, "Uses `Config` for settings")

        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        # No design.md created

        specs = [_make_spec("10_downstream", spec_dir)]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await run_stale_dependency_validation(
                specs, tmp_path, "STANDARD"
            )

            assert len(findings) == 0
            assert mock_client.messages.create.call_count == 0


# -- TS-21-9: AI unavailable skips rule ---------------------------------------


class TestAIUnavailableSkips:
    """TS-21-9: Verify AI unavailability logs warning and returns empty.

    Requirement: 21-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_ai_error_returns_empty(self, tmp_path: Path) -> None:
        """AI error returns empty findings list."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        # Create spec with prd.md and upstream with design.md
        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd(spec_dir, "Uses `Config` for settings")

        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        (upstream_dir / "design.md").write_text("# Design\n\nConfig is defined.")

        specs = [_make_spec("10_downstream", spec_dir)]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.side_effect = Exception("Auth failed")
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await run_stale_dependency_validation(
                specs, tmp_path, "STANDARD"
            )

            assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_ai_error_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AI error produces a log warning."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd(spec_dir, "Uses `Config` for settings")

        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        (upstream_dir / "design.md").write_text("# Design\n\nConfig is defined.")

        specs = [_make_spec("10_downstream", spec_dir)]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.side_effect = Exception("Auth failed")
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING):
                _findings = await run_stale_dependency_validation(
                    specs, tmp_path, "STANDARD"
                )

            assert not _findings  # also empty
            assert any(
                record.levelno >= logging.WARNING for record in caplog.records
            )


# -- TS-21-10: Malformed AI response logs warning -----------------------------


class TestMalformedResponse:
    """TS-21-10: Verify malformed AI response is handled gracefully.

    Requirement: 21-REQ-2.E3
    """

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self) -> None:
        """Malformed JSON response returns empty findings."""
        from agent_fox.spec.validator import (
            DependencyRef,
            validate_dependency_interfaces,
        )

        ref = DependencyRef(
            declaring_spec="my_spec",
            upstream_spec="01_core",
            identifier="Config",
            raw_relationship="Uses `Config`",
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json {{}}")]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await validate_dependency_interfaces(
                "01_core", "# Design doc", [ref], "STANDARD"
            )

            assert len(findings) == 0


# -- TS-21-11: Batch multiple rows to same upstream spec ----------------------


class TestBatchSameUpstream:
    """TS-21-11: Verify single AI call for multiple rows to same upstream.

    Requirements: 21-REQ-3.1, 21-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_single_ai_call_for_same_upstream(
        self, tmp_path: Path
    ) -> None:
        """Two specs referencing same upstream produce one AI call."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        # Spec A depends on 01_core
        spec_a_dir = tmp_path / "10_spec_a"
        spec_a_dir.mkdir()
        _write_prd(spec_a_dir, "Uses `Config` for settings")

        # Spec B also depends on 01_core
        spec_b_dir = tmp_path / "11_spec_b"
        spec_b_dir.mkdir()
        _write_prd(spec_b_dir, "Uses `Store` for persistence")

        # Upstream 01_core with design.md
        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        (upstream_dir / "design.md").write_text(
            "# Design\n\nConfig and Store are defined."
        )

        specs = [
            _make_spec("10_spec_a", spec_a_dir),
            _make_spec("11_spec_b", spec_b_dir),
        ]

        mock_response = _make_mock_ai_response(
            [
                {
                    "identifier": "Config",
                    "found": True,
                    "explanation": "Found",
                    "suggestion": None,
                },
                {
                    "identifier": "Store",
                    "found": True,
                    "explanation": "Found",
                    "suggestion": None,
                },
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            _findings = await run_stale_dependency_validation(
                specs, tmp_path, "STANDARD"
            )

            assert _findings is not None
            # Only one AI call for the single upstream spec 01_core
            assert mock_client.messages.create.call_count == 1

            # Verify both identifiers were sent in the prompt
            call_args = mock_client.messages.create.call_args
            prompt = str(call_args)
            assert "Config" in prompt
            assert "Store" in prompt


# -- TS-21-12: No backtick tokens means zero AI calls -------------------------


class TestNoBactickTokensZeroCalls:
    """TS-21-12: Verify no AI calls when no Relationship has backticks.

    Requirement: 21-REQ-3.E1
    """

    @pytest.mark.asyncio
    async def test_no_backticks_no_ai_calls(self, tmp_path: Path) -> None:
        """Plain-text Relationships produce zero AI calls."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd_no_backticks(spec_dir)

        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        (upstream_dir / "design.md").write_text("# Design")

        specs = [_make_spec("10_downstream", spec_dir)]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await run_stale_dependency_validation(
                specs, tmp_path, "STANDARD"
            )

            assert len(findings) == 0
            assert mock_client.messages.create.call_count == 0


# -- TS-21-13: Findings have correct severity and format ----------------------


class TestFindingSeverityFormat:
    """TS-21-13: Verify stale-dependency findings are Warning severity.

    Requirements: 21-REQ-4.1, 21-REQ-4.2, 21-REQ-4.3
    """

    @pytest.mark.asyncio
    async def test_findings_are_warning_severity(self) -> None:
        """stale-dependency findings have severity='warning'."""
        from agent_fox.spec.validator import (
            DependencyRef,
            validate_dependency_interfaces,
        )

        ref = DependencyRef(
            declaring_spec="my_spec",
            upstream_spec="01_core",
            identifier="BadRef",
            raw_relationship="Uses `BadRef`",
        )

        mock_response = _make_mock_ai_response(
            [
                {
                    "identifier": "BadRef",
                    "found": False,
                    "explanation": "Not found",
                    "suggestion": "GoodRef",
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await validate_dependency_interfaces(
                "01_core", "# Design", [ref], "STANDARD"
            )

            assert all(f.severity == "warning" for f in findings)

    @pytest.mark.asyncio
    async def test_stale_dep_findings_via_run_ai_validation(
        self, tmp_path: Path
    ) -> None:
        """stale-dep findings appear via run_ai_validation.

        Requirements: 21-REQ-4.1, 21-REQ-4.2
        """
        from agent_fox.spec.validator import run_ai_validation

        # Create spec with prd.md and requirements.md
        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd(spec_dir, "Uses `BadRef` for something")
        req_text = (
            "# Requirements\n\n## Requirement 1\n\n"
            "1. [99-REQ-1.1] THE system SHALL work.\n"
        )
        (spec_dir / "requirements.md").write_text(req_text)

        # Create upstream with design.md
        upstream_dir = tmp_path / "01_core"
        upstream_dir.mkdir()
        (upstream_dir / "design.md").write_text("# Design\n\nGoodRef is defined.")

        specs = [_make_spec("10_downstream", spec_dir)]

        # Mock: acceptance criteria returns empty, stale-dep flags BadRef
        stale_response = _make_mock_ai_response(
            [
                {
                    "identifier": "BadRef",
                    "found": False,
                    "explanation": "Not found",
                    "suggestion": "GoodRef",
                }
            ]
        )
        criteria_response = MagicMock()
        criteria_response.content = [MagicMock(text='{"issues": []}')]

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            # First call = acceptance criteria, second call = stale-dep
            mock_client.messages.create.side_effect = [
                criteria_response,
                stale_response,
            ]
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            findings = await run_ai_validation(
                specs, "STANDARD", specs_dir=tmp_path
            )

            stale = [f for f in findings if f.rule == "stale-dependency"]
            assert len(stale) == 1
            assert stale[0].severity == "warning"

    def test_findings_sortable_with_other_types(self) -> None:
        """stale-dependency findings sort alongside other finding types."""
        findings = [
            Finding(
                spec_name="b_spec",
                file="prd.md",
                rule="stale-dependency",
                severity="warning",
                message="test stale dep",
                line=None,
            ),
            Finding(
                spec_name="a_spec",
                file="requirements.md",
                rule="missing-file",
                severity="error",
                message="test missing file",
                line=None,
            ),
        ]
        sorted_f = sort_findings(findings)
        assert sorted_f is not None
        assert sorted_f[0].spec_name == "a_spec"
        assert sorted_f[1].spec_name == "b_spec"


# -- TS-21-14: Multiple upstream specs produce separate AI calls ---------------


class TestMultipleUpstreamsSeparateCalls:
    """TS-21-14: Verify different upstream specs get separate AI calls.

    Requirement: 21-REQ-3.1
    """

    @pytest.mark.asyncio
    async def test_two_upstreams_two_calls(self, tmp_path: Path) -> None:
        """Deps on two different upstreams produce two AI calls."""
        from agent_fox.spec.validator import run_stale_dependency_validation

        # Spec that depends on both 01_core and 02_store
        spec_dir = tmp_path / "10_downstream"
        spec_dir.mkdir()
        _write_prd_multi_upstream(spec_dir)

        # Create both upstream specs with design.md
        for name in ["01_core", "02_store"]:
            up_dir = tmp_path / name
            up_dir.mkdir()
            (up_dir / "design.md").write_text(f"# Design for {name}")

        specs = [_make_spec("10_downstream", spec_dir)]

        mock_response = _make_mock_ai_response(
            [
                {
                    "identifier": "Config",
                    "found": True,
                    "explanation": "Found",
                    "suggestion": None,
                }
            ]
        )

        with patch(_MOCK_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_cls.return_value = mock_client

            _findings = await run_stale_dependency_validation(
                specs, tmp_path, "STANDARD"
            )

            assert _findings is not None  # may or may not have findings
            assert mock_client.messages.create.call_count == 2


# -- TS-21-15: Fix replaces stale identifier with AI suggestion ----------------


class TestFixReplacesIdentifier:
    """TS-21-15: Verify fixer replaces backtick identifier in prd.md.

    Requirements: 21-REQ-5.1, 21-REQ-5.2, 21-REQ-5.4
    """

    def test_replace_stale_identifier(self, tmp_path: Path) -> None:
        """Stale identifier is replaced with AI suggestion."""
        from agent_fox.spec.fixer import IdentifierFix, fix_stale_dependency

        prd_path = _write_prd(
            tmp_path,
            "Uses `SnippetStore` for persistence",
        )

        fix = IdentifierFix(
            original="SnippetStore",
            suggestion="Store",
            upstream_spec="01_core",
        )

        results = fix_stale_dependency("my_spec", prd_path, [fix])

        assert len(results) == 1
        content = prd_path.read_text()
        assert "`Store`" in content
        assert "`SnippetStore`" not in content
        assert "SnippetStore" in results[0].description
        assert "Store" in results[0].description


# -- TS-21-16: Fix skips findings without suggestion --------------------------


class TestFixSkipsNoSuggestion:
    """TS-21-16: Verify fixer skips findings where AI provided no suggestion.

    Requirement: 21-REQ-5.E1
    """

    def test_empty_suggestion_skips(self, tmp_path: Path) -> None:
        """Empty suggestion string causes skip."""
        from agent_fox.spec.fixer import IdentifierFix, fix_stale_dependency

        prd_path = _write_prd(
            tmp_path,
            "Uses `SnippetStore` for persistence",
        )
        content_before = prd_path.read_text()

        fix = IdentifierFix(
            original="SnippetStore",
            suggestion="",
            upstream_spec="01_core",
        )

        results = fix_stale_dependency("my_spec", prd_path, [fix])

        assert len(results) == 0
        assert prd_path.read_text() == content_before


# -- TS-21-17: Fix skips when suggestion already present ----------------------


class TestFixSkipsAlreadyPresent:
    """TS-21-17: Verify fixer skips when suggested identifier already exists.

    Requirement: 21-REQ-5.E3
    """

    def test_already_fixed_skips(self, tmp_path: Path) -> None:
        """Skip when original is gone and suggestion already present."""
        from agent_fox.spec.fixer import IdentifierFix, fix_stale_dependency

        # prd.md already has `Store`, not `SnippetStore`
        prd_path = _write_prd(
            tmp_path,
            "Uses `Store` for persistence",
        )
        content_before = prd_path.read_text()

        fix = IdentifierFix(
            original="SnippetStore",
            suggestion="Store",
            upstream_spec="01_core",
        )

        results = fix_stale_dependency("my_spec", prd_path, [fix])

        assert len(results) == 0
        assert prd_path.read_text() == content_before


# -- TS-21-18: Fix preserves surrounding text ---------------------------------


class TestFixPreservesSurrounding:
    """TS-21-18: Verify fixer only replaces the target, leaving rest intact.

    Requirement: 21-REQ-5.2
    """

    def test_surrounding_text_preserved(self, tmp_path: Path) -> None:
        """Only the target identifier is replaced; others remain."""
        from agent_fox.spec.fixer import IdentifierFix, fix_stale_dependency

        prd_path = _write_prd(
            tmp_path,
            "Uses `SnippetStore` for persistence and `Config` for settings",
        )

        fix = IdentifierFix(
            original="SnippetStore",
            suggestion="Store",
            upstream_spec="01_core",
        )

        _results = fix_stale_dependency("my_spec", prd_path, [fix])

        assert len(_results) >= 0  # just ensure it ran
        content = prd_path.read_text()
        assert "`Store`" in content
        assert "`Config`" in content
        assert "`SnippetStore`" not in content
