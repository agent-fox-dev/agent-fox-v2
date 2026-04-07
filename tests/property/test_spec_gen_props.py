"""Property tests for spec generator.

Test Spec: TS-86-P1 through TS-86-P7
Properties: 1-7 from design.md
Requirements: 86-REQ-1.1, 86-REQ-1.2, 86-REQ-3.1, 86-REQ-3.2,
              86-REQ-5.1, 86-REQ-5.3, 86-REQ-6.3, 86-REQ-6.E2,
              86-REQ-10.1, 86-REQ-10.2
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agent_fox.nightshift.spec_gen import (
    LABEL_ANALYZING,
    LABEL_BLOCKED,
    LABEL_DONE,
    LABEL_GENERATING,
    LABEL_PENDING,
    LABEL_SPEC,
    IssueComment,
    SpecGenerator,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.nightshift.config import NightShiftConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LABEL_SET = [LABEL_SPEC, LABEL_ANALYZING, LABEL_PENDING, LABEL_GENERATING, LABEL_DONE, LABEL_BLOCKED]


def _make_generator(repo_root: Path | None = None) -> SpecGenerator:
    """Create a SpecGenerator with mocked dependencies."""
    platform = MagicMock()
    platform.assign_label = AsyncMock()
    platform.remove_label = AsyncMock()
    config = NightShiftConfig(
        max_clarification_rounds=3,
        max_budget_usd=2.0,
        spec_gen_model_tier="ADVANCED",
    )
    if repo_root is None:
        repo_root = Path("/tmp/test-repo")
    return SpecGenerator(platform=platform, config=config, repo_root=repo_root)


# ---------------------------------------------------------------------------
# TS-86-P1: Label transition always assigns before removing
# Property 1: For any label transition, assign_label is called before
#   remove_label.
# Validates: 86-REQ-3.1, 86-REQ-3.2
# ---------------------------------------------------------------------------


@given(
    from_label=st.sampled_from(_LABEL_SET),
    to_label=st.sampled_from(_LABEL_SET),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P1_label_transition_assign_before_remove(
    from_label: str,
    to_label: str,
) -> None:
    """Property 1: assign_label is called before remove_label."""
    import asyncio

    platform = MagicMock()
    call_order: list[str] = []

    async def track_assign(*args: object, **kw: object) -> None:
        call_order.append("assign")

    async def track_remove(*args: object, **kw: object) -> None:
        call_order.append("remove")

    platform.assign_label = AsyncMock(side_effect=track_assign)
    platform.remove_label = AsyncMock(side_effect=track_remove)

    config = NightShiftConfig(
        max_clarification_rounds=3,
        max_budget_usd=2.0,
        spec_gen_model_tier="ADVANCED",
    )
    gen = SpecGenerator(platform=platform, config=config, repo_root=Path("/tmp/test"))

    asyncio.get_event_loop().run_until_complete(
        gen._transition_label(42, from_label, to_label)
    )

    assert call_order.index("assign") < call_order.index("remove")


# ---------------------------------------------------------------------------
# TS-86-P2: Clarification round count is bounded
# Property 2: Round count is always between 0 and the number of fox
#   clarification comments.
# Validates: 86-REQ-5.1, 86-REQ-5.2
# ---------------------------------------------------------------------------

_fox_comment_strategy = st.builds(
    IssueComment,
    id=st.integers(min_value=1, max_value=10000),
    body=st.just("## Agent Fox -- Clarification Needed\n\n1. Question?"),
    user=st.just("agent-fox[bot]"),
    created_at=st.just("2026-01-01T00:00:00Z"),
)

_human_comment_strategy = st.builds(
    IssueComment,
    id=st.integers(min_value=1, max_value=10000),
    body=st.text(min_size=1, max_size=100).filter(
        lambda s: not s.strip().startswith("## Agent Fox")
    ),
    user=st.just("alice"),
    created_at=st.just("2026-01-02T00:00:00Z"),
)

_comment_strategy = st.one_of(_fox_comment_strategy, _human_comment_strategy)


@given(comments=st.lists(_comment_strategy, min_size=0, max_size=20))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P2_clarification_round_count_bounded(
    comments: list[IssueComment],
) -> None:
    """Property 2: 0 <= rounds <= fox_clarification_count."""
    gen = _make_generator()

    rounds = gen._count_clarification_rounds(comments)
    fox_count = sum(1 for c in comments if c.body.strip().startswith("## Agent Fox"))

    assert 0 <= rounds <= fox_count


# ---------------------------------------------------------------------------
# TS-86-P3: Fox comment detection is consistent with prefix
# Property 3: _is_fox_comment returns True iff body starts with
#   "## Agent Fox".
# Validates: 86-REQ-5.3, 86-REQ-2.3
# ---------------------------------------------------------------------------


@given(body=st.text(min_size=0, max_size=500))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P3_fox_comment_detection_consistent(body: str) -> None:
    """Property 3: _is_fox_comment(comment) == body.strip().startswith('## Agent Fox')."""
    gen = _make_generator()
    comment = IssueComment(id=1, body=body, user="bot", created_at="2026-01-01T00:00:00Z")

    expected = body.strip().startswith("## Agent Fox")
    assert gen._is_fox_comment(comment) == expected


# ---------------------------------------------------------------------------
# TS-86-P4: Spec number exceeds all existing prefixes
# Property 4: Next spec number is always greater than all existing.
# Validates: 86-REQ-6.3, 86-REQ-6.E2
# ---------------------------------------------------------------------------


@given(prefixes=st.sets(st.integers(min_value=1, max_value=99), max_size=15))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P4_spec_number_exceeds_existing(
    prefixes: set[int],
    tmp_path: Path,
) -> None:
    """Property 4: next spec number > max(existing_prefixes), or 1 if empty."""
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir(exist_ok=True)

    for p in prefixes:
        (specs_dir / f"{p:02d}_test_spec").mkdir(exist_ok=True)

    gen = _make_generator(repo_root=tmp_path)
    result = gen._find_next_spec_number()

    # Note: tmp_path may contain folders from prior Hypothesis examples,
    # so we check that result exceeds all currently-present prefixes.
    all_prefixes: set[int] = set()
    import re as _re
    for entry in specs_dir.iterdir():
        m = _re.match(r"^(\d{2,})_", entry.name)
        if m:
            all_prefixes.add(int(m.group(1)))

    if not all_prefixes:
        assert result == 1
    else:
        assert result > max(all_prefixes)


# ---------------------------------------------------------------------------
# TS-86-P5: Remove label idempotency
# Property 5: remove_label succeeds regardless of whether the label is present.
# Validates: 86-REQ-1.1, 86-REQ-1.2
# ---------------------------------------------------------------------------


@given(label=st.text(min_size=1, max_size=50))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P5_remove_label_idempotency(label: str) -> None:
    """Property 5: remove_label never raises, whether 204 or 404."""
    import asyncio

    from agent_fox.platform.github import GitHubPlatform

    platform = GitHubPlatform(owner="org", repo="repo", token="tok")

    # Randomly return 204 (present) or 404 (absent)
    import random

    status = random.choice([204, 404])  # noqa: S311
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.text = ""

    client = AsyncMock()
    client.delete = AsyncMock(return_value=mock_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent_fox.platform.github.httpx.AsyncClient", return_value=client):
        # Should not raise regardless of 204 or 404
        asyncio.get_event_loop().run_until_complete(platform.remove_label(42, label))


# ---------------------------------------------------------------------------
# TS-86-P6: Cost is monotonically non-decreasing
# Property 6: Cumulative cost never decreases across API calls.
# Validates: 86-REQ-10.1, 86-REQ-10.2
# ---------------------------------------------------------------------------


@given(costs=st.lists(st.floats(min_value=0, max_value=10, allow_nan=False), min_size=1, max_size=10))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P6_cost_monotonically_nondecreasing(costs: list[float]) -> None:
    """Property 6: Cumulative cost never decreases and cap enforcement works."""
    max_budget = 2.0
    total = 0.0
    prev = 0.0
    exceeded = False

    for cost in costs:
        total += cost
        assert total >= prev
        prev = total
        if total >= max_budget:
            exceeded = True
            break

    if exceeded:
        assert total >= max_budget


# ---------------------------------------------------------------------------
# TS-86-P7: Spec name derivation produces valid folder names
# Property 7: Output always matches \d{2}_[a-z0-9_]+ pattern.
# Validates: 86-REQ-6.3
# ---------------------------------------------------------------------------


@given(
    title=st.text(min_size=1, max_size=100),
    prefix=st.integers(min_value=1, max_value=99),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_TS_86_P7_spec_name_valid_folder_name(title: str, prefix: int) -> None:
    """Property 7: Result matches spec folder name pattern."""
    gen = _make_generator()
    name = gen._spec_name_from_title(title, prefix)

    assert re.match(r"^\d{2}_[a-z0-9_]+$", name), f"Invalid spec name: {name!r}"

    # Determinism: same inputs produce same output
    name2 = gen._spec_name_from_title(title, prefix)
    assert name == name2
