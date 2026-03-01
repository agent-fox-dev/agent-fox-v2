# Agent Fox — Project Memory

*Generated from .agent-fox/memory.jsonl — do not edit manually.*

## Gotchas

- Click 8.3+ removed `CliRunner(mix_stderr=False)` parameter — use `CliRunner()` without arguments. *(source: 01_core_foundation/1)*
- Error hierarchy stubs are complete implementations (just class definitions inheriting from AgentFoxError), so tests pass immediately without additional code — this is expected and correct. *(source: 01_core_foundation/1)*
- Config property tests in tests/property/core/ fail until task group 3 implements load_config(); this is expected behavior and not a regression. *(source: 01_core_foundation/2)*
- ConfigDict(extra='ignore') must be set on every sub-model in a pydantic model hierarchy; setting it only on the top-level model does not automatically apply to nested models. *(source: 01_core_foundation/3)*
- `from __future__ import annotations` causes ruff I001 import sorting errors in files with no type annotations needing it — omit the import when unnecessary. *(source: 01_core_foundation/4)*
- CliRunner inherits the process CWD at invocation time, so `os.chdir()` in `tmp_git_repo` fixture properly affects the init command; test ordering can matter if CWD-changing tests run before others without proper cleanup. *(source: 01_core_foundation/4)*
- Fast-mode filter must compute ordering on a temporary graph excluding optional nodes to prevent edges referencing skipped nodes from confusing the resolver, though the returned TaskGraph retains skipped nodes with SKIPPED status. *(source: 02_planning_engine/4)*
- Cross-spec dependencies from prd.md must be filtered to only include specs in the discovered set before passing to build_graph(), otherwise --spec filtering causes dangling reference errors. *(source: 02_planning_engine/5)*
- Ruff's import sorter (I001) requires third-party imports (e.g., `claude_code_sdk`) to be in a separate group from local imports (e.g., `agent_fox.*`), with blank lines separating the groups. *(source: 03_session_and_workspace/1)*
- Ruff rule UP041 requires using builtin TimeoutError instead of asyncio.TimeoutError — they are the same class in Python 3.11+ but ruff flags the alias as incorrect. *(source: 03_session_and_workspace/3)*
- When rebasing a feature branch that is checked out in a worktree, `git rebase <onto> <branch>` fails with 'already used by worktree' error. Run `git rebase <onto>` without the branch argument from within the worktree directory instead. *(source: 03_session_and_workspace/4)*

## Patterns

