"""Property tests for review archetype persistence and review-only mode.

Uses Hypothesis to verify structural invariants: parse-or-warn, supersession
consistency, archetype routing correctness, JSON extraction robustness,
review-only graph completeness, read-only enforcement, and retry context.

Test Spec: TS-53-P1 through TS-53-P7
Requirements: 53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1, 53-REQ-1.2, 53-REQ-2.2,
              53-REQ-3.2, 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1, 53-REQ-4.1,
              53-REQ-6.2, 53-REQ-6.4, 53-REQ-5.1, 53-REQ-5.2
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.graph.injection import build_review_only_graph
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.migrations import apply_pending_migrations
from agent_fox.knowledge.review_store import (
    ReviewFinding,
    insert_findings,
    query_active_findings,
)

# NOTE: The following imports fail until the respective task groups implement them.
# All property tests in this file will fail with ImportError until Task Group 2
# creates engine.review_parser.
from agent_fox.session.review_parser import (
    extract_json_array,
)

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_knowledge_db() -> KnowledgeDB:
    """Create an isolated in-memory KnowledgeDB for property tests."""
    import duckdb

    from tests.unit.knowledge.conftest import SCHEMA_DDL

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    apply_pending_migrations(conn)
    db = KnowledgeDB.__new__(KnowledgeDB)
    db._conn = conn
    return db


def _make_finding(
    spec_name: str = "prop_spec",
    task_group: str = "1",
    severity: str = "major",
    description: str = "prop finding",
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id="prop_session",
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_SEVERITIES = ["critical", "major", "minor", "observation"]
VALID_ARCHETYPES = ["skeptic", "verifier", "oracle"]
WRITE_COMMANDS = {"cp", "mv", "rm", "mkdir", "touch", "tee", "sed", "awk"}


@st.composite
def valid_review_finding_dict(draw: st.DrawFn) -> dict:
    """Generate a valid ReviewFinding dict."""
    return {
        "severity": draw(st.sampled_from(VALID_SEVERITIES)),
        "description": draw(
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
            )
        ),
        "requirement_ref": draw(
            st.one_of(
                st.none(),
                st.from_regex(r"[A-Z0-9]{2,4}-REQ-\d+\.\d+", fullmatch=True),
            )
        ),
    }


@st.composite
def finding_batch(draw: st.DrawFn) -> list[ReviewFinding]:
    """Generate a non-empty batch of ReviewFinding instances."""
    n = draw(st.integers(min_value=1, max_value=5))
    return [_make_finding(description=f"Finding {i}") for i in range(n)]


@st.composite
def random_text_with_possible_json(draw: st.DrawFn) -> str:
    """Generate text that may or may not contain a valid JSON array."""
    has_json = draw(st.booleans())
    prose = draw(
        st.text(
            min_size=0,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        )
    )
    if has_json:
        items = draw(st.lists(valid_review_finding_dict(), min_size=1, max_size=3))
        return f"{prose}\n{json.dumps(items)}\n{prose}"
    return prose or "no json here"


@st.composite
def prose_wrapped_json_array(draw: st.DrawFn) -> tuple[str, list]:
    """Generate a valid JSON array wrapped in random prose."""
    items = draw(st.lists(valid_review_finding_dict(), min_size=0, max_size=5))
    prefix = draw(
        st.text(
            min_size=0,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "Z")),
        )
    )
    suffix = draw(
        st.text(
            min_size=0,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "Z")),
        )
    )
    return f"{prefix}\n{json.dumps(items)}\n{suffix}", items


# ---------------------------------------------------------------------------
# TS-53-P1: Parse or warn invariant
# ---------------------------------------------------------------------------


class TestParseOrWarnInvariant:
    """TS-53-P1: For any archetype output, either findings are persisted or
    review.parse_failure is emitted. No output is silently discarded.

    Property 1 from design.md.
    Validates: 53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1
    """

    @given(
        output=random_text_with_possible_json(),
        archetype=st.sampled_from(VALID_ARCHETYPES),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_parse_or_warn_invariant(self, output: str, archetype: str) -> None:
        """TS-53-P1: Either inserts >= 1 record or emits review.parse_failure."""
        assert hasattr(AuditEventType, "REVIEW_PARSE_FAILURE"), "AuditEventType.REVIEW_PARSE_FAILURE not yet defined"

        db = _make_knowledge_db()
        try:
            emitted: list = []
            mock_sink = MagicMock()
            mock_sink.emit_audit_event.side_effect = lambda e: emitted.append(e)

            runner = NodeSessionRunner(
                "prop_spec:1",
                AgentFoxConfig(),
                archetype=archetype,
                knowledge_db=db,
                sink_dispatcher=mock_sink,
                run_id="prop_run",
            )

            runner._persist_review_findings(output, "prop_spec:1", 1)

            # Count total inserted records across all tables
            _tables = ("review_findings", "verification_results", "drift_findings")
            total_inserted = sum(
                db._conn.execute(  # type: ignore[union-attr]
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                ).fetchone()[0]  # type: ignore[index]
                for table in _tables
            )

            parse_failure_events = [e for e in emitted if e.event_type == "review.parse_failure"]

            assert total_inserted > 0 or len(parse_failure_events) > 0, (
                f"No findings persisted and no parse_failure event emitted for output={output!r}, archetype={archetype}"
            )
        finally:
            db._conn.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# TS-53-P2: Supersession consistency
# ---------------------------------------------------------------------------


class TestSupersessionConsistency:
    """TS-53-P2: After N insertions, only the last batch has superseded_by=NULL.

    Property 2 from design.md.
    Validates: 53-REQ-1.2, 53-REQ-2.2, 53-REQ-3.2
    """

    @given(
        batches=st.lists(
            st.lists(
                st.from_regex(r"[a-z]{3,15}", fullmatch=True),
                min_size=1,
                max_size=4,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_only_last_batch_active(self, batches: list[list[str]]) -> None:
        """TS-53-P2: Only the most recently inserted batch is active."""
        db = _make_knowledge_db()
        try:
            spec_name = "prop_spec"
            task_group = "1"
            last_batch_ids: set[str] = set()

            for i, descriptions in enumerate(batches):
                batch = [
                    _make_finding(
                        spec_name=spec_name,
                        task_group=task_group,
                        description=desc,
                    )
                    for desc in descriptions
                ]
                insert_findings(db._conn, batch)  # type: ignore[arg-type]
                if i == len(batches) - 1:
                    last_batch_ids = {f.id for f in batch}

            active = query_active_findings(db._conn, spec_name, task_group)  # type: ignore[arg-type]
            active_ids = {f.id for f in active}

            assert active_ids <= last_batch_ids, (
                f"Active findings include IDs not in last batch: {active_ids - last_batch_ids}"
            )
            assert len(active_ids) == len(last_batch_ids), (
                f"Not all last-batch findings are active: active={active_ids}, last={last_batch_ids}"
            )
        finally:
            db._conn.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# TS-53-P3: Archetype routing correctness
# ---------------------------------------------------------------------------


class TestArchetypeRoutingCorrectness:
    """TS-53-P3: Each archetype routes to the correct insert function.

    Property 3 from design.md.
    Validates: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1
    """

    @given(archetype=st.sampled_from(VALID_ARCHETYPES))
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_archetype_routes_to_correct_insert(self, archetype: str) -> None:
        """TS-53-P3: Each archetype type routes to the correct persistence function."""
        db = _make_knowledge_db()
        try:
            # Build valid JSON for each archetype type
            if archetype == "skeptic":
                output = json.dumps([{"severity": "major", "description": "finding"}])
                table = "review_findings"
            elif archetype == "verifier":
                output = json.dumps([{"requirement_id": "REQ-1.1", "verdict": "PASS"}])
                table = "verification_results"
            else:  # oracle
                output = json.dumps([{"severity": "major", "description": "drift"}])
                table = "drift_findings"

            runner = NodeSessionRunner(
                "prop_spec:1",
                AgentFoxConfig(),
                archetype=archetype,
                knowledge_db=db,
            )

            runner._persist_review_findings(output, "prop_spec:1", 1)

            count = db._conn.execute(  # type: ignore[union-attr]
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]  # type: ignore[index]

            assert count > 0, f"archetype={archetype} should have inserted into {table}, but count=0"

            # Verify nothing was inserted into the wrong tables
            other_tables = {
                "review_findings",
                "verification_results",
                "drift_findings",
            } - {table}
            for other in other_tables:
                other_count = db._conn.execute(  # type: ignore[union-attr]
                    f"SELECT COUNT(*) FROM {other}"  # noqa: S608
                ).fetchone()[0]  # type: ignore[index]
                assert other_count == 0, (
                    f"archetype={archetype} should not insert into {other}, but count={other_count}"
                )
        finally:
            db._conn.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# TS-53-P4: JSON extraction robustness
# ---------------------------------------------------------------------------


class TestJsonExtractionRobustness:
    """TS-53-P4: Any text containing a valid JSON array yields non-None from
    extract_json_array.

    Property 4 from design.md.
    Validates: 53-REQ-4.1
    """

    @given(wrapped=prose_wrapped_json_array())
    @settings(
        max_examples=40,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_valid_array_in_prose_extracted(self, wrapped: tuple[str, list]) -> None:
        """TS-53-P4: Any text containing a valid JSON array is extracted."""
        text, expected = wrapped
        result = extract_json_array(text)
        assert result is not None, f"extract_json_array returned None for text containing valid JSON: {text!r}"
        assert result == expected, f"Extracted array {result!r} does not match expected {expected!r}"

    @given(
        prefix=st.text(
            min_size=0,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "Z")),
        ),
        array=st.lists(valid_review_finding_dict(), min_size=1, max_size=5),
        suffix=st.text(
            min_size=0,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "Z")),
        ),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_extract_with_arbitrary_prose_wrapper(self, prefix: str, array: list, suffix: str) -> None:
        """TS-53-P4: extract_json_array handles arbitrary prose wrapping."""
        text = prefix + json.dumps(array) + suffix
        result = extract_json_array(text)
        assert result is not None
        assert result == array


# ---------------------------------------------------------------------------
# TS-53-P5: Review-only graph completeness
# ---------------------------------------------------------------------------


class TestReviewOnlyGraphCompleteness:
    """TS-53-P5: Every eligible spec has the correct archetype nodes in the graph.

    Property 5 from design.md.
    Validates: 53-REQ-6.2
    """

    @given(
        spec_configs=st.lists(
            st.fixed_dictionaries(
                {
                    "name": st.from_regex(r"[0-9]{2}_[a-z]{3,10}", fullmatch=True),
                    "has_source": st.booleans(),
                    "has_reqs": st.booleans(),
                }
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_correct_nodes_per_spec(self, tmp_path: Path, spec_configs: list[dict]) -> None:
        """TS-53-P5: Each spec gets Skeptic+Oracle iff source, Verifier iff reqs."""
        # Deduplicate spec names to avoid collisions in hypothesis
        seen: set[str] = set()
        unique_configs = []
        for cfg in spec_configs:
            if cfg["name"] not in seen:
                seen.add(cfg["name"])
                unique_configs.append(cfg)

        import shutil  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        # Clean up from previous Hypothesis example since tmp_path is reused
        if specs_dir.exists():
            shutil.rmtree(specs_dir)
        specs_dir.mkdir()

        for cfg in unique_configs:
            spec_dir = specs_dir / cfg["name"]
            spec_dir.mkdir()
            if cfg["has_source"]:
                (spec_dir / "main.py").write_text("# code\n")
            if cfg["has_reqs"]:
                (spec_dir / "requirements.md").write_text("# reqs\n")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        for cfg in unique_configs:
            if not cfg["has_source"] and not cfg["has_reqs"]:
                continue  # Spec is not eligible; may or may not have nodes

            archetypes = {n.archetype for n in graph.nodes.values() if n.spec_name == cfg["name"]}

            if cfg["has_source"]:
                assert "skeptic" in archetypes, f"Spec {cfg['name']} with source should have skeptic"
                assert "oracle" in archetypes, f"Spec {cfg['name']} with source should have oracle"
            else:
                assert "skeptic" not in archetypes, f"Spec {cfg['name']} without source should not have skeptic"

            if cfg["has_reqs"]:
                assert "verifier" in archetypes, f"Spec {cfg['name']} with reqs should have verifier"
            else:
                assert "verifier" not in archetypes, f"Spec {cfg['name']} without reqs should not have verifier"


# ---------------------------------------------------------------------------
# TS-53-P6: Review-only read-only enforcement
# ---------------------------------------------------------------------------


class TestReviewOnlyReadOnlyEnforcement:
    """TS-53-P6: No review-only node has write commands in its allowlist.

    Property 6 from design.md.
    Validates: 53-REQ-6.4
    """

    def test_review_only_nodes_have_no_write_commands(self, tmp_path: Path) -> None:
        """TS-53-P6: No review node's allowlist contains write shell commands."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "03_api"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("# reqs\n")
        (spec_dir / "main.py").write_text("# code\n")

        graph = build_review_only_graph(specs_dir, archetypes_config=None)

        for node in graph.nodes.values():
            entry = ARCHETYPE_REGISTRY.get(node.archetype)
            if entry is None:
                continue
            allowlist = set(entry.default_allowlist or [])
            forbidden = allowlist & WRITE_COMMANDS
            assert not forbidden, f"Archetype {node.archetype} has write commands in allowlist: {forbidden}"


