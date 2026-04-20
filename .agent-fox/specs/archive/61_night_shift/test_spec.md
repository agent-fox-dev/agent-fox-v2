# Test Specification: Night Shift

## Overview

Test cases map to the 9 requirements and 8 correctness properties from the
design document. Unit tests validate individual components (finding format,
config, scheduling, consolidation, in-memory spec). Property tests validate
invariants (format universality, cost monotonicity, bijection, isolation).
Integration tests validate end-to-end flows with mocked platform and backend.

## Test Cases

### TS-61-1: Night-shift command starts event loop

**Requirement:** 61-REQ-1.1
**Type:** integration
**Description:** Verify that `night-shift` starts a continuous event loop.

**Preconditions:**
- Valid platform config with GitHub type and token.
- Mock platform and backend.

**Input:**
- Invoke `night_shift_cmd` with valid config.
- Send SIGINT after a short delay.

**Expected:**
- Engine `run()` is called.
- Event loop runs until SIGINT.
- Exit code is 0.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, mock_platform)
task = asyncio.create_task(engine.run())
await asyncio.sleep(0.1)
send SIGINT
result = await task
ASSERT result.is_shutting_down == True
```

### TS-61-2: Auto flag assigns af:fix label

**Requirement:** 61-REQ-1.2
**Type:** unit
**Description:** Verify that `--auto` causes created issues to get the
`af:fix` label.

**Preconditions:**
- Engine created with `auto_fix=True`.
- Mock platform.

**Input:**
- A single finding from a hunt scan.

**Expected:**
- `platform.assign_label(issue_number, "af:fix")` is called after issue
  creation.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, mock_platform, auto_fix=True)
await engine._run_hunt_scan()
ASSERT mock_platform.assign_label.called_with(ANY, "af:fix")
```

### TS-61-3: Graceful shutdown on SIGINT

**Requirement:** 61-REQ-1.3
**Type:** integration
**Description:** Verify that a single SIGINT completes the current operation
before exiting.

**Preconditions:**
- Engine running with a long-running hunt scan.

**Input:**
- Send SIGINT during hunt scan.

**Expected:**
- Hunt scan completes.
- Engine exits with state `is_shutting_down=True`.

**Assertion pseudocode:**
```
engine = NightShiftEngine(config, mock_platform)
task = asyncio.create_task(engine.run())
# Wait for hunt scan to start
await hunt_scan_started_event.wait()
send SIGINT
result = await task
ASSERT result.hunt_scans_completed >= 1
```

### TS-61-4: Issue check runs at configured interval

**Requirement:** 61-REQ-2.1
**Type:** unit
**Description:** Verify that issue checks are scheduled at the configured
interval.

**Preconditions:**
- `issue_check_interval` set to 120 seconds.

**Input:**
- Run scheduler for 250 seconds (simulated).

**Expected:**
- Issue check called 3 times (t=0, t=120, t=240).

**Assertion pseudocode:**
```
scheduler = Scheduler(issue_interval=120, hunt_interval=99999)
call_count = 0
async def on_issue_check(): call_count += 1
scheduler.on_issue_check = on_issue_check
await scheduler.run_for(250)
ASSERT call_count == 3
```

### TS-61-5: Hunt scan runs at configured interval

**Requirement:** 61-REQ-2.2
**Type:** unit
**Description:** Verify that hunt scans are scheduled at the configured
interval.

**Preconditions:**
- `hunt_scan_interval` set to 100 seconds.

**Input:**
- Run scheduler for 250 seconds (simulated).

**Expected:**
- Hunt scan called 3 times (t=0, t=100, t=200).

**Assertion pseudocode:**
```
scheduler = Scheduler(issue_interval=99999, hunt_interval=100)
call_count = 0
async def on_hunt_scan(): call_count += 1
scheduler.on_hunt_scan = on_hunt_scan
await scheduler.run_for(250)
ASSERT call_count == 3
```

### TS-61-6: Initial scan on startup

**Requirement:** 61-REQ-2.3
**Type:** unit
**Description:** Verify that both issue check and hunt scan run immediately on
startup.

**Preconditions:**
- Default intervals.

**Input:**
- Start scheduler, stop after first tick.

**Expected:**
- Both callbacks invoked once before any interval elapses.

