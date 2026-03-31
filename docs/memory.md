# Agent-Fox Memory

## Gotchas

- Property-based testing with Hypothesis should suppress HealthCheck.function_scoped_fixture warnings when using pytest fixtures inside hypothesis tests. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
- When verifying that handlers do not contain business logic, check that they do not include direct operations like 'conn.execute' in their source, and instead delegate to importable backing functions. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- The end-of-run discovery feature with hot_load defaulting to True causes an extra barrier call, which can break existing sync barrier tests that weren't expecting this behavior. _(spec: 60_end_of_run_discovery, confidence: 0.90)_

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

## Decisions

- Verifier instances are explicitly set to 2 while other archetypes use defaults, suggesting that verification intensity can be tuned per archetype for quality control emphasis. _(spec: 59_cli_separation_and_logging, confidence: 0.60)_
- The orchestrator parallel setting ranges from 1-8 with a default of 2; increasing it (e.g., to 4) allows more concurrent sessions but may impact resource usage. _(spec: 61_night_shift, confidence: 0.90)_
- Knowledge store uses DuckDB with configurable embedding models and dimensions; the confidence_threshold (default 0.5) controls which facts are included in session context. _(spec: 61_night_shift, confidence: 0.60)_

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

## Fragile Areas

- When adding new features with default-enabled behavior, verify impact on existing tests involving shared resources like barriers that count invocations. _(spec: 60_end_of_run_discovery, confidence: 0.90)_