- A _clamp() helper function centralizes range enforcement and warning logging for all numeric config fields, allowing individual @field_validator methods to remain terse. *(source: 01_core_foundation/3)*
- Playful/neutral messages are stored in module-level dicts keyed by event name, allowing easy extension without modifying the AppTheme class. *(source: 01_core_foundation/4)*
- Property tests should use tmp_path_factory.mktemp() instead of tmp_path when combined with Hypothesis, since each example needs a fresh directory. *(source: 02_planning_engine/1)*
- Graph test fixtures use a make_graph() helper in conftest.py that wraps Node/Edge lists into a TaskGraph with default metadata. *(source: 02_planning_engine/1)*
- Planning engine modules are organized into agent_fox/spec/ (discovery, parser) for spec-level logic and agent_fox/graph/ (types, builder, resolver, fast_mode, persistence) for graph-level operations. *(source: 02_planning_engine/1)*
- The `discover_specs()` function returns all matching specs including those without `tasks.md` files (with `has_tasks=False`), allowing callers to handle missing task files rather than filtering them out automatically. *(source: 02_planning_engine/2)*
- The task parser uses two regex patterns: `_GROUP_PATTERN` matches top-level groups with `^- \[([ x\-])\] (\* )?(\d+)\. (.+)$` and `_SUBTASK_PATTERN` matches nested subtasks with `^\s+- \[([ x\-])\] (\d+\.\d+) (.+)$`, covering all checkbox states (unchecked, completed, in-progress). *(source: 02_planning_engine/3)*
- The graph builder sorts task groups by number within each spec before creating intra-spec edges, ensuring correct sequential ordering even when groups appear out of order in the input. *(source: 02_planning_engine/3)*
- The resolver uses heapq with (sort_key, node_id) tuples for deterministic tie-breaking in Kahn's algorithm, where sort_key is (spec_name, group_number). *(source: 02_planning_engine/4)*
- The load_plan() function returns None for both missing and corrupted files using a two-stage try/except: first for JSON parsing, then for structure validation. *(source: 02_planning_engine/4)*
- The plan CLI command uses Path.cwd() to locate .specs/ and .agent-fox/plan.json directories, making it sensitive to the current working directory. *(source: 02_planning_engine/5)*
- When patching module-level imports (e.g., `query` from claude-code-sdk), the stub module must import the name with `# noqa: F401` comment so that `patch("module.name")` can locate and patch it. *(source: 03_session_and_workspace/1)*
- Runner tests mock `agent_fox.session.runner.query` by patching the imported name in the runner module and providing async generator mock functions that yield mock message objects. *(source: 03_session_and_workspace/1)*
- Git operations in the workspace module use `asyncio.create_subprocess_exec('git', *args)` with PIPE for stdout/stderr, matching the async architecture required by the session runner. *(source: 03_session_and_workspace/2)*
- Worktree cleanup uses a two-step approach: first attempt `git worktree remove --force`, then fall back to `shutil.rmtree` if the directory still exists. *(source: 03_session_and_workspace/2)*
- The session runner uses a two-level async structure: run_session() catches TimeoutError and generic Exception, while _execute_query() handles actual SDK iteration. This separation allows with_timeout() to wrap only the query execution. *(source: 03_session_and_workspace/3)*
- Tests mock agent_fox.session.runner.query via side_effect with async generator functions for success cases, and side_effect=Exception(...) for error cases. The timeout test patches both query and with_timeout. *(source: 03_session_and_workspace/3)*
- The harvester executes rebase and abort_rebase operations from `workspace.path` (the worktree directory) rather than `repo_root` to avoid worktree branch lock conflicts. *(source: 03_session_and_workspace/4)*
- CircuitBreaker.check_launch() uses 1-indexed attempts where attempt 1 is the initial try and attempts 2 through max_retries+1 are retries. Allowed attempt count equals max_retries + 1. *(source: 04_orchestrator/1)*
- GraphSync edges dict maps node_id to list of dependency node_ids (predecessors); reverse adjacency must be built in __init__ for cascade blocking BFS operations. *(source: 04_orchestrator/2)*
- Persistence layer uses dataclasses.asdict() for serialization and manual field extraction for deserialization when reconstructing SessionRecord objects from dicts. *(source: 04_orchestrator/2)*
- SerialRunner supports both callable runners (via __call__) and runners with an execute() method by checking hasattr(runner, 'execute'). This dual support accommodates mock styles used in tests: MockSerialSessionRunner (callable) and MockSessionRunner (.execute() method). *(source: 04_orchestrator/3)*
- The orchestrator dispatches one ready task per main-loop iteration in serial mode, then re-evaluates ready tasks. This ensures newly-unblocked tasks are discovered immediately after each completion. *(source: 04_orchestrator/3)*
- The orchestrator uses an attempt tracker and error tracker initialized from session history to support correct resume behavior — attempt counts and error messages persist across sessions. *(source: 04_orchestrator/3)*

## Decisions