**Assertion pseudocode:**
```
scheduler = Scheduler(issue_interval=900, hunt_interval=14400)
issue_checked = False
hunt_scanned = False
scheduler.on_issue_check = lambda: issue_checked = True
scheduler.on_hunt_scan = lambda: hunt_scanned = True
await scheduler.run_for(1)
ASSERT issue_checked == True
ASSERT hunt_scanned == True
```

### TS-61-7: Seven built-in hunt categories registered

**Requirement:** 61-REQ-3.1
**Type:** unit
**Description:** Verify that all seven categories are registered.

**Preconditions:**
- Default configuration.

**Input:**
- Query hunt category registry.

**Expected:**
- Registry contains exactly: dependency_freshness, todo_fixme,
  test_coverage, deprecated_api, linter_debt, dead_code,
  documentation_drift.

**Assertion pseudocode:**
```
registry = HuntCategoryRegistry()
names = {cat.name for cat in registry.all()}
ASSERT names == {"dependency_freshness", "todo_fixme", "test_coverage",
                 "deprecated_api", "linter_debt", "dead_code",
                 "documentation_drift"}
```

### TS-61-8: Only enabled categories execute

**Requirement:** 61-REQ-3.2
**Type:** unit
**Description:** Verify that disabled categories are skipped during a scan.

**Preconditions:**
- Config with `todo_fixme = false`, all others enabled.

**Input:**
- Run hunt scan.

**Expected:**
- `todo_fixme` category `detect()` is NOT called.
- All other categories `detect()` IS called.

**Assertion pseudocode:**
```
config.night_shift.categories.todo_fixme = False
scanner = HuntScanner(registry, config)
await scanner.run(project_root)
ASSERT mock_todo_fixme.detect.not_called()
ASSERT mock_linter_debt.detect.called()
```

### TS-61-9: Hunt category interface contract

**Requirement:** 61-REQ-3.3
**Type:** unit
**Description:** Verify that the hunt category interface returns findings in
the standardised format.

**Preconditions:**
- A mock hunt category implementation.

**Input:**
- Call `detect()` on the category.

**Expected:**
- Returns `list[Finding]` where each finding has all required fields.

**Assertion pseudocode:**
```
category = MockHuntCategory()
findings = await category.detect(project_root, config)
ASSERT isinstance(findings, list)
for f in findings:
    ASSERT isinstance(f, Finding)
    ASSERT f.category != ""
    ASSERT f.title != ""
    ASSERT f.severity in ("critical", "major", "minor", "info")
```

### TS-61-10: Parallel category execution

**Requirement:** 61-REQ-3.4
**Type:** integration
**Description:** Verify that independent hunt categories execute in parallel.

**Preconditions:**
- Multiple categories enabled, each with a delay.

**Input:**
- Run hunt scan with 3 categories, each taking 0.1s.

**Expected:**
- Total scan time < 0.3s (not serialised).

**Assertion pseudocode:**
```
start = time.monotonic()
await scanner.run(project_root)
elapsed = time.monotonic() - start
ASSERT elapsed < 0.25  # parallel, not 0.3 serial
```

### TS-61-11: Static tooling runs before AI analysis

**Requirement:** 61-REQ-4.1, 61-REQ-4.2
**Type:** unit
**Description:** Verify the two-phase detection order.

**Preconditions:**
- A hunt category with both static tool and AI agent.
- Mock backend.

**Input:**
- Run category `detect()`.

**Expected:**
- Static tool output is passed to the AI agent prompt.
- AI agent is invoked after static tool completes.

**Assertion pseudocode:**
```
category = DependencyFreshnessCategory(config, backend)
findings = await category.detect(project_root, config)
ASSERT mock_static_tool.called_before(mock_ai_agent)
ASSERT "static tool output" in mock_ai_agent.last_prompt
```

### TS-61-12: Category-specific prompt templates

**Requirement:** 61-REQ-4.3
**Type:** unit
**Description:** Verify that each category uses its own prompt template.

**Preconditions:**
- Category registry with all categories.

**Input:**
- Inspect prompt templates for each category.

**Expected:**
- Each category has a distinct, non-empty prompt template.

**Assertion pseudocode:**
```
registry = HuntCategoryRegistry()
templates = {cat.name: cat.prompt_template for cat in registry.all()}
ASSERT len(templates) == 7
ASSERT len(set(templates.values())) == 7  # all distinct
for t in templates.values():
    ASSERT len(t) > 0
```

### TS-61-13: Finding grouping by root cause

**Requirement:** 61-REQ-5.1
**Type:** unit
**Description:** Verify that findings are grouped by root cause (group_key).