# ---------------------------------------------------------------------------
# TS-53-P7: Retry context includes active critical/major findings
# ---------------------------------------------------------------------------


class TestRetryContextIncludesFindings:
    """TS-53-P7: All active critical/major findings appear in the retry context.
    Minor and observation findings do not.

    Property 7 from design.md.
    Validates: 53-REQ-5.1, 53-REQ-5.2
    """

    @given(finding_severities=st.lists(st.sampled_from(VALID_SEVERITIES), min_size=0, max_size=10))
    @settings(
        max_examples=25,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_critical_major_in_context_minor_obs_not(self, finding_severities: list[str]) -> None:
        """TS-53-P7: Critical/major findings appear in context; minor/obs do not."""
        db = _make_knowledge_db()
        try:
            findings_with_desc = [
                ReviewFinding(
                    id=str(uuid.uuid4()),
                    severity=sev,
                    description=f"Finding severity={sev} idx={i}",
                    requirement_ref=None,
                    spec_name="prop_spec",
                    task_group="1",
                    session_id="prop_sess",
                )
                for i, sev in enumerate(finding_severities)
            ]

            if findings_with_desc:
                insert_findings(db._conn, findings_with_desc)  # type: ignore[arg-type]

            runner = NodeSessionRunner(
                "prop_spec:2",
                AgentFoxConfig(),
                archetype="coder",
                knowledge_db=db,
            )

            context = runner._build_retry_context("prop_spec")

            for f in findings_with_desc:
                if f.severity in ("critical", "major"):
                    assert f.description in context, (
                        f"Active {f.severity} finding should appear in context: {f.description!r}"
                    )
                else:
                    assert f.description not in context, (
                        f"{f.severity} finding should NOT appear in context: {f.description!r}"
                    )
        finally:
            db._conn.close()  # type: ignore[union-attr]
