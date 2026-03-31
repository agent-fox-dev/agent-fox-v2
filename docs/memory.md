# Agent-Fox Memory

## Gotchas

- Property-based testing with Hypothesis should suppress HealthCheck.function_scoped_fixture warnings when using pytest fixtures inside hypothesis tests. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When verifying that handlers do not contain business logic, check that they do not include direct operations like 'conn.execute' in their source, and instead delegate to importable backing functions. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- The end-of-run discovery feature with hot_load defaulting to True causes an extra barrier call, which can break existing sync barrier tests that weren't expecting this behavior. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- A 10% cost-limit threshold in engine.py was too strict and caused integration test failures; increasing it to 50% correctly prevents over-budget dispatching when more than half the budget is consumed. _(spec: 61_night_shift, confidence: 0.90)_
- asyncio.get_event_loop().run_until_complete() is deprecated; use asyncio.run() instead for running async code in tests. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When a fallback model configuration matches the primary session model ID, it must be set to None before passing to the Claude CLI, as the CLI rejects fallback models that are identical to the main model. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Claude CLI expects hyphenated flag names (--max-budget-usd, --fallback-model) rather than underscored names (--max_budget_usd, --fallback_model) when passed via extra_args. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Task checkbox reset logic using regex anchored to column 0 will skip indented sub-task checkboxes; use section-based matching instead to reset checkboxes at any nesting depth. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When extracting JSON from LLM output text, bracket-depth scanning alone fails for JSON strings containing bracket characters; use markdown fence detection and JSONDecoder.raw_decode() as fallback. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Hypothesis tests using function-scoped tmp_path fixtures cannot be reused across multiple Hypothesis examples without triggering FileExistsError; use request.getfixturevalue() or module-scoped paths. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- The Claude CLI expects hyphenated flag names (--max-budget-usd, --fallback-model) not underscores (--max_budget_usd, --fallback_model) when passed as extra_args to the SDK. _(spec: 61_night_shift, confidence: 0.90)_
- The Claude CLI rejects --fallback-model when it equals the session's primary model; set resolved_fallback to None when they match to avoid 'Fallback model cannot be the same as the main model' errors. _(spec: 61_night_shift, confidence: 0.90)_
- Checkbox reset logic using column-0 anchored regex skips indented sub-task checkboxes; use section-based matching instead to reset checkboxes at any nesting depth within each task group. _(spec: 61_night_shift, confidence: 0.90)_
- Use JSON.JSONDecoder.raw_decode() instead of naive bracket-depth tracking for extracting JSON arrays from LLM output, as the latter fails for JSON strings containing [ or ] characters. _(spec: 61_night_shift, confidence: 0.90)_

## Patterns