**Preconditions:**
- Multiple findings with shared and distinct group_keys.

**Input:**
- 4 findings: 2 with group_key "unused-imports", 2 with "missing-docstring".

**Expected:**
- 2 finding groups produced.

**Assertion pseudocode:**
```
findings = [
    Finding(group_key="unused-imports", ...),
    Finding(group_key="unused-imports", ...),
    Finding(group_key="missing-docstring", ...),
    Finding(group_key="missing-docstring", ...),
]
groups = consolidate_findings(findings)
ASSERT len(groups) == 2
ASSERT len(groups[0].findings) == 2
ASSERT len(groups[1].findings) == 2
```

### TS-61-14: One issue per finding group

**Requirement:** 61-REQ-5.2
**Type:** integration
**Description:** Verify that exactly one platform issue is created per group.

**Preconditions:**
- Mock platform.
- 3 finding groups.

**Input:**
- Create issues from 3 finding groups.

**Expected:**
- `platform.create_issue()` called exactly 3 times.

**Assertion pseudocode:**
```
groups = [FindingGroup(...), FindingGroup(...), FindingGroup(...)]
await create_issues_from_groups(groups, mock_platform)
ASSERT mock_platform.create_issue.call_count == 3
```

### TS-61-15: Issue body contains required fields

**Requirement:** 61-REQ-5.3
**Type:** unit
**Description:** Verify that issue body includes category, severity, files,
and suggested fix.

**Preconditions:**
- A finding group with known values.

**Input:**
- Build issue body from a finding group.

**Expected:**
- Body contains category name, severity, file list, and remediation text.

**Assertion pseudocode:**
```
group = FindingGroup(
    category="linter_debt",
    findings=[Finding(severity="minor", affected_files=["foo.py"], ...)],
    ...
)
body = build_issue_body(group)
ASSERT "linter_debt" in body
ASSERT "minor" in body
ASSERT "foo.py" in body
ASSERT "suggested" in body.lower() or "remediation" in body.lower()
```

### TS-61-16: In-memory spec from issue

**Requirement:** 61-REQ-6.1
**Type:** unit
**Description:** Verify that an in-memory spec is built from issue content.

**Preconditions:**
- An issue with title "Fix unused imports" and body with details.

**Input:**
- Build in-memory spec from issue.

**Expected:**
- `InMemorySpec` with populated `task_prompt`, `system_context`,
  `branch_name`.

**Assertion pseudocode:**
```
issue = IssueResult(number=42, title="Fix unused imports", ...)
issue_body = "Remove unused imports in engine/ ..."
spec = build_in_memory_spec(issue, issue_body)
ASSERT spec.issue_number == 42
ASSERT "unused imports" in spec.task_prompt.lower()
ASSERT spec.branch_name.startswith("fix/")
```

### TS-61-17: Fix branch naming

**Requirement:** 61-REQ-6.2
**Type:** unit
**Description:** Verify branch name is `fix/{sanitised-title}`.

**Preconditions:**
- Issue title with special characters: "Fix: unused imports (engine/)"

**Input:**
- Generate branch name from issue title.

**Expected:**
- Branch name is sanitised: `fix/fix-unused-imports-engine`.

**Assertion pseudocode:**
```
branch = sanitise_branch_name("Fix: unused imports (engine/)")
ASSERT branch == "fix/fix-unused-imports-engine"
ASSERT "/" not in branch[4:]  # no extra slashes after "fix/"
```

### TS-61-18: Full archetype pipeline for fixes

**Requirement:** 61-REQ-6.3
**Type:** integration
**Description:** Verify that fixes use the full archetype pipeline.

**Preconditions:**
- Mock session runner and platform.
- Archetypes skeptic, coder, verifier enabled.

**Input:**
- Process an af:fix issue.

**Expected:**
- Session runner invoked with skeptic, coder, and verifier archetypes
  (in that order or as configured).

**Assertion pseudocode:**
```
pipeline = FixPipeline(config, mock_platform)
await pipeline.process_issue(issue)
archetypes_used = [call.archetype for call in mock_session_runner.calls]
ASSERT "skeptic" in archetypes_used
ASSERT "coder" in archetypes_used
ASSERT "verifier" in archetypes_used
```

### TS-61-19: Fix progress documented in issue

**Requirement:** 61-REQ-6.4
**Type:** integration
**Description:** Verify that implementation details are posted as issue
comments.

**Preconditions:**
- Mock platform.