- Use `StrEnum` (not `str, Enum`) for `ModelTier` because ruff UP042 requires it for Python 3.12+. *(source: 01_core_foundation/1)*
- Specify `claude-code-sdk>=0.0.1` (not `>=0.1`) because PyPI only has versions up to 0.0.25. *(source: 01_core_foundation/1)*
- resolve_model() uses deferred import of ConfigError to avoid circular imports between models.py and errors.py. *(source: 01_core_foundation/2)*
- Cost calculation uses simple arithmetic (tokens / 1_000_000) * price_per_m without rounding, returning raw float for maximum precision in downstream calculations. *(source: 01_core_foundation/2)*
- Numeric clamping uses pydantic @field_validator with mode='after' instead of Field(ge=, le=) constraints because the requirement specifies clamping behavior (silently adjust out-of-range values) rather than rejection via ValidationError. *(source: 01_core_foundation/3)*
- Config loading uses tomllib (stdlib in Python 3.11+) for TOML parsing, with tomllib.TOMLDecodeError caught and converted to ConfigError, and pydantic ValidationError also caught and converted with field location details. *(source: 01_core_foundation/3)*
- Logging configures the `agent_fox` namespace logger (not root) to avoid polluting output from third-party libraries; handler deduplication prevents repeated `setup_logging()` calls from stacking handlers. *(source: 01_core_foundation/4)*
- Persistence functions (save_plan, load_plan) live in a separate agent_fox/graph/persistence.py module rather than in types.py, to keep data models separate from I/O. *(source: 02_planning_engine/1)*
- NodeStatus is defined in agent_fox/graph/types.py using StrEnum; core/types.py is a placeholder that may re-export it later. *(source: 02_planning_engine/1)*
- The `discover_specs()` function imports `PlanError` from `agent_fox.core.errors` for error handling, establishing a dependency on core errors but intentionally avoiding dependencies on graph types. *(source: 02_planning_engine/2)*
- The `parse_cross_deps()` function uses sentinel group numbers (from_group=0, to_group=0) for spec-level dependencies because the prd.md table only contains spec names, not group numbers. The graph builder later resolves 0 to the first or last group number as appropriate. *(source: 02_planning_engine/3)*
- Persistence uses manual dict-based serialization instead of dataclasses.asdict() because NodeStatus (StrEnum) and frozen dataclasses require controlled conversion. *(source: 02_planning_engine/4)*
- Plan persistence reuse (02-REQ-6.3) checks for existing plan.json before rebuilding; the --reanalyze flag explicitly skips this cache check to force recomputation. *(source: 02_planning_engine/5)*
- Allowlist hook tests are separated into a dedicated `test_security.py` file rather than placed in `test_runner.py` to improve clarity and organization. *(source: 03_session_and_workspace/1)*
- The `with_timeout` function uses PEP 695 type parameters (`async def with_timeout[T](...)`) instead of `TypeVar` to satisfy the ruff UP047 rule. *(source: 03_session_and_workspace/1)*
- `delete_branch()` detects 'not found' in stderr to distinguish missing-branch errors (handled as no-op with warning) from other failures (which raise WorkspaceError). *(source: 03_session_and_workspace/2)*
- Data models (SessionRecord, ExecutionState, RunStatus, LaunchDecision) are defined in their respective stub modules rather than shared locations to support proper test imports. *(source: 04_orchestrator/1)*
- StateManager persists ExecutionState using JSON Lines format where each line is a complete snapshot; load() reads the last line, save() appends new lines. *(source: 04_orchestrator/2)*
- In-progress tasks from prior interrupted runs are reset to pending status during state loading, with attempt tracking preserved from session history. This implements exactly-once semantics per requirement 04-REQ-7.E1. *(source: 04_orchestrator/3)*

## Conventions