- The coding model tier is set to STANDARD while coordinator is set to ADVANCED, indicating a pattern of using different model tiers for different task types to balance cost and capability. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- Model tiers can be configured per task type (coding, coordination, memory extraction) with options like STANDARD, ADVANCED, and SIMPLE to balance cost and capability. _(spec: 61_night_shift, confidence: 0.90)_
- Multiple archetype instances (e.g., verifier=2) can be configured to run in parallel for quality assurance, improving review coverage at the cost of additional processing. _(spec: 61_night_shift, confidence: 0.60)_
- agent-fox maintains state across runs using .agent-fox/memory.jsonl and .agent-fox/state.jsonl files for persistent knowledge and execution state. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Model tier selection (SIMPLE, STANDARD, ADVANCED) can be configured per task type (coding, coordinator, memory_extraction) to balance cost and capability. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Knowledge store uses embedding-based retrieval with configurable top_k results, confidence thresholds, and fact ranking that can be pre-computed at plan time. _(spec: 60_end_of_run_discovery, confidence: 0.60)_
- End-of-run discovery in orchestrators should only trigger on COMPLETED status, not on other terminal states (STALLED, COST_LIMIT, SESSION_LIMIT, BLOCK_LIMIT, INTERRUPTED). _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Hot-load discovery can be gated by a configuration flag; when disabled, the entire discovery process should be skipped without invoking the barrier sequence. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- End-of-run discovery should reuse the same barrier sequence function and keyword arguments as mid-run barriers to ensure consistency, including hot_load_fn, emit_audit, and other parameters. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Exceptions raised during barrier sequences in discovery should be caught and handled gracefully, returning a boolean status rather than propagating the exception. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When end-of-run discovery produces ready tasks (non-empty task set), the main orchestrator loop should continue execution; when no tasks are discovered, execution terminates. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When testing orchestrator methods that depend on internal state (like _graph_sync, _hot_load_new_specs), those attributes must be set up or mocked before calling the method under test. _(spec: 60_end_of_run_discovery, confidence: 0.60)_
- Property-based testing can be used to verify invariants alongside traditional unit tests in a single test suite. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- Organizing tests into multiple files by feature area (command renames, module separation, progress display, invariants) improves test maintainability and clarity. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- Use Click's CliRunner for testing CLI commands; invoke with CliRunner().invoke(main, [args]) and check result.exit_code and result.output. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Separate CLI handler logic from business logic by creating thin CLI handlers that delegate to importable backing functions, passing options as explicit keyword arguments. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When testing async functions with pytest-asyncio, mark the test with @pytest.mark.asyncio() and use async def test_...() syntax. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- For testing Rich console output, create a StringIO buffer and inject it into Console(file=buf, ...) to capture formatted output without side effects. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Property-based tests with Hypothesis should use @given() for input generation and @settings(max_examples=N) to control test repetition; useful for invariant validation (e.g., truncation never exceeds max_len). _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Use inspect.signature(func).parameters to verify function signatures in tests, and inspect.getsource(module) to verify implementation patterns like function calls or absence of direct operations. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Mock external dependencies (database connections, file I/O, subprocesses) using unittest.mock.MagicMock and patch to avoid side effects and create deterministic test behavior. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Structure result objects (ExportResult, LintResult, ExecutionState) with clear fields (count, findings, exit_code, status) to make CLI handlers and backing functions communicate structured data instead of relying on side effects. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Test CLI command renames by verifying that old commands (dump, lint-spec) exit with non-zero codes while new commands (export, lint-specs) exit successfully with correct behavior. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When testing optional archetype labels in output, verify that presence matches the event field: if archetype is None, bracket labels should be absent; if set, they should appear. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- For truncation functions, use property tests to verify the invariant that output length never exceeds max_len across a range of inputs, and unit tests to verify specific behaviors like ellipsis placement and filename preservation. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Keyboard interrupts in async orchestrators should be caught and converted to a structured ExecutionState with status='interrupted' rather than propagated as exceptions. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- End-of-run discovery requires a sync barrier before terminating with COMPLETED status to ensure all pending operations finish before final status is set. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When implementing end-of-run discovery, the main loop's COMPLETED branch must be modified to continue execution rather than terminate immediately when new specs are discovered. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Maintaining full traceability by mapping every requirement to at least one passing test provides confidence in specification coverage. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When constructing EngineConfig objects in tests, the hot_load parameter should be explicitly set to False to avoid unintended behavior from default values or side effects. _(spec: 60_end_of_run_discovery, confidence: 0.60)_
- Test files should be organized across unit, integration, and property test directories to provide comprehensive coverage of different testing concerns. _(spec: 61_night_shift, confidence: 0.90)_
- Tests should be created and validated to fail before implementation exists, ensuring they properly specify expected behavior. _(spec: 61_night_shift, confidence: 0.90)_
- When renaming CLI commands, ensure backing modules are created with appropriate dataclasses (e.g., ExportResult, LintResult) to encapsulate command outputs and maintain separation of concerns. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Test files should be organized into three separate directories: unit/, integration/, and property/ tests, each with their own __init__.py files. _(spec: 61_night_shift, confidence: 0.90)_
- Use @pytest.mark.asyncio decorator to mark async test methods, and create tasks with asyncio.create_task() for concurrent test operations. _(spec: 61_night_shift, confidence: 0.90)_
- Mock async methods using AsyncMock from unittest.mock, and verify call counts with .call_count attribute on mocked async functions. _(spec: 61_night_shift, confidence: 0.90)_
- Use hypothesis @given decorator with strategies (st.integers, st.text, st.sampled_from) for property-based testing, and apply @settings(max_examples=N) to control iteration count. _(spec: 61_night_shift, confidence: 0.90)_
- Dataclasses should be marked as frozen to ensure immutability and prevent accidental mutations in tests. _(spec: 61_night_shift, confidence: 0.90)_
- Use caplog fixture with caplog.at_level(logging.LEVEL) context manager to capture and verify log messages in tests. _(spec: 61_night_shift, confidence: 0.90)_
- When testing graceful shutdown, use asyncio.Event() to coordinate timing between the main task and shutdown signal, ensuring operations complete before exit. _(spec: 61_night_shift, confidence: 0.60)_
- Finding objects require 8 fields: category, title, description, severity (one of: critical, major, minor, info), affected_files, suggested_fix, evidence, and group_key. _(spec: 61_night_shift, confidence: 0.90)_
- Group findings by group_key (root cause) into FindingGroup objects before creating platform issues, with one issue per group. _(spec: 61_night_shift, confidence: 0.90)_
- Engine state should track is_shutting_down flag, total_cost, and issues_fixed; use request_shutdown() method to initiate graceful shutdown. _(spec: 61_night_shift, confidence: 0.90)_
- Test isolation requires mocking platform API calls (list_issues_by_label, create_issue, add_issue_comment, create_pr) with AsyncMock to avoid real network calls. _(spec: 61_night_shift, confidence: 0.90)_
- Fix pipeline should invoke three archetypes in sequence (skeptic, coder, verifier) via _run_session() method to process a single issue. _(spec: 61_night_shift, confidence: 0.90)_
- When PR creation fails, include branch name (prefixed with 'fix/') in fallback comment on the issue to enable manual PR creation. _(spec: 61_night_shift, confidence: 0.60)_
- Parallel category execution timing tests should expect concurrent categories to complete in ~0.1s (not 0.3s for 3 sequential 0.1s operations). _(spec: 61_night_shift, confidence: 0.60)_
- Category failures should not block other categories; use try-except in parallel execution to isolate failures and log warnings. _(spec: 61_night_shift, confidence: 0.90)_
- Cost tracking enforces max_cost limit; engine stops dispatching new fixes when total_cost would exceed max_cost threshold. _(spec: 61_night_shift, confidence: 0.90)_
- Task dependencies can overlap across task groups—verify that required functionality wasn't already implemented in previous task groups before starting work. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Running the full test suite early can reveal that task group objectives are already complete, saving time and preventing duplicate implementation effort. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When extracting backing modules for CLI handlers, delegate thin handler logic to a dedicated module (e.g., agent_fox/spec/lint.py) rather than embedding business logic in the CLI layer. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Use dataclasses (e.g., LintResult) to structure return values from backing module functions, enabling clear contracts between CLI handlers and business logic. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Use @runtime_checkable decorator on Protocol classes to enable isinstance() checks at runtime, enabling flexible platform abstraction patterns. _(spec: 61_night_shift, confidence: 0.90)_
- Implement consolidation logic in dataclasses (e.g., FindingGroup) to handle aggregation of related domain objects, improving data structure expressiveness. _(spec: 61_night_shift, confidence: 0.60)_
- Use interval clamping in configuration classes (e.g., NightShiftConfig) to enforce valid bounds on numeric parameters during initialization. _(spec: 61_night_shift, confidence: 0.60)_
- Create platform factory functions to abstract platform instantiation and decouple consumer code from concrete platform implementations. _(spec: 61_night_shift, confidence: 0.60)_
- PlatformProtocol should be marked as @runtime_checkable to allow isinstance() checks at runtime for protocol compliance. _(spec: 61_night_shift, confidence: 0.90)_
- NightShiftConfig requires interval clamping logic to ensure configuration values stay within valid bounds. _(spec: 61_night_shift, confidence: 0.90)_
- Branch name sanitisation should be implemented in InMemorySpec to handle invalid characters or formatting in branch names. _(spec: 61_night_shift, confidence: 0.60)_
- Finding and FindingGroup types should support consolidation logic for aggregating or deduplicating findings. _(spec: 61_night_shift, confidence: 0.60)_
- Implement a two-phase detection pattern in base category classes to separate initialization from actual detection logic. _(spec: 61_night_shift, confidence: 0.60)_
- Use error isolation in parallel scanners (HuntScanner) to prevent one category's failure from blocking others. _(spec: 61_night_shift, confidence: 0.60)_
- Prevent hunt scan overlaps at the engine level when scheduling multiple category scans. _(spec: 61_night_shift, confidence: 0.60)_
- Use a registry pattern (HuntCategoryRegistry) to manage and organize multiple protocol implementations dynamically. _(spec: 61_night_shift, confidence: 0.60)_
- When changing default parameter values (e.g., abbreviate_arg max_len from 30 to 60), explicitly update dependent tests to use the old default value rather than relying on implicit defaults, ensuring test behavior remains unchanged. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Status rendering logic (_format_task_line) needs to be updated whenever new task states are added (retry, disagreed, escalated) to ensure complete branch coverage. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- The FixPipeline class requires a real _run_session() implementation that uses run_session() and build_system_prompt() helper methods to execute fix operations. _(spec: 61_night_shift, confidence: 0.90)_
- Issue content propagation requires adding a body field to IssueResult and ensuring list_issues_by_label() populates this field when retrieving issues. _(spec: 61_night_shift, confidence: 0.90)_
- NightShiftEngine._process_fix() should be wired to use FixPipeline for handling fix operations in the pipeline architecture. _(spec: 61_night_shift, confidence: 0.90)_
- A _create_fix_branch() helper method is needed as part of the FixPipeline implementation to support branching operations. _(spec: 61_night_shift, confidence: 0.60)_
- The .agent-fox/memory.jsonl file is being reset/cleared as part of task group management, suggesting it serves as a session-scoped memory store that should be regenerated for each task group. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- Property-based tests should suppress Hypothesis health check warnings when using fixtures that create temporary files, as Hypothesis may incorrectly flag slow example generation. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- Running comprehensive test suites (unit, integration, property tests) together can expose state management issues not visible in isolated runs. _(spec: 61_night_shift, confidence: 0.60)_
- Audit event types should be added to the AuditEventType enum before wiring them into engine implementations that emit those events. _(spec: 61_night_shift, confidence: 0.90)_
- CLI commands that handle graceful shutdown should implement SIGINT handling, typically via signal handlers or context managers. _(spec: 61_night_shift, confidence: 0.90)_
- When adding new event types to an enum, audit completeness tests should use subset checks rather than equality checks to avoid brittleness. _(spec: 61_night_shift, confidence: 0.90)_
- Comprehensive test coverage (63 tests passing) should be verified before considering a feature complete, and regression testing should confirm no existing functionality is broken. _(spec: 61_night_shift, confidence: 0.90)_
- LLM JSON responses should be validated with field-level constraints (content: 5000 chars, keywords: 100 chars/20 max, refs: 500 chars, evidence: 10000 chars) and overall size gating (500KB) to prevent memory exhaustion and prompt injection. _(spec: 61_night_shift, confidence: 0.90)_
- Sanitize untrusted content in LLM prompts using boundary markers (nonce-tagged XML tags), control character stripping, and content truncation to prevent prompt injection attacks. _(spec: 61_night_shift, confidence: 0.90)_
- Validate table names against an allowlist before SQL interpolation in DuckDB queries to prevent SQL injection even if callers are modified to pass dynamic values. _(spec: 61_night_shift, confidence: 0.90)_
- Guard each cleanup step independently in finally blocks with separate try/except so that a failure in one step (e.g., DuckDB lock contention) does not prevent subsequent cleanup steps from executing. _(spec: 61_night_shift, confidence: 0.90)_
- Add __repr__ overrides to classes storing sensitive data (e.g., GitHubPlatform with PAT) to prevent token exposure in tracebacks, debug logs, or crash dumps. _(spec: 61_night_shift, confidence: 0.90)_
- Prevent git argument injection by validating ref names (reject leading '-' and unsafe characters) and add '--' end-of-options separator to branch/merge commands. _(spec: 61_night_shift, confidence: 0.90)_
- Restrict config file and directory permissions to owner-only (0o600 for files, 0o700 for dirs) using custom _secure_write_text() and _secure_mkdir() helpers instead of relying on system umask. _(spec: 61_night_shift, confidence: 0.90)_
- Escape markdown special characters in all database-sourced fields before rendering to prevent unexpected formatting when CLI output is piped to a markdown renderer. _(spec: 61_night_shift, confidence: 0.90)_
- Log full diagnostic details at debug level only; surface only operation name and status/exit code in user-facing exception messages to prevent path and API detail leakage. _(spec: 61_night_shift, confidence: 0.90)_