**Input:**
- Run fix pipeline on an issue.

**Expected:**
- At least one comment posted to the issue during the fix process.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue)
ASSERT mock_platform.add_issue_comment.call_count >= 1
```

### TS-61-20: PR created on fix success

**Requirement:** 61-REQ-7.1
**Type:** integration
**Description:** Verify that one PR is created per successful fix.

**Preconditions:**
- Mock platform.
- Fix session completes successfully.

**Input:**
- Process a fixable issue.

**Expected:**
- `platform.create_pr()` called exactly once.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue)
ASSERT mock_platform.create_pr.call_count == 1
```

### TS-61-21: PR references originating issue

**Requirement:** 61-REQ-7.2
**Type:** unit
**Description:** Verify that the PR body contains an issue reference.

**Preconditions:**
- Issue number 42.

**Input:**
- Build PR body for issue #42.

**Expected:**
- PR body contains "Fixes #42" or "Closes #42".

**Assertion pseudocode:**
```
body = build_pr_body(issue_number=42, summary="Removed unused imports")
ASSERT "#42" in body
ASSERT "Fixes #42" in body or "Closes #42" in body
```

### TS-61-22: Issue comment links to PR

**Requirement:** 61-REQ-7.3
**Type:** integration
**Description:** Verify that a comment with PR link is posted on the issue.

**Preconditions:**
- Mock platform that returns PR URL on `create_pr`.

**Input:**
- Complete a fix successfully.

**Expected:**
- Comment posted containing the PR URL.

**Assertion pseudocode:**
```
mock_platform.create_pr.return_value = "https://github.com/.../pull/99"
await pipeline.process_issue(issue)
comments = mock_platform.add_issue_comment.call_args_list
ASSERT any("pull/99" in str(c) for c in comments)
```

### TS-61-23: Platform protocol completeness

**Requirement:** 61-REQ-8.1
**Type:** unit
**Description:** Verify that PlatformProtocol defines all required methods.

**Preconditions:**
- None.

**Input:**
- Inspect PlatformProtocol.

**Expected:**
- Protocol has: `create_issue`, `list_issues_by_label`,
  `add_issue_comment`, `assign_label`, `create_pr`, `close`.

**Assertion pseudocode:**
```
methods = {m for m in dir(PlatformProtocol) if not m.startswith("_")}
required = {"create_issue", "list_issues_by_label", "add_issue_comment",
            "assign_label", "create_pr", "close"}
ASSERT required.issubset(methods)
```

### TS-61-24: GitHub implements platform protocol

**Requirement:** 61-REQ-8.2
**Type:** unit
**Description:** Verify that GitHubPlatform satisfies PlatformProtocol.

**Preconditions:**
- None.

**Input:**
- Check runtime protocol compliance.

**Expected:**
- `isinstance(GitHubPlatform(...), PlatformProtocol)` is True.

**Assertion pseudocode:**
```
gh = GitHubPlatform(owner="x", repo="y", token="t")
ASSERT isinstance(gh, PlatformProtocol)
```

### TS-61-25: Platform instantiation from config

**Requirement:** 61-REQ-8.3
**Type:** unit
**Description:** Verify that platform is instantiated from config.

**Preconditions:**
- Config with `[platform] type = "github"`.
- `GITHUB_PAT` env var set.

**Input:**
- Call platform factory with config.

**Expected:**
- Returns a `GitHubPlatform` instance.

**Assertion pseudocode:**
```
config.platform.type = "github"
platform = create_platform(config, project_root)
ASSERT isinstance(platform, GitHubPlatform)
```

### TS-61-26: NightShiftConfig defaults

**Requirement:** 61-REQ-9.1
**Type:** unit
**Description:** Verify default config values.

**Preconditions:**
- No `[night_shift]` section in config.

**Input:**
- Load default NightShiftConfig.

**Expected:**
- `issue_check_interval` == 900
- `hunt_scan_interval` == 14400

**Assertion pseudocode:**
```
cfg = NightShiftConfig()
ASSERT cfg.issue_check_interval == 900
ASSERT cfg.hunt_scan_interval == 14400
```

### TS-61-27: Category enable/disable config

**Requirement:** 61-REQ-9.2
**Type:** unit
**Description:** Verify category toggle configuration.

**Preconditions:**
- Config with `[night_shift.categories] dead_code = false`.

**Input:**
- Load config.

**Expected:**
- `dead_code` is False, all others True.

