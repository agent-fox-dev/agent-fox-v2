"""GitHub issue search-before-create idempotency via ``gh`` CLI.

Provides ``file_or_update_issue()`` which searches for an existing open issue
with a matching title prefix before creating a new one. On re-runs, existing
issues are updated rather than duplicated.

All ``gh`` failures are logged and swallowed — GitHub issue filing never
blocks session completion.

Requirements: 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, 26-REQ-10.E1
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def _run_gh_command(args: list[str]) -> str:
    """Run a ``gh`` CLI command and return stdout.

    Raises on non-zero exit or if ``gh`` is not found.
    """
    cmd = ["gh", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh command failed (exit {proc.returncode}): "
            f"{stderr.decode().strip()}"
        )
    return stdout.decode().strip()


def _parse_issue_number(search_output: str) -> str | None:
    """Extract the first issue number from ``gh issue list`` output.

    Expected format: ``NUMBER\\tTITLE\\t...`` per line.
    Returns the number string or None if no results.
    """
    if not search_output.strip():
        return None
    first_line = search_output.strip().splitlines()[0]
    parts = first_line.split("\t")
    if parts:
        return parts[0].strip()
    return None


async def file_or_update_issue(
    title_prefix: str,
    body: str,
    *,
    repo: str | None = None,
    close_if_empty: bool = False,
) -> str | None:
    """Search-before-create GitHub issue idempotency.

    1. Search: ``gh issue list --search "in:title {title_prefix}" --state open``
    2. If found: update body, add comment noting re-run.
    3. If not found: create new issue.
    4. If ``close_if_empty`` and body is empty/whitespace: close existing issue.

    Returns issue URL or None on failure.
    Failures are logged but never raise.

    Requirements: 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, 26-REQ-10.E1
    """
    try:
        # 1. Search for existing open issue
        search_args = [
            "issue", "list",
            "--search", f"in:title {title_prefix}",
            "--state", "open",
            "--limit", "1",
        ]
        if repo:
            search_args.extend(["--repo", repo])

        search_output = await _run_gh_command(search_args)
        existing_number = _parse_issue_number(search_output)

        if existing_number:
            # 4. Close if empty and close_if_empty is set
            if close_if_empty and not body.strip():
                close_args = ["issue", "close", existing_number]
                if repo:
                    close_args.extend(["--repo", repo])
                close_args.extend([
                    "--comment",
                    "Closing: no findings on re-run.",
                ])
                await _run_gh_command(close_args)
                logger.info(
                    "Closed issue #%s (no findings): %s",
                    existing_number,
                    title_prefix,
                )
                return None

            # 2. Update existing issue
            edit_args = [
                "issue", "edit", existing_number,
                "--body", body,
            ]
            if repo:
                edit_args.extend(["--repo", repo])
            await _run_gh_command(edit_args)

            # Add comment noting the re-run
            comment_args = [
                "issue", "comment", existing_number,
                "--body", "Updated on re-run.",
            ]
            if repo:
                comment_args.extend(["--repo", repo])
            await _run_gh_command(comment_args)

            logger.info(
                "Updated existing issue #%s: %s",
                existing_number,
                title_prefix,
            )
            return f"#{existing_number}"

        # 3. Create new issue
        create_args = [
            "issue", "create",
            "--title", title_prefix,
            "--body", body,
        ]
        if repo:
            create_args.extend(["--repo", repo])

        result = await _run_gh_command(create_args)
        logger.info("Created new issue: %s — %s", title_prefix, result)
        return result

    except FileNotFoundError:
        logger.warning(
            "gh CLI not found; cannot file GitHub issue for '%s'",
            title_prefix,
        )
        return None
    except Exception:
        logger.warning(
            "GitHub issue filing failed for '%s'; continuing without issue",
            title_prefix,
            exc_info=True,
        )
        return None