## Decisions

- Verifier instances are explicitly set to 2 while other archetypes use defaults, suggesting that verification intensity can be tuned per archetype for quality control emphasis. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- The orchestrator parallel setting ranges from 1-8 with a default of 2; increasing it (e.g., to 4) allows more concurrent sessions but may impact resource usage. _(spec: 61_night_shift, confidence: 0.90)_
- Knowledge store uses DuckDB with configurable embedding models and dimensions; the confidence_threshold (default 0.5) controls which facts are included in session context. _(spec: 61_night_shift, confidence: 0.60)_
- Config objects should have sensible defaults (e.g., issue_check_interval=900, hunt_scan_interval=14400) and clamp interval values to a minimum of 60 seconds. _(spec: 61_night_shift, confidence: 0.90)_
- Support initial-run-on-startup configuration in schedulers to control whether callbacks execute immediately upon initialization. _(spec: 61_night_shift, confidence: 0.60)_
- Multi-provider LLM abstraction carries real maintenance costs (protocol differences, adapter complexity, doubled testing surface) but speculative benefits; commit to Claude exclusively unless concrete multi-provider requirements emerge. _(spec: 61_night_shift, confidence: 0.90)_

## Conventions

- Agent-fox uses a TOML configuration file at .agent-fox/config.toml for orchestrator, archetype, model, and platform settings. Key parameters include parallel session count, sync intervals, model tiers (STANDARD, ADVANCED), and archetype instance counts. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Agent-fox maintains persistent state and memory in .agent-fox/ directory using JSONL format (state.jsonl, memory.jsonl) and a knowledge store (knowledge.duckdb by default) for embedding-based fact retrieval. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- agent-fox configuration uses TOML format with schema-based section headers that should not be removed, and many settings can be customized by uncommenting and editing values. _(spec: 61_night_shift, confidence: 0.90)_
- agent-fox uses a TOML configuration file at .agent-fox/config.toml with schema-generated section headers that should not be removed. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- The orchestrator parallel setting (1-8, default: 2) controls maximum concurrent sessions; sync_interval controls task group synchronization frequency. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Use `@pytest.mark.asyncio` decorator on async test methods that use `await`, even when testing mocked async functions. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When creating test files for unimplemented features, tests are expected to fail initially. This is a valid part of test-driven development where tests define the specification before implementation. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Test spec files should include docstrings with Test Spec IDs (e.g., TS-59-1) and Requirements references (e.g., 59-REQ-1.1) to link tests to specification. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Task group completion requires verification that all tests pass, traceability is confirmed between requirements and tests, and the working tree is clean before marking as done. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- Linting validation should be performed on all test files as part of the test creation process. _(spec: 61_night_shift, confidence: 0.90)_
- CLI command renames require updates across multiple locations: command registrations in app.py, all related test files, and documentation to maintain consistency and prevent regressions. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Test specs should map to requirements using docstring format: 'Test Spec: TS-XX-Y' and 'Requirements: 61-REQ-X.Y' for traceability. _(spec: 61_night_shift, confidence: 0.90)_
- Use utility functions like sanitise_branch_name for data normalization to ensure consistency across platform integrations. _(spec: 61_night_shift, confidence: 0.60)_
- Running 'make check' across a large test suite (2800+ tests) requires attention to code formatting violations caught by tools like ruff. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- New CLI commands must be registered in the main app.py file to be accessible to the CLI framework. _(spec: 61_night_shift, confidence: 0.90)_
- Documentation for CLI commands should include coverage of all major flags (like --auto), scheduling behavior, cost control mechanisms, graceful shutdown procedures, and exit codes. _(spec: 61_night_shift, confidence: 0.90)_
- Configuration documentation should explicitly document all toggles/options (e.g., seven category toggles) and any constraints on their values (e.g., interval clamping). _(spec: 61_night_shift, confidence: 0.90)_
- README should include a quick-start section with practical usage examples for new features to aid discoverability. _(spec: 61_night_shift, confidence: 0.60)_