**Assertion pseudocode:**
```
cfg = NightShiftConfig(categories=NightShiftCategoryConfig(dead_code=False))
ASSERT cfg.categories.dead_code == False
ASSERT cfg.categories.linter_debt == True
ASSERT cfg.categories.todo_fixme == True
```

### TS-61-28: Cost limit honoured

**Requirement:** 61-REQ-9.3
**Type:** integration
**Description:** Verify that night-shift stops when max_cost is reached.

**Preconditions:**
- `max_cost = 1.0`.
- Fix session costs 0.6 per session.

**Input:**
- Process two issues.

**Expected:**
- First issue processed. Second issue skipped. Engine exits.

**Assertion pseudocode:**
```
config.orchestrator.max_cost = 1.0
engine = NightShiftEngine(config, mock_platform)
# Mock two af:fix issues, each costing 0.6
result = await engine.run()
ASSERT result.issues_fixed == 1
ASSERT result.total_cost <= 1.0
```

## Edge Case Tests

### TS-61-E1: Platform not configured

**Requirement:** 61-REQ-1.E1
**Type:** unit
**Description:** Verify abort when platform is not configured.

**Preconditions:**
- Config with `[platform] type = "none"`.

**Input:**
- Attempt to start night-shift.

**Expected:**
- Raises SystemExit with code 1.
- Error message mentions platform configuration.

**Assertion pseudocode:**
```
config.platform.type = "none"
with pytest.raises(SystemExit) as exc:
    validate_night_shift_prerequisites(config)
ASSERT exc.value.code == 1
```

### TS-61-E2: Cost limit reached

**Requirement:** 61-REQ-1.E2
**Type:** unit
**Description:** Verify engine stops on cost limit.

**Preconditions:**
- State with `total_cost = 9.5`, `max_cost = 10.0`.
- Next operation costs 0.6.

**Input:**
- Check cost limit.

**Expected:**
- `_check_cost_limit()` returns True (limit reached).

**Assertion pseudocode:**
```
engine.state.total_cost = 9.5
config.orchestrator.max_cost = 10.0
ASSERT engine._check_cost_limit() == True
```

### TS-61-E3: Platform API temporarily unavailable

**Requirement:** 61-REQ-2.E1
**Type:** integration
**Description:** Verify graceful handling of platform API failure.

**Preconditions:**
- Mock platform that raises `httpx.ConnectError` on first call.

**Input:**
- Run issue check.

**Expected:**
- Warning logged. No crash. Next interval proceeds normally.

**Assertion pseudocode:**
```
mock_platform.list_issues_by_label.side_effect = httpx.ConnectError("...")
await engine._run_issue_check()  # should not raise
ASSERT "warning" in caplog.text.lower()
```

### TS-61-E4: Hunt scan overlap prevention

**Requirement:** 61-REQ-2.E2
**Type:** unit
**Description:** Verify that overlapping hunt scans are skipped.

**Preconditions:**
- A hunt scan already in progress.

**Input:**
- Trigger a second hunt scan.

**Expected:**
- Second scan is skipped. Info message logged.

**Assertion pseudocode:**
```
engine._hunt_scan_in_progress = True
await engine._run_hunt_scan()
ASSERT "skipping" in caplog.text.lower() or "overlap" in caplog.text.lower()
```

### TS-61-E5: Hunt category agent failure

**Requirement:** 61-REQ-3.E1
**Type:** integration
**Description:** Verify that a failing category does not block others.

**Preconditions:**
- 3 categories: A (succeeds), B (raises RuntimeError), C (succeeds).

**Input:**
- Run hunt scan.

**Expected:**
- Categories A and C produce findings.
- Category B failure is logged.

**Assertion pseudocode:**
```
mock_cat_b.detect.side_effect = RuntimeError("agent timeout")
findings = await scanner.run(project_root)
ASSERT len(findings) > 0  # from A and C
ASSERT "RuntimeError" in caplog.text
```

### TS-61-E6: No static tooling available

**Requirement:** 61-REQ-4.E1
**Type:** unit
**Description:** Verify AI-only analysis when no static tools available.

**Preconditions:**
- Category with no static tool configured.

**Input:**
- Run category detect().

**Expected:**
- AI agent invoked without static tool output.
- Findings produced from AI analysis alone.

**Assertion pseudocode:**
```
category = LinterDebtCategory(config, backend, static_tool=None)
findings = await category.detect(project_root, config)
ASSERT mock_backend.execute.called
ASSERT len(findings) >= 0  # may find issues or not
```

