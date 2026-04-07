"""Spec generator: autonomous issue-to-spec pipeline.

Orchestrates issue analysis, clarification loop, spec document generation,
and git landing. The SpecGenerator class contains all spec-generation logic;
SpecGeneratorStream (in streams.py) delegates to it.

Requirements: 86-REQ-2.* through 86-REQ-10.*
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anthropic.types import TextBlock

from agent_fox.core.client import cached_messages_create
from agent_fox.core.errors import ConfigError, IntegrationError
from agent_fox.core.json_extraction import extract_json_object
from agent_fox.core.models import TIER_DEFAULTS, ModelTier, resolve_model
from agent_fox.platform.github import IssueComment, IssueResult

if TYPE_CHECKING:
    from agent_fox.nightshift.config import NightShiftConfig
    from agent_fox.platform.protocol import PlatformProtocol
    from agent_fox.spec.discovery import SpecInfo

logger = logging.getLogger(__name__)


def _extract_text(response: Any, context: str) -> str:
    """Extract text from an Anthropic API response content block.

    Handles the TextBlock union type by narrowing with isinstance first,
    then falling back to getattr for compatible types such as test mocks.
    Raises ValueError if no text content is available.
    """
    first_block = response.content[0]
    if isinstance(first_block, TextBlock):
        return first_block.text
    maybe_text: str | None = getattr(first_block, "text", None)
    if maybe_text is None:
        raise ValueError(f"AI response for {context} has no text content")
    return maybe_text


# ---------------------------------------------------------------------------
# Label constants
# ---------------------------------------------------------------------------

LABEL_SPEC = "af:spec"
LABEL_ANALYZING = "af:spec-analyzing"
LABEL_PENDING = "af:spec-pending"
LABEL_GENERATING = "af:spec-generating"
LABEL_DONE = "af:spec-done"
LABEL_BLOCKED = "af:spec-blocked"

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class SpecGenOutcome(StrEnum):
    """Outcome of a spec generation attempt."""

    GENERATED = "generated"
    PENDING = "pending"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SpecGenResult:
    """Result of processing a single issue."""

    outcome: SpecGenOutcome
    issue_number: int
    spec_name: str | None = None
    commit_hash: str | None = None
    cost: float = 0.0


@dataclass(frozen=True)
class AnalysisResult:
    """Result of AI analysis of an issue's clarity."""

    clear: bool
    questions: list[str]
    summary: str


@dataclass(frozen=True)
class DuplicateCheckResult:
    """Result of checking for duplicate/overlapping specs."""

    is_duplicate: bool
    overlapping_spec: str | None = None
    explanation: str = ""


@dataclass(frozen=True)
class ReferencedIssue:
    """An issue referenced via #N in body or comments."""

    number: int
    title: str
    body: str
    comments: list[IssueComment]


@dataclass(frozen=True)
class SpecPackage:
    """A complete spec package ready to be landed."""

    spec_name: str
    files: dict[str, str]
    source_issue_url: str


# ---------------------------------------------------------------------------
# Internal context object
# ---------------------------------------------------------------------------


@dataclass
class _SpecGenContext:
    """Accumulated context for a single spec generation run."""

    referenced_issues: list[ReferencedIssue]
    existing_specs: list[SpecInfo]
    supersedes: str | None = None


# Reference pattern for #N mentions
_REFERENCE_PATTERN = re.compile(r"#(\d+)")

# Spec directory pattern
_SPEC_DIR_PATTERN = re.compile(r"^(\d{2,})_(.+)$")


# ---------------------------------------------------------------------------
# SpecGenerator
# ---------------------------------------------------------------------------