- All Python files use `from __future__ import annotations` for modern type hint syntax. *(source: 01_core_foundation/1)*
- Error hierarchy uses simple class inheritance with `**context` kwargs pattern for passing contextual data to exceptions (e.g., `AgentFoxError("msg", field="x")`). *(source: 01_core_foundation/1)*
- Package structure follows: `agent_fox/cli/`, `agent_fox/core/`, `agent_fox/infra/`, `agent_fox/ui/` with matching test structure in `tests/unit/`, `tests/property/`, `tests/integration/`. *(source: 01_core_foundation/1)*
- MODEL_REGISTRY keys are full model ID strings (e.g. 'claude-sonnet-4-6'), and TIER_DEFAULTS maps ModelTier enum values to those keys. *(source: 01_core_foundation/2)*
- All pydantic ConfigDict models must set extra='ignore' to handle unknown keys, and this must be applied to every sub-model (not just top-level AgentFoxConfig) to properly ignore unknown fields within known configuration sections. *(source: 01_core_foundation/3)*
- `invoke_without_command=True` is used instead of custom `BannerGroup.invoke()` override to handle no-subcommand banner display while avoiding interference with Click's built-in unknown-subcommand error handling (exit code 2). *(source: 01_core_foundation/4)*
- Git operations in the init command use `subprocess.run()` rather than a git library, keeping dependencies minimal. *(source: 01_core_foundation/4)*
- Theme system validates Rich style strings at theme creation time using `Style.parse()`, falling back to defaults from `_DEFAULT_STYLES` dict on invalid values. *(source: 01_core_foundation/4)*
- Test files follow a naming convention where class names map to test spec IDs (e.g., TestDiscoverSpecsSorted maps to TS-02-1). *(source: 02_planning_engine/1)*
- CrossSpecDep fields use from_spec/from_group (the spec declaring the dependency) and to_spec/to_group (the spec being depended on), matching the prd.md table direction. *(source: 02_planning_engine/1)*
- Spec folder discovery uses a regex pattern `^(\d{2})_(.+)$` that requires exactly two-digit prefixes. Only directories matching this pattern are recognized as valid specs. *(source: 02_planning_engine/2)*
- Edge direction in the dependency graph is opposite to CrossSpecDep field naming: CrossSpecDep(from_spec=declaring, to_spec=depended-on) becomes Edge(source=to_spec:to_group, target=from_spec:from_group). The builder handles this translation. *(source: 02_planning_engine/3)*
- CLI end-to-end tests (TestPlanCLIEndToEnd / TS-02-11) belong to task group 5 and are expected to fail until the plan CLI command is implemented. *(source: 02_planning_engine/4)*
- Integration tests use tmp_git_repo fixture which os.chdir's into the temp repo to test plan command behavior with correct working directory context. *(source: 02_planning_engine/5)*
- Async tests use pytest-asyncio with `asyncio_mode = "auto"` in pyproject.toml, so `@pytest.mark.asyncio` decorator is not required (though included for explicitness in existing tests). *(source: 03_session_and_workspace/1)*
- Workspace test fixtures are located in `tests/unit/workspace/conftest.py`. The `tmp_worktree_repo` fixture provides a temporary git repository with a develop branch, and helper functions (`add_commit_to_branch`, `get_branch_tip`, `list_branches`) are defined as plain functions rather than fixtures. *(source: 03_session_and_workspace/1)*
- Session test fixtures live in `tests/unit/session/conftest.py` and include: `tmp_spec_dir`, `default_config`, `short_timeout_config`, `small_allowlist_config`, and `workspace_info`. *(source: 03_session_and_workspace/1)*
- `run_git()` is the single low-level function that all other git operations delegate to; it centralizes check/raise semantics so callers don't need to. *(source: 03_session_and_workspace/2)*
- `merge_fast_forward()` and `rebase_onto()` raise `IntegrationError` (not `WorkspaceError`) since they belong to the harvesting/integration domain rather than workspace management. *(source: 03_session_and_workspace/2)*
- The allowlist hook returns a dict with {"callback": fn} structure, where the callback is a sync function accepting tool_name and tool_input keyword arguments, returning {"decision": "block", "message": "..."} to block or {} to allow. *(source: 03_session_and_workspace/3)*
- The effective allowlist is computed as: if config.security.bash_allowlist is set (not None), use it as replacement; otherwise use DEFAULT_BASH_ALLOWLIST + config.security.bash_allowlist_extend. *(source: 03_session_and_workspace/3)*
- Engine modules are located under agent_fox/engine/ consisting of six files: orchestrator.py, serial.py, parallel.py, circuit.py, state.py, and sync.py. Corresponding unit and property tests mirror this structure in tests/unit/engine/ and tests/property/engine/. *(source: 04_orchestrator/1)*
- Orchestrator tests use class-based grouping where test class names map to test spec IDs (e.g., TestReadyTasksIdentified → TS-04-2, TestCascadeBlockingLinear → TS-04-6). *(source: 04_orchestrator/1)*
- Stub modules use raise NotImplementedError in all methods to ensure test failures occur at assertion level rather than import level, enabling proper test collection. *(source: 04_orchestrator/1)*
- RunStatus uses StrEnum instead of str, Enum per ruff rule UP042. *(source: 04_orchestrator/1)*
- ruff requires imports sorted in order: stdlib → third-party → first-party → local. Use 'ruff check --fix' to auto-sort. Property test files import hypothesis before agent_fox modules. *(source: 04_orchestrator/1)*
- Use `datetime.UTC` alias instead of `datetime.timezone.utc` to satisfy ruff linter rule UP017. *(source: 04_orchestrator/2)*
- Plan edges use source → target notation where source must complete before target. The Orchestrator converts these to GraphSync edges dict format: {target: [source, ...]} mapping each node to its dependency predecessors. *(source: 04_orchestrator/3)*

## Anti-Patterns

*(No facts in this category.)*

## Fragile Areas

- Property tests using `tmp_path_factory` with Hypothesis: each Hypothesis example creates a new temp directory, so use `tmp_path_factory.mktemp()` instead of the `tmp_path` fixture. *(source: 01_core_foundation/1)*
- Integration tests change working directory via `os.chdir()` — must restore in fixture teardown to avoid side effects on subsequent tests. *(source: 01_core_foundation/1)*
- CrossSpecDep field naming (from_spec = declaring spec, to_spec = depended-on spec) is opposite to edge direction in the graph; the builder must translate so edges go from to_spec:to_group -> from_spec:from_group. *(source: 02_planning_engine/1)*
- Cross-spec dependency resolution between prd.md and discovered specs is fragile; incomplete filtering can cause dangling references that break graph building. *(source: 02_planning_engine/5)*