### TS-61-E7: Issue creation failure

**Requirement:** 61-REQ-5.E1
**Type:** integration
**Description:** Verify that issue creation failure does not block other
findings.

**Preconditions:**
- Mock platform that fails on first `create_issue`, succeeds on second.
- 2 finding groups.

**Input:**
- Create issues from 2 groups.

**Expected:**
- First group's failure logged.
- Second group's issue created.

**Assertion pseudocode:**
```
mock_platform.create_issue.side_effect = [httpx.HTTPError("fail"), IssueResult(...)]
await create_issues_from_groups([group1, group2], mock_platform)
ASSERT mock_platform.create_issue.call_count == 2
ASSERT "fail" in caplog.text
```

### TS-61-E8: Fix session failure after retries

**Requirement:** 61-REQ-6.E1
**Type:** integration
**Description:** Verify that fix failure results in an issue comment.

**Preconditions:**
- Fix session configured to fail.

**Input:**
- Process an af:fix issue.

**Expected:**
- Comment posted on issue describing the failure.
- Pipeline continues to next issue.

**Assertion pseudocode:**
```
mock_session.execute.side_effect = RuntimeError("session failed")
await pipeline.process_issue(issue)
comments = mock_platform.add_issue_comment.call_args_list
ASSERT any("failed" in str(c).lower() for c in comments)
```

### TS-61-E9: Empty issue body

**Requirement:** 61-REQ-6.E2
**Type:** unit
**Description:** Verify handling of empty issue body.

**Preconditions:**
- Issue with empty body.

**Input:**
- Attempt to build in-memory spec.

**Expected:**
- Comment posted requesting more detail.
- Issue skipped.

**Assertion pseudocode:**
```
issue = IssueResult(number=1, title="Fix something", html_url="...")
result = await pipeline.process_issue(issue)  # body is empty
comments = mock_platform.add_issue_comment.call_args_list
ASSERT any("detail" in str(c).lower() or "insufficient" in str(c).lower()
           for c in comments)
```

### TS-61-E10: PR creation failure

**Requirement:** 61-REQ-7.E1
**Type:** integration
**Description:** Verify fallback when PR creation fails.

**Preconditions:**
- Fix session succeeds, PR creation fails.

**Input:**
- Process a fixable issue.

**Expected:**
- Comment posted on issue with branch name for manual PR creation.

**Assertion pseudocode:**
```
mock_platform.create_pr.side_effect = httpx.HTTPError("API error")
await pipeline.process_issue(issue)
comments = mock_platform.add_issue_comment.call_args_list
ASSERT any("fix/" in str(c) for c in comments)
```

### TS-61-E11: Unknown platform type

**Requirement:** 61-REQ-8.E1
**Type:** unit
**Description:** Verify abort on unknown platform type.

**Preconditions:**
- Config with `[platform] type = "bitbucket"`.

**Input:**
- Attempt platform instantiation.

**Expected:**
- Raises SystemExit with code 1.
- Error message lists supported types.

**Assertion pseudocode:**
```
config.platform.type = "bitbucket"
with pytest.raises(SystemExit) as exc:
    create_platform(config, project_root)
ASSERT exc.value.code == 1
ASSERT "github" in str(exc.value) or "supported" in str(exc.value).lower()
```

### TS-61-E12: Interval clamped to minimum

**Requirement:** 61-REQ-9.E1
**Type:** unit
**Description:** Verify that intervals < 60s are clamped to 60.

**Preconditions:**
- Config with `issue_check_interval = 10`.

**Input:**
- Load NightShiftConfig.

**Expected:**
- `issue_check_interval` is 60 (clamped).

**Assertion pseudocode:**
```
cfg = NightShiftConfig(issue_check_interval=10)
ASSERT cfg.issue_check_interval == 60
```

## Property Test Cases

### TS-61-P1: Finding format universality

**Property:** Property 1 from design.md
**Validates:** 61-REQ-3.3, 61-REQ-4.1, 61-REQ-4.2
**Type:** property
**Description:** Every Finding has all required fields populated.

**For any:** Finding generated with arbitrary valid strings for each field.
**Invariant:** All required attributes are non-empty strings; severity is one
of the four valid values.

**Assertion pseudocode:**
```
FOR ANY finding IN findings_strategy():
    ASSERT finding.category != ""
    ASSERT finding.title != ""
    ASSERT finding.description != ""
    ASSERT finding.severity in ("critical", "major", "minor", "info")
    ASSERT finding.group_key != ""
    ASSERT len(finding.affected_files) >= 0
```