class SpecGenerator:
    """Orchestrates the full issue-to-spec pipeline.

    Requirements: 86-REQ-2.* through 86-REQ-10.*
    """

    def __init__(
        self,
        platform: PlatformProtocol,
        config: NightShiftConfig,
        repo_root: Path,
    ) -> None:
        self._platform = platform
        self._config = config
        self._repo_root = repo_root
        self._cost: float = 0.0

        # Resolve model tier with fallback to ADVANCED (86-REQ-9.E2)
        try:
            entry = resolve_model(config.spec_gen_model_tier)
            self._model_id = entry.model_id
        except ConfigError:
            logger.warning(
                "Invalid model tier '%s'; falling back to ADVANCED",
                config.spec_gen_model_tier,
            )
            self._model_id = TIER_DEFAULTS[ModelTier.ADVANCED]

        # Lazy-init AI client
        self._ai_client: Any = None

    def _get_ai_client(self) -> Any:
        """Lazily create the async Anthropic client."""
        if self._ai_client is None:
            from agent_fox.core.client import create_async_anthropic_client

            self._ai_client = create_async_anthropic_client()
        return self._ai_client

    # ------------------------------------------------------------------
    # Fox comment helpers (86-REQ-5.3)
    # ------------------------------------------------------------------

    def _is_fox_comment(self, comment: IssueComment) -> bool:
        """Check if a comment is a fox comment.

        Requirements: 86-REQ-5.3
        """
        return comment.body.strip().startswith("## Agent Fox")

    def _count_clarification_rounds(self, comments: list[IssueComment]) -> int:
        """Count the number of fox clarification comments.

        Requirements: 86-REQ-5.1
        """
        return sum(1 for c in comments if self._is_fox_comment(c) and "Clarification" in c.body)

    def _has_new_human_comment(self, comments: list[IssueComment]) -> bool:
        """Check if there's a human comment after the last fox comment.

        Requirements: 86-REQ-2.3, 86-REQ-2.4
        """
        if not comments:
            return False

        last_fox_idx = -1
        for i, c in enumerate(comments):
            if self._is_fox_comment(c):
                last_fox_idx = i

        if last_fox_idx == -1:
            # No fox comments at all — treat as having a new human comment
            return True

        # Check if any non-fox comment exists after the last fox comment
        for c in comments[last_fox_idx + 1 :]:
            if not self._is_fox_comment(c):
                return True

        return False

    # ------------------------------------------------------------------
    # Spec numbering (86-REQ-6.3, 86-REQ-6.E2)
    # ------------------------------------------------------------------

    def _find_next_spec_number(self) -> int:
        """Find the next available spec number.

        Scans .specs/ for the highest existing numeric prefix and returns
        the next sequential number. Returns 1 if no specs exist.

        Requirements: 86-REQ-6.3, 86-REQ-6.E2
        """
        specs_dir = self._repo_root / ".specs"
        if not specs_dir.is_dir():
            return 1

        max_prefix = 0
        for entry in specs_dir.iterdir():
            if not entry.is_dir():
                continue
            match = _SPEC_DIR_PATTERN.match(entry.name)
            if match:
                prefix = int(match.group(1))
                max_prefix = max(max_prefix, prefix)

        return max_prefix + 1 if max_prefix > 0 else 1

    def _spec_name_from_title(self, title: str, prefix: int) -> str:
        """Derive a spec folder name from an issue title.

        Requirements: 86-REQ-6.3
        """
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        slug = slug[:40]
        # Ensure slug is non-empty
        if not slug:
            slug = "untitled"
        return f"{prefix:02d}_{slug}"

    # ------------------------------------------------------------------
    # Label transition (86-REQ-3.1)
    # ------------------------------------------------------------------

    async def _transition_label(
        self,
        issue_number: int,
        from_label: str,
        to_label: str,
    ) -> None:
        """Transition an issue from one label to another.

        Assigns the new label first, then removes the old label,
        ensuring the issue always has at least one af:spec-* label.

        Requirements: 86-REQ-3.1
        """
        logger.info(
            "Issue #%d: transitioning %s -> %s",
            issue_number,
            from_label,
            to_label,
        )
        await self._platform.assign_label(issue_number, to_label)
        await self._platform.remove_label(issue_number, from_label)

    # ------------------------------------------------------------------
    # Comment formatters
    # ------------------------------------------------------------------

    def _format_clarification_comment(
        self,
        questions: list[str],
        round_num: int,
        max_rounds: int,
    ) -> str:
        """Format a clarification comment with numbered questions.

        Requirements: 86-REQ-4.2
        """
        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
        return (
            f"## Agent Fox -- Clarification Needed\n\n"
            f"**Round {round_num + 1} of {max_rounds}**\n\n"
            f"I need some additional information before I can generate "
            f"the specification:\n\n"
            f"{numbered}\n\n"
            f"Please reply to this comment with your answers."
        )

    def _format_completion_comment(
        self,
        package: SpecPackage,
        commit_hash: str,
    ) -> str:
        """Format a completion comment with spec details.

        Requirements: 86-REQ-8.4
        """
        file_list = "\n".join(f"- `{f}`" for f in sorted(package.files.keys()))
        return (
            f"## Agent Fox -- Specification Created\n\n"
            f"Spec folder: `.specs/{package.spec_name}/`\n\n"
            f"Files:\n{file_list}\n\n"
            f"Commit: `{commit_hash}`"
        )

    def _format_escalation_comment(
        self,
        open_questions: list[str],
    ) -> str:
        """Format an escalation comment listing remaining questions.

        Requirements: 86-REQ-5.2
        """
        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(open_questions))
        return (
            f"## Agent Fox -- Specification Blocked\n\n"
            f"Maximum clarification rounds reached. The following questions "
            f"remain unresolved:\n\n"
            f"{numbered}\n\n"
            f"Please provide more detail on the issue description or "
            f"request manual spec creation."
        )

    def _format_budget_comment(
        self,
        cost: float,
        limit: float,
    ) -> str:
        """Format a budget-exceeded comment.

        Requirements: 86-REQ-10.2
        """
        return (
            f"## Agent Fox -- Specification Blocked\n\n"
            f"Budget exceeded during spec generation.\n\n"
            f"- Cost so far: ${cost:.2f}\n"
            f"- Budget limit: ${limit:.2f}\n\n"
            f"The generation has been aborted. Please adjust the budget "
            f"or simplify the issue scope."
        )

    def _format_duplicate_comment(
        self,
        result: DuplicateCheckResult,
    ) -> str:
        """Format a duplicate detection comment."""
        return (
            f"## Agent Fox -- Potential Duplicate Detected\n\n"
            f"This issue appears to overlap with an existing spec: "
            f"**{result.overlapping_spec}**\n\n"
            f"{result.explanation}\n\n"
            f"Would you like to **supersede** the existing spec, or should "
            f"I skip this issue? Reply with 'supersede' to proceed."
        )

    def _format_error_comment(
        self,
        error: Exception,
        branch_name: str | None = None,
    ) -> str:
        """Format an error comment for blocked issues."""
        msg = (
            f"## Agent Fox -- Specification Blocked\n\n"
            f"An error occurred during spec generation:\n\n"
            f"```\n{error!s}\n```\n"
        )
        if branch_name:
            msg += f"\nThe partial work is on branch `{branch_name}`. You can recover it manually."
        return msg

    # ------------------------------------------------------------------
    # Reference harvesting (86-REQ-4.3)
    # ------------------------------------------------------------------

    async def _harvest_references(
        self,
        body: str,
        comments: list[IssueComment],
    ) -> list[ReferencedIssue]:
        """Parse #N references from body and comments, fetch each.

        Requirements: 86-REQ-4.3, 86-REQ-4.E1
        """
        # Collect all unique issue numbers from body and comments
        all_text = body + "\n" + "\n".join(c.body for c in comments)
        matches = _REFERENCE_PATTERN.findall(all_text)
        unique_numbers = sorted(set(int(m) for m in matches))

        refs: list[ReferencedIssue] = []
        for num in unique_numbers:
            try:
                issue = await self._platform.get_issue(num)
                issue_comments = await self._platform.list_issue_comments(num)
                refs.append(
                    ReferencedIssue(
                        number=num,
                        title=issue.title,
                        body=issue.body or "",
                        comments=issue_comments,
                    )
                )
                logger.debug("Harvested reference #%d: %s", num, issue.title)
            except IntegrationError:
                logger.warning(
                    "Referenced issue #%d is inaccessible; skipping",
                    num,
                )
        return refs

    # ------------------------------------------------------------------
    # AI-powered methods
    # ------------------------------------------------------------------

    async def _analyze_issue(
        self,
        issue: IssueResult,
        comments: list[IssueComment],
        context: _SpecGenContext,
    ) -> AnalysisResult:
        """Analyze issue clarity via AI.

        Requirements: 86-REQ-4.1, 86-REQ-4.E2
        """
        # Build context string
        ref_context = ""
        for ref in context.referenced_issues:
            ref_context += f"\n### Referenced Issue #{ref.number}: {ref.title}\n{ref.body}\n"

        spec_context = ""
        for spec in context.existing_specs:
            spec_context += f"\n- {spec.name}"

        comment_text = "\n".join(f"**{c.user}** ({c.created_at}):\n{c.body}" for c in comments)

        system_prompt = (
            "You are a specification analyst. Analyze whether the following "
            "GitHub issue contains enough information to generate a complete "
            "software specification. Respond with JSON: "
            '{"clear": true/false, "questions": ["..."], "summary": "..."}'
        )

        user_prompt = (
            f"# Issue: {issue.title}\n\n"
            f"## Body\n{issue.body or '(empty)'}\n\n"
            f"## Comments\n{comment_text or '(none)'}\n\n"
            f"## Referenced Issues\n{ref_context or '(none)'}\n\n"
            f"## Existing Specs\n{spec_context or '(none)'}\n"
        )

        client = self._get_ai_client()
        response = await cached_messages_create(
            client,
            model=self._model_id,
            max_tokens=2000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        # Track cost
        self._track_cost(response)

        # Parse response
        text = _extract_text(response, "issue analysis")
        try:
            data = extract_json_object(text)
        except Exception:
            data = {"clear": False, "questions": ["Could not parse analysis"], "summary": text}

        return AnalysisResult(
            clear=bool(data.get("clear", False)),
            questions=list(data.get("questions", [])),
            summary=str(data.get("summary", "")),
        )

    async def _check_duplicates(
        self,
        issue: IssueResult,
        existing_specs: list[SpecInfo],
    ) -> DuplicateCheckResult:
        """Check for duplicate/overlapping specs via AI.

        Requirements: 86-REQ-7.1, 86-REQ-7.E1
        """
        if not existing_specs:
            return DuplicateCheckResult(is_duplicate=False)

        spec_list = "\n".join(f"- {s.name}" for s in existing_specs)

        system_prompt = (
            "You are a specification deduplication checker. Compare the issue "
            "against existing specs and determine if it overlaps. Respond with "
            'JSON: {"is_duplicate": true/false, "overlapping_spec": "name_or_null", '
            '"explanation": "..."}'
        )

        user_prompt = (
            f"# Issue: {issue.title}\n\n## Body\n{issue.body or '(empty)'}\n\n## Existing Specs\n{spec_list}\n"
        )

        client = self._get_ai_client()
        response = await cached_messages_create(
            client,
            model=self._model_id,
            max_tokens=1000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
        )

        self._track_cost(response)

        text = _extract_text(response, "duplicate check")
        try:
            data = extract_json_object(text)
        except Exception:
            data = {"is_duplicate": False}

        return DuplicateCheckResult(
            is_duplicate=bool(data.get("is_duplicate", False)),
            overlapping_spec=data.get("overlapping_spec"),
            explanation=str(data.get("explanation", "")),
        )

    async def _generate_spec_package(
        self,
        issue: IssueResult,
        comments: list[IssueComment],
        context: _SpecGenContext,
    ) -> SpecPackage:
        """Generate all 5 spec files via sequential AI calls.

        Requirements: 86-REQ-6.1, 86-REQ-6.2, 86-REQ-6.4,
                      86-REQ-10.1, 86-REQ-10.2
        """
        spec_number = self._find_next_spec_number()
        spec_name = self._spec_name_from_title(issue.title, spec_number)

        comment_text = "\n".join(f"**{c.user}** ({c.created_at}):\n{c.body}" for c in comments)

        # Build PRD from issue body + comments + source section
        prd_content = f"{issue.body or ''}\n\n"
        if comment_text:
            prd_content += f"## Clarification\n\n{comment_text}\n\n"

        # Add supersedes section if applicable (86-REQ-7.3)
        supersedes = getattr(context, "supersedes", None)
        if supersedes:
            prd_content += f"## Supersedes\n\n{supersedes}\n\n"

        prd_content += f"## Source\n\nGenerated from: {issue.html_url}\n"

        files: dict[str, str] = {"prd.md": prd_content}

        # Generate remaining documents sequentially
        doc_order = ["requirements.md", "design.md", "test_spec.md", "tasks.md"]
        prev_docs = f"# PRD\n\n{prd_content}"

        for doc_name in doc_order:
            # Check budget before each call (86-REQ-10.2)
            max_budget = self._config.max_budget_usd
            if max_budget and max_budget > 0 and self._cost >= max_budget:
                raise _BudgetExceededError(self._cost, max_budget)

            system_prompt = (
                f"You are a specification writer. Generate the {doc_name} "
                f"document for a software specification based on the PRD and "
                f"any previously generated documents. Return ONLY the document "
                f"content in markdown format."
            )

            user_prompt = f"# Context\n\n{prev_docs}\n\n# Task\n\nGenerate {doc_name} for spec '{spec_name}'."

            client = self._get_ai_client()
            response = await cached_messages_create(
                client,
                model=self._model_id,
                max_tokens=8000,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
            )

            self._track_cost(response)

            doc_content = _extract_text(response, f"spec generation ({doc_name})")
            files[doc_name] = doc_content
            prev_docs += f"\n\n# {doc_name}\n\n{doc_content}"

        return SpecPackage(
            spec_name=spec_name,
            files=files,
            source_issue_url=issue.html_url,
        )

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    def _track_cost(self, response: Any) -> None:
        """Track cost from an API response.

        Requirements: 86-REQ-10.1
        """
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)

        # Simple cost estimate (per-token pricing approximation)
        # Real pricing would use calculate_cost() with PricingConfig,
        # but for tracking purposes we use a rough estimate.
        cost = (input_tokens * 0.000015) + (output_tokens * 0.000075)
        self._cost += cost
        logger.debug(
            "API cost: $%.4f (cumulative: $%.4f, tokens: %d in / %d out)",
            cost,
            self._cost,
            input_tokens,
            output_tokens,
        )

    # ------------------------------------------------------------------
    # Landing workflow
    # ------------------------------------------------------------------

    async def _land_spec(
        self,
        package: SpecPackage,
        issue_number: int,
    ) -> str:
        """Create branch, write files, commit, merge. Returns commit hash.

        Requirements: 86-REQ-8.1, 86-REQ-8.2, 86-REQ-8.3,
                      86-REQ-8.E1, 86-REQ-8.E2
        """
        branch_name = f"spec/{package.spec_name}"
        spec_dir = self._repo_root / ".specs" / package.spec_name
        commit_msg = f"feat(spec): generate {package.spec_name} from #{issue_number}"

        # Try to create branch, handle collision (86-REQ-8.E1)
        suffix = 0
        actual_branch = branch_name
        while True:
            result = subprocess.run(
                ["git", "checkout", "-b", actual_branch, "develop"],
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
            )
            if result.returncode == 0:
                break
            suffix += 1
            actual_branch = f"{branch_name}-{suffix + 1}"
            if suffix > 10:
                raise RuntimeError(f"Could not create branch: {branch_name}")

        # Write spec files
        spec_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in package.files.items():
            (spec_dir / filename).write_text(content)

        # Stage and commit
        subprocess.run(
            ["git", "add", str(spec_dir)],
            capture_output=True,
            cwd=str(self._repo_root),
        )
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            cwd=str(self._repo_root),
        )

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(self._repo_root),
        )
        commit_hash = hash_result.stdout.strip()

        # Merge strategy
        if self._config.merge_strategy == "pr":
            await self._platform.create_pull_request(
                title=commit_msg,
                body=f"Auto-generated spec from issue #{issue_number}",
                head=actual_branch,
                base="develop",
            )
        else:
            # Direct merge (86-REQ-8.2)
            subprocess.run(
                ["git", "checkout", "develop"],
                capture_output=True,
                cwd=str(self._repo_root),
            )
            merge_result = subprocess.run(
                ["git", "merge", actual_branch],
                capture_output=True,
                text=True,
                cwd=str(self._repo_root),
            )
            if merge_result.returncode != 0:
                raise RuntimeError(f"Merge failed for branch {actual_branch}: {merge_result.stderr}")
            # Delete feature branch
            subprocess.run(
                ["git", "branch", "-d", actual_branch],
                capture_output=True,
                cwd=str(self._repo_root),
            )

        return commit_hash

    # ------------------------------------------------------------------
    # Main orchestration (86-REQ-3.2 through 86-REQ-3.4)
    # ------------------------------------------------------------------

    async def process_issue(self, issue: IssueResult) -> SpecGenResult:
        """Full pipeline: analyze, clarify or generate, land.

        Requirements: 86-REQ-3.2, 86-REQ-3.3, 86-REQ-3.4,
                      86-REQ-4.2, 86-REQ-5.2, 86-REQ-7.2, 86-REQ-7.3,
                      86-REQ-6.E1
        """
        self._cost = 0.0
        branch_name: str | None = None

        try:
            # Step 1: Transition to analyzing (86-REQ-3.2)
            await self._transition_label(issue.number, LABEL_SPEC, LABEL_ANALYZING)

            # Step 2: Fetch comments
            comments = await self._platform.list_issue_comments(issue.number)

            # Step 3: Harvest references (86-REQ-4.3)
            referenced_issues = await self._harvest_references(issue.body or "", comments)

            # Step 4: Gather existing specs for context
            existing_specs = self._discover_existing_specs()

            context = _SpecGenContext(
                referenced_issues=referenced_issues,
                existing_specs=existing_specs,
            )

            # Step 5: Check duplicates (86-REQ-7.1)
            dup_result = await self._check_duplicates(issue, existing_specs)
            if dup_result.is_duplicate:
                # Post duplicate comment and transition to pending (86-REQ-7.2)
                comment = self._format_duplicate_comment(dup_result)
                await self._platform.add_issue_comment(issue.number, comment)
                await self._transition_label(issue.number, LABEL_ANALYZING, LABEL_PENDING)
                return SpecGenResult(
                    outcome=SpecGenOutcome.PENDING,
                    issue_number=issue.number,
                    cost=self._cost,
                )

            # Step 6: Count clarification rounds (86-REQ-5.1)
            rounds = self._count_clarification_rounds(comments)

            # Step 7: Analyze issue (86-REQ-4.1)
            analysis = await self._analyze_issue(issue, comments, context)

            if not analysis.clear:
                # Check if max rounds reached (86-REQ-5.2)
                if rounds >= self._config.max_clarification_rounds:
                    # Escalate (86-REQ-5.2)
                    comment = self._format_escalation_comment(analysis.questions)
                    await self._platform.add_issue_comment(issue.number, comment)
                    await self._transition_label(issue.number, LABEL_ANALYZING, LABEL_BLOCKED)
                    return SpecGenResult(
                        outcome=SpecGenOutcome.BLOCKED,
                        issue_number=issue.number,
                        cost=self._cost,
                    )

                # Post clarification (86-REQ-4.2)
                comment = self._format_clarification_comment(
                    analysis.questions, rounds, self._config.max_clarification_rounds
                )
                await self._platform.add_issue_comment(issue.number, comment)
                await self._transition_label(issue.number, LABEL_ANALYZING, LABEL_PENDING)
                return SpecGenResult(
                    outcome=SpecGenOutcome.PENDING,
                    issue_number=issue.number,
                    cost=self._cost,
                )

            # Step 8: Transition to generating (86-REQ-3.3)
            await self._transition_label(issue.number, LABEL_ANALYZING, LABEL_GENERATING)

            # Step 9: Generate spec package (86-REQ-6.1)
            package = await self._generate_spec_package(issue, comments, context)
            branch_name = f"spec/{package.spec_name}"

            # Step 10: Land spec (86-REQ-8.1)
            commit_hash = await self._land_spec(package, issue.number)

            # Step 11: Post completion comment (86-REQ-8.4)
            completion_comment = self._format_completion_comment(package, commit_hash)
            await self._platform.add_issue_comment(issue.number, completion_comment)

            # Step 12: Transition to done and close (86-REQ-3.4)
            await self._transition_label(issue.number, LABEL_GENERATING, LABEL_DONE)
            await self._platform.close_issue(issue.number)

            return SpecGenResult(
                outcome=SpecGenOutcome.GENERATED,
                issue_number=issue.number,
                spec_name=package.spec_name,
                commit_hash=commit_hash,
                cost=self._cost,
            )

        except _BudgetExceededError as exc:
            # Budget exceeded (86-REQ-10.2)
            comment = self._format_budget_comment(exc.cost, exc.limit)
            await self._platform.add_issue_comment(issue.number, comment)
            await self._transition_label(issue.number, LABEL_GENERATING, LABEL_BLOCKED)
            return SpecGenResult(
                outcome=SpecGenOutcome.BLOCKED,
                issue_number=issue.number,
                cost=self._cost,
            )

        except Exception as exc:
            # General error (86-REQ-6.E1, 86-REQ-8.E2)
            logger.exception("Error processing issue #%d", issue.number)
            comment = self._format_error_comment(exc, branch_name=branch_name)
            try:
                await self._platform.add_issue_comment(issue.number, comment)
                await self._platform.assign_label(issue.number, LABEL_BLOCKED)
            except Exception:
                logger.exception("Failed to post error comment on issue #%d", issue.number)

            return SpecGenResult(
                outcome=SpecGenOutcome.BLOCKED,
                issue_number=issue.number,
                cost=self._cost,
            )

    def _discover_existing_specs(self) -> list[SpecInfo]:
        """Discover existing specs, returning empty list if none found.

        Wraps discover_specs() to handle PlanError gracefully.
        """
        from agent_fox.core.errors import PlanError
        from agent_fox.spec.discovery import discover_specs

        specs_dir = self._repo_root / ".specs"
        try:
            return discover_specs(specs_dir)
        except PlanError:
            return []


# ---------------------------------------------------------------------------
# Internal exceptions
# ---------------------------------------------------------------------------


class _BudgetExceededError(Exception):
    """Raised when the per-spec budget is exceeded."""

    def __init__(self, cost: float, limit: float) -> None:
        self.cost = cost
        self.limit = limit
        super().__init__(f"Budget exceeded: ${cost:.2f} > ${limit:.2f}")
