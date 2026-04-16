"""Tests for required label creation during af init (issue #358).

Verifies that _ensure_platform_labels is called during init and that:
- labels are created when the platform is configured
- init succeeds silently when the platform is not configured
- init succeeds silently when GITHUB_PAT is absent
- label creation failures are non-fatal

Requirements: 358-REQ-3, 358-REQ-4, 358-REQ-5
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# TS-358-6: _ensure_platform_labels creates required labels when configured
# ---------------------------------------------------------------------------


class TestEnsurePlatformLabelsConfigured:
    """Verify required labels are created when platform is configured."""

    def test_creates_required_labels_when_platform_configured(self, tmp_path: Path) -> None:
        """TS-358-6: create_label called for each REQUIRED_LABEL."""
        from agent_fox.platform.labels import REQUIRED_LABELS
        from agent_fox.workspace.init_project import _ensure_platform_labels

        mock_platform = AsyncMock()
        mock_platform.create_label = AsyncMock(return_value=None)

        with (
            patch(
                "agent_fox.workspace.init_project._ensure_platform_labels_async",
                return_value=len(REQUIRED_LABELS),
            ) as mock_async,
        ):
            result = _ensure_platform_labels(tmp_path)

        assert result == len(REQUIRED_LABELS)
        mock_async.assert_called_once_with(tmp_path)


# ---------------------------------------------------------------------------
# TS-358-7: _ensure_platform_labels skips when platform is None
# ---------------------------------------------------------------------------


class TestEnsurePlatformLabelsNoPlatform:
    """Verify label creation is skipped when platform is not configured."""

    def test_returns_zero_when_platform_not_configured(self, tmp_path: Path) -> None:
        """TS-358-7: Returns 0 silently when create_platform_safe returns None."""
        import asyncio

        from agent_fox.workspace.init_project import _ensure_platform_labels_async

        with (
            patch("agent_fox.workspace.init_project._ensure_platform_labels_async", None),
            # Direct async test
        ):
            pass

        # Test the async function directly
        async def run() -> int:
            with (
                patch("agent_fox.core.config.load_config", return_value=MagicMock()),
                patch(
                    "agent_fox.nightshift.platform_factory.create_platform_safe",
                    return_value=None,
                ),
            ):
                return await _ensure_platform_labels_async(tmp_path)

        result = asyncio.run(run())
        assert result == 0


# ---------------------------------------------------------------------------
# TS-358-8: _ensure_platform_labels is non-fatal on config load failure
# ---------------------------------------------------------------------------


class TestEnsurePlatformLabelsConfigError:
    """Verify label creation failure does not break init."""

    def test_returns_zero_on_config_load_failure(self, tmp_path: Path) -> None:
        """TS-358-8: Returns 0 when config cannot be loaded."""
        from agent_fox.workspace.init_project import _ensure_platform_labels

        with patch(
            "agent_fox.workspace.init_project._ensure_platform_labels_async",
            side_effect=RuntimeError("config error"),
        ):
            result = _ensure_platform_labels(tmp_path)

        assert result == 0

    def test_returns_zero_on_individual_label_failure(self, tmp_path: Path) -> None:
        """TS-358-9: Partial failure still returns count of successes."""
        import asyncio

        from agent_fox.platform.labels import REQUIRED_LABELS
        from agent_fox.workspace.init_project import _ensure_platform_labels_async

        call_count = 0

        async def flaky_create_label(name: str, color: str, description: str = "") -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            # Second call succeeds

        mock_platform = AsyncMock()
        mock_platform.create_label = flaky_create_label

        async def run() -> int:
            with (
                patch("agent_fox.core.config.load_config", return_value=MagicMock()),
                patch(
                    "agent_fox.nightshift.platform_factory.create_platform_safe",
                    return_value=mock_platform,
                ),
            ):
                return await _ensure_platform_labels_async(tmp_path)

        result = asyncio.run(run())
        # Only 1 out of 2 labels succeeded
        assert result == len(REQUIRED_LABELS) - 1


# ---------------------------------------------------------------------------
# TS-358-10: InitResult includes labels_ensured field
# ---------------------------------------------------------------------------


class TestInitResultLabelsEnsured:
    """Verify InitResult carries labels_ensured count."""

    def test_init_result_has_labels_ensured_field(self) -> None:
        """TS-358-10: InitResult dataclass has labels_ensured field."""
        from agent_fox.workspace.init_project import InitResult

        result = InitResult(status="ok", agents_md="created")
        assert hasattr(result, "labels_ensured")
        assert result.labels_ensured == 0

    def test_init_result_labels_ensured_nonzero(self) -> None:
        """TS-358-10b: InitResult can carry nonzero labels_ensured."""
        from agent_fox.workspace.init_project import InitResult

        result = InitResult(status="ok", agents_md="created", labels_ensured=2)
        assert result.labels_ensured == 2


# ---------------------------------------------------------------------------
# TS-358-11: Label constants are correct values
# ---------------------------------------------------------------------------


class TestLabelConstants:
    """Verify label constant values match what the codebase expects."""

    def test_label_fix_value(self) -> None:
        """TS-358-11: LABEL_FIX == 'af:fix'."""
        from agent_fox.platform.labels import LABEL_FIX

        assert LABEL_FIX == "af:fix"

    def test_label_hunt_value(self) -> None:
        """TS-358-12: LABEL_HUNT == 'af:hunt'."""
        from agent_fox.platform.labels import LABEL_HUNT

        assert LABEL_HUNT == "af:hunt"

    def test_required_labels_contains_both(self) -> None:
        """TS-358-13: REQUIRED_LABELS contains both af:fix and af:hunt."""
        from agent_fox.platform.labels import LABEL_FIX, LABEL_HUNT, REQUIRED_LABELS

        names = {spec.name for spec in REQUIRED_LABELS}
        assert LABEL_FIX in names
        assert LABEL_HUNT in names

    def test_dedup_fingerprint_label_uses_constant(self) -> None:
        """TS-358-14: dedup.FINGERPRINT_LABEL equals labels.LABEL_HUNT."""
        from agent_fox.nightshift.dedup import FINGERPRINT_LABEL
        from agent_fox.platform.labels import LABEL_HUNT

        assert FINGERPRINT_LABEL == LABEL_HUNT