### TS-61-P2: Schedule interval compliance

**Property:** Property 2 from design.md
**Validates:** 61-REQ-2.1, 61-REQ-2.2, 61-REQ-9.1
**Type:** property
**Description:** Callbacks are invoked at intervals within tolerance.

**For any:** interval in [60, 86400] seconds.
**Invariant:** After simulating N intervals, the callback is invoked N+1
times (including initial) within 10% jitter.

**Assertion pseudocode:**
```
FOR ANY interval IN integers(min=60, max=86400):
    scheduler = Scheduler(issue_interval=interval, hunt_interval=99999)
    count = 0
    scheduler.on_issue_check = lambda: count += 1
    await scheduler.run_for(interval * 3 + 1)
    ASSERT count == 4  # t=0, t=interval, t=2*interval, t=3*interval
```

### TS-61-P3: Issue-finding bijection

**Property:** Property 3 from design.md
**Validates:** 61-REQ-5.1, 61-REQ-5.2
**Type:** property
**Description:** Every finding appears in exactly one group, and the number
of issues equals the number of groups.

**For any:** list of findings with arbitrary group_keys.
**Invariant:** Union of all group.findings equals the input list (as sets by
identity). No finding appears in more than one group.

**Assertion pseudocode:**
```
FOR ANY findings IN lists(findings_strategy(), min_size=1, max_size=50):
    groups = consolidate_findings(findings)
    all_grouped = [f for g in groups for f in g.findings]
    ASSERT len(all_grouped) == len(findings)
    ASSERT set(id(f) for f in all_grouped) == set(id(f) for f in findings)
```

### TS-61-P4: Fix pipeline completeness

**Property:** Property 4 from design.md
**Validates:** 61-REQ-6.2, 61-REQ-7.1, 61-REQ-7.2
**Type:** property
**Description:** Successful fix produces exactly one branch and one PR.

**For any:** issue with valid title and non-empty body.
**Invariant:** On success, `create_pr` called once, branch name starts with
`fix/`, PR body references issue number.

**Assertion pseudocode:**
```
FOR ANY issue IN issue_strategy():
    mock_platform.reset()
    result = await pipeline.process_issue(issue)
    if result.success:
        ASSERT mock_platform.create_pr.call_count == 1
        branch = mock_platform.create_pr.call_args[0][0]
        ASSERT branch.startswith("fix/")
        body = mock_platform.create_pr.call_args[0][2]
        ASSERT f"#{issue.number}" in body
```

### TS-61-P5: Cost monotonicity

**Property:** Property 5 from design.md
**Validates:** 61-REQ-1.E2, 61-REQ-9.3
**Type:** property
**Description:** Cost never decreases during a run.

**For any:** sequence of operations with positive costs.
**Invariant:** `state.total_cost` is monotonically non-decreasing after each
operation.

**Assertion pseudocode:**
```
FOR ANY costs IN lists(floats(min=0.0, max=10.0), min_size=1, max_size=20):
    state = NightShiftState()
    previous = 0.0
    for cost in costs:
        state.total_cost += cost
        ASSERT state.total_cost >= previous
        previous = state.total_cost
```

### TS-61-P6: Graceful shutdown completeness

**Property:** Property 6 from design.md
**Validates:** 61-REQ-1.3, 61-REQ-1.4
**Type:** property
**Description:** Shutdown always completes the current operation.

**For any:** operation in {issue_check, hunt_scan, fix_session}.
**Invariant:** After SIGINT, the active operation's completion callback fires
before the engine exits.

**Assertion pseudocode:**
```
FOR ANY operation IN sampled_from(["issue_check", "hunt_scan", "fix_session"]):
    engine = NightShiftEngine(config, mock_platform)
    completed = False
    original = getattr(engine, f"_run_{operation}")
    async def tracked():
        await original()
        completed = True
    setattr(engine, f"_run_{operation}", tracked)
    task = asyncio.create_task(engine.run())
    send SIGINT
    await task
    ASSERT completed == True
```

### TS-61-P7: Category isolation

**Property:** Property 7 from design.md
**Validates:** 61-REQ-3.E1, 61-REQ-3.4
**Type:** property
**Description:** A failing category does not affect other categories.

**For any:** subset of categories that raise exceptions.
**Invariant:** Non-failing categories still produce their findings.