## Anti-Patterns

- Custom file tools with per-line hash verification add schema overhead (800-1000 tokens per session) but are not adopted by the model; prefer built-in provider tools (Read, Edit, Grep) over custom MCP tools. _(spec: 61_night_shift, confidence: 0.90)_

## Fragile Areas

- When adding new features with default-enabled behavior, verify impact on existing tests involving shared resources like barriers that count invocations. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When setting cost-limit thresholds for budget control, account for the margin needed before stopping dispatch operations to avoid exceeding allocated resources. _(spec: 61_night_shift, confidence: 0.90)_
- TaskEvent schema extensions should be coordinated across multiple modules (result_handler.py, engine.py) to ensure all event producers wire the new fields consistently. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- When using caplog in pytest, ensure the logger name matches the actual logger being used in the code being tested. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- The audit event completeness checks (hardcoded sets) must be updated whenever new AuditEventType variants are added, otherwise tests will fail despite the new events being properly implemented. _(spec: 59_cli_separation_and_logging, confidence: 0.90)_
- Asyncio event loop state can cause cross-suite test failures; ensure proper event loop cleanup and isolation between test suites. _(spec: 61_night_shift, confidence: 0.90)_
- Caplog logger scoping issues can lead to test failures across suites; verify logger fixture scope and handler cleanup between tests. _(spec: 61_night_shift, confidence: 0.90)_