**Assertion pseudocode:**
```
FOR ANY failing_cats IN subsets(category_names):
    for name in failing_cats:
        mock_categories[name].detect.side_effect = RuntimeError("fail")
    findings = await scanner.run(project_root)
    expected_count = sum(
        mock_categories[n].expected_findings
        for n in category_names if n not in failing_cats
    )
    ASSERT len(findings) == expected_count
```

### TS-61-P8: Platform protocol substitutability

**Property:** Property 8 from design.md
**Validates:** 61-REQ-8.1, 61-REQ-8.2, 61-REQ-8.3
**Type:** property
**Description:** Any PlatformProtocol implementation works with the engine.

**For any:** mock implementation satisfying PlatformProtocol.
**Invariant:** Engine completes issue check and hunt scan without
type errors.

**Assertion pseudocode:**
```
FOR ANY platform IN platform_mocks_strategy():
    ASSERT isinstance(platform, PlatformProtocol)
    engine = NightShiftEngine(config, platform)
    # Should not raise TypeError
    await engine._run_issue_check()
    await engine._run_hunt_scan()
```

## Coverage Matrix

| Requirement    | Test Spec Entry | Type        |
| -------------- | --------------- | ----------- |
| 61-REQ-1.1     | TS-61-1         | integration |
| 61-REQ-1.2     | TS-61-2         | unit        |
| 61-REQ-1.3     | TS-61-3         | integration |
| 61-REQ-1.4     | TS-61-3         | integration |
| 61-REQ-1.E1    | TS-61-E1        | unit        |
| 61-REQ-1.E2    | TS-61-E2        | unit        |
| 61-REQ-2.1     | TS-61-4         | unit        |
| 61-REQ-2.2     | TS-61-5         | unit        |
| 61-REQ-2.3     | TS-61-6         | unit        |
| 61-REQ-2.E1    | TS-61-E3        | integration |
| 61-REQ-2.E2    | TS-61-E4        | unit        |
| 61-REQ-3.1     | TS-61-7         | unit        |
| 61-REQ-3.2     | TS-61-8         | unit        |
| 61-REQ-3.3     | TS-61-9         | unit        |
| 61-REQ-3.4     | TS-61-10        | integration |
| 61-REQ-3.E1    | TS-61-E5        | integration |
| 61-REQ-4.1     | TS-61-11        | unit        |
| 61-REQ-4.2     | TS-61-11        | unit        |
| 61-REQ-4.3     | TS-61-12        | unit        |
| 61-REQ-4.E1    | TS-61-E6        | unit        |
| 61-REQ-5.1     | TS-61-13        | unit        |
| 61-REQ-5.2     | TS-61-14        | integration |
| 61-REQ-5.3     | TS-61-15        | unit        |
| 61-REQ-5.4     | TS-61-2         | unit        |
| 61-REQ-5.E1    | TS-61-E7        | integration |
| 61-REQ-6.1     | TS-61-16        | unit        |
| 61-REQ-6.2     | TS-61-17        | unit        |
| 61-REQ-6.3     | TS-61-18        | integration |
| 61-REQ-6.4     | TS-61-19        | integration |
| 61-REQ-6.E1    | TS-61-E8        | integration |
| 61-REQ-6.E2    | TS-61-E9        | unit        |
| 61-REQ-7.1     | TS-61-20        | integration |
| 61-REQ-7.2     | TS-61-21        | unit        |
| 61-REQ-7.3     | TS-61-22        | integration |
| 61-REQ-7.E1    | TS-61-E10       | integration |
| 61-REQ-8.1     | TS-61-23        | unit        |
| 61-REQ-8.2     | TS-61-24        | unit        |
| 61-REQ-8.3     | TS-61-25        | unit        |
| 61-REQ-8.E1    | TS-61-E11       | unit        |
| 61-REQ-9.1     | TS-61-26        | unit        |
| 61-REQ-9.2     | TS-61-27        | unit        |
| 61-REQ-9.3     | TS-61-28        | integration |
| 61-REQ-9.E1    | TS-61-E12       | unit        |
| Property 1     | TS-61-P1        | property    |
| Property 2     | TS-61-P2        | property    |
| Property 3     | TS-61-P3        | property    |
| Property 4     | TS-61-P4        | property    |
| Property 5     | TS-61-P5        | property    |
| Property 6     | TS-61-P6        | property    |
| Property 7     | TS-61-P7        | property    |
| Property 8     | TS-61-P8        | property    |
