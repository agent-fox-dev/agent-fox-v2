# Implementation Plan: Core Foundation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec bootstraps the agent-fox v2 project from an empty repository. Task
groups are ordered to build up from project skeleton to working CLI with init
command.

## Test Commands

- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/property/ -q`
- All tests: `uv run pytest tests/ -q`
- Linter: `uv run ruff check agent_fox/`
- Type check: `uv run mypy agent_fox/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up project tooling
    - Create `pyproject.toml` with dependencies (click, pydantic, rich,
      anthropic, pytest, hypothesis, ruff, mypy)
    - Create `agent_fox/__init__.py` and `agent_fox/__main__.py`
    - Create `tests/conftest.py` with shared fixtures (tmp_git_repo,
      cli_runner)
    - Run `uv sync` to install dependencies

  - [x] 1.2 Write CLI tests
    - `tests/unit/cli/test_app.py`: TS-01-1 (version), TS-01-2 (help)
    - `tests/unit/cli/test_app.py`: TS-01-E1 (unknown subcommand)
    - _Test Spec: TS-01-1, TS-01-2, TS-01-E1_

  - [x] 1.3 Write config tests
    - `tests/unit/core/test_config.py`: TS-01-3 (defaults), TS-01-4
      (overrides), TS-01-5 (invalid type), TS-01-E2 (missing file),
      TS-01-E3 (invalid TOML), TS-01-E7 (unknown keys)
    - _Test Spec: TS-01-3, TS-01-4, TS-01-5, TS-01-E2, TS-01-E3, TS-01-E7_

  - [x] 1.4 Write model registry tests
    - `tests/unit/core/test_models.py`: TS-01-9 (tier resolution),
      TS-01-10 (cost calc), TS-01-E5 (unknown model)
    - _Test Spec: TS-01-9, TS-01-10, TS-01-E5_

  - [x] 1.5 Write error hierarchy tests
    - `tests/unit/core/test_errors.py`: TS-01-11 (hierarchy check)
    - _Test Spec: TS-01-11_

  - [x] 1.6 Write theme tests
    - `tests/unit/ui/test_theme.py`: TS-01-12 (playful toggle),
      TS-01-E6 (invalid color fallback)
    - _Test Spec: TS-01-12, TS-01-E6_

  - [x] 1.7 Write property tests
    - `tests/property/core/test_config_props.py`: TS-01-P1 (defaults),
      TS-01-P2 (clamping)
    - `tests/property/core/test_models_props.py`: TS-01-P3 (cost),
      TS-01-P4 (registry), TS-01-P5 (error hierarchy)
    - _Test Spec: TS-01-P1, TS-01-P2, TS-01-P3, TS-01-P4, TS-01-P5_

  - [x] 1.8 Write init integration tests
    - `tests/integration/test_init.py`: TS-01-6 (creates structure),
      TS-01-7 (idempotent), TS-01-8 (gitignore), TS-01-E4 (no git)
    - _Test Spec: TS-01-6, TS-01-7, TS-01-8, TS-01-E4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement error hierarchy and model registry
  - [x] 2.1 Create error hierarchy
    - `agent_fox/core/errors.py`: AgentFoxError base class and all
      subclasses (ConfigError, InitError, PlanError, SessionError,
      WorkspaceError, IntegrationError, HookError, SessionTimeoutError,
      CostLimitError, SecurityError, KnowledgeStoreError)
    - Each carries a message and optional **context kwargs
    - _Requirements: 01-REQ-4.1, 01-REQ-4.2, 01-REQ-4.3_

  - [x] 2.2 Create model registry
    - `agent_fox/core/models.py`: ModelTier enum, ModelEntry dataclass,
      MODEL_REGISTRY dict, TIER_DEFAULTS dict
    - `resolve_model(name)`: tier name or model ID → ModelEntry
    - `calculate_cost(input_tokens, output_tokens, model)`: USD float
    - _Requirements: 01-REQ-5.1, 01-REQ-5.2, 01-REQ-5.3, 01-REQ-5.4_

  - [x] 2.3 Create domain types stub
    - `agent_fox/core/types.py`: placeholder file for shared domain types
      (NodeStatus enum, etc.) — populated by later specs

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/core/test_errors.py tests/unit/core/test_models.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/core/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/core/`
    - [x] Requirements 01-REQ-4.*, 01-REQ-5.* acceptance criteria met

- [x] 3. Implement configuration system
  - [x] 3.1 Create pydantic config models
    - `agent_fox/core/config.py`: All config section models
      (OrchestratorConfig, ModelConfig, HookConfig, SecurityConfig,
      ThemeConfig, PlatformConfig, MemoryConfig, KnowledgeConfig,
      AgentFoxConfig)
    - All fields with documented defaults and validation constraints
    - _Requirements: 01-REQ-2.3, 01-REQ-2.4_

  - [x] 3.2 Implement config loading
    - `load_config(path)`: TOML → pydantic model with defaults
    - Handle missing file (return defaults), invalid TOML (raise
      ConfigError), invalid types (raise ConfigError with field details)
    - Handle unknown keys (log warning, ignore via `model_config =
      ConfigDict(extra="ignore")`)
    - Implement numeric clamping via pydantic validators
    - _Requirements: 01-REQ-2.1, 01-REQ-2.2, 01-REQ-2.5, 01-REQ-2.6_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/core/test_config.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/core/test_config_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/core/config.py`
    - [x] Requirements 01-REQ-2.* acceptance criteria met

- [x] 4. Implement CLI, theme, logging, and init command
  - [x] 4.1 Create theme system
    - `agent_fox/ui/__init__.py`, `agent_fox/ui/theme.py`: AppTheme
      class with Rich Console, color roles, playful/neutral message
      variants
    - `agent_fox/ui/banner.py`: CLI banner rendering with version
    - `create_theme(config)`: factory function
    - _Requirements: 01-REQ-7.1, 01-REQ-7.2, 01-REQ-7.3, 01-REQ-7.4_

  - [x] 4.2 Create logging setup
    - `agent_fox/infra/__init__.py`, `agent_fox/infra/logging.py`:
      `setup_logging(verbose, quiet)` configuring Python logging with
      format `[LEVEL] component: message`
    - Named loggers per module
    - _Requirements: 01-REQ-6.1, 01-REQ-6.2, 01-REQ-6.3_

  - [x] 4.3 Create CLI entry point
    - `agent_fox/cli/__init__.py`, `agent_fox/cli/app.py`: BannerGroup
      class, `main` Click group with --version, --verbose, --quiet
    - Global exception handler for AgentFoxError and unexpected exceptions
    - Load config and attach to Click context
    - _Requirements: 01-REQ-1.1, 01-REQ-1.2, 01-REQ-1.3, 01-REQ-1.4_

  - [x] 4.4 Implement init command
    - `agent_fox/cli/init.py`: `init` Click command
    - Create `.agent-fox/` directory structure
    - Generate default `config.toml` (render from template or string)
    - Create/verify `develop` branch
    - Update `.gitignore`
    - Idempotency: skip if already initialized
    - Git repo check: exit with error if not in a git repo
    - _Requirements: 01-REQ-3.1, 01-REQ-3.2, 01-REQ-3.3, 01-REQ-3.4, 01-REQ-3.5_

  - [x] 4.5 Wire up `__main__.py` and pyproject.toml console script
    - `agent_fox/__main__.py`: `from agent_fox.cli.app import main; main()`
    - Verify `pyproject.toml` has `[project.scripts] agent-fox = "..."`

  - [x] 4.V Verify task group 4
    - [x] All spec tests pass: `uv run pytest tests/ -q`
    - [x] All property tests pass: `uv run pytest tests/property/ -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`
    - [x] Type check passes: `uv run mypy agent_fox/`
    - [x] Requirements 01-REQ-1.*, 01-REQ-3.*, 01-REQ-6.*, 01-REQ-7.* met
    - [x] CLI is invocable: `uv run agent-fox --version`

- [ ] 5. Checkpoint — Core Foundation Complete
  - Ensure all tests pass: `uv run pytest tests/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/ tests/`
  - Ensure type check clean: `uv run mypy agent_fox/`
  - Verify `uv run agent-fox init` works end-to-end in a fresh repo
  - Create or update `README.md` with project description, installation
    instructions, and usage for `agent-fox init`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 01-REQ-1.1 | TS-01-1, TS-01-2 | 4.3 | tests/unit/cli/test_app.py |
| 01-REQ-1.2 | TS-01-2 | 4.3 | tests/unit/cli/test_app.py |
| 01-REQ-1.3 | TS-01-2 | 4.3 | tests/unit/cli/test_app.py |
| 01-REQ-1.4 | TS-01-1 | 4.5 | tests/unit/cli/test_app.py |
| 01-REQ-1.E1 | TS-01-E1 | 4.3 | tests/unit/cli/test_app.py |
| 01-REQ-2.1 | TS-01-3, TS-01-4 | 3.1, 3.2 | tests/unit/core/test_config.py |
| 01-REQ-2.2 | TS-01-5 | 3.2 | tests/unit/core/test_config.py |
| 01-REQ-2.3 | TS-01-3 | 3.1 | tests/unit/core/test_config.py |
| 01-REQ-2.4 | TS-01-3 | 3.1 | tests/unit/core/test_config.py |
| 01-REQ-2.5 | TS-01-P1 | 3.2 | tests/property/core/test_config_props.py |
| 01-REQ-2.6 | TS-01-E7 | 3.2 | tests/unit/core/test_config.py |
| 01-REQ-2.E1 | TS-01-E2 | 3.2 | tests/unit/core/test_config.py |
| 01-REQ-2.E2 | TS-01-E3 | 3.2 | tests/unit/core/test_config.py |
| 01-REQ-2.E3 | TS-01-P2 | 3.2 | tests/property/core/test_config_props.py |
| 01-REQ-3.1 | TS-01-6 | 4.4 | tests/integration/test_init.py |
| 01-REQ-3.2 | TS-01-6 | 4.4 | tests/integration/test_init.py |
| 01-REQ-3.3 | TS-01-7 | 4.4 | tests/integration/test_init.py |
| 01-REQ-3.4 | TS-01-8 | 4.4 | tests/integration/test_init.py |
| 01-REQ-3.5 | TS-01-E4 | 4.4 | tests/integration/test_init.py |
| 01-REQ-4.1 | TS-01-11 | 2.1 | tests/unit/core/test_errors.py |
| 01-REQ-4.2 | TS-01-11 | 2.1 | tests/unit/core/test_errors.py |
| 01-REQ-5.1 | TS-01-9 | 2.2 | tests/unit/core/test_models.py |
| 01-REQ-5.3 | TS-01-9 | 2.2 | tests/unit/core/test_models.py |
| 01-REQ-5.4 | TS-01-10 | 2.2 | tests/unit/core/test_models.py |
| 01-REQ-5.E1 | TS-01-E5 | 2.2 | tests/unit/core/test_models.py |
| 01-REQ-6.1 | — | 4.2 | tests/unit/infra/test_logging.py |
| 01-REQ-6.2 | — | 4.2 | tests/unit/infra/test_logging.py |
| 01-REQ-7.1 | TS-01-12 | 4.1 | tests/unit/ui/test_theme.py |
| 01-REQ-7.3 | TS-01-12 | 4.1 | tests/unit/ui/test_theme.py |
| 01-REQ-7.4 | TS-01-12 | 4.1 | tests/unit/ui/test_theme.py |
| 01-REQ-7.E1 | TS-01-E6 | 4.1 | tests/unit/ui/test_theme.py |
| Property 1 | TS-01-P1 | 3.1, 3.2 | tests/property/core/test_config_props.py |
| Property 5 | TS-01-P4 | 2.2 | tests/property/core/test_models_props.py |
| Property 6 | TS-01-P3 | 2.2 | tests/property/core/test_models_props.py |
| Property 7 | TS-01-P5 | 2.1 | tests/property/core/test_models_props.py |
| Property 8 | TS-01-P2 | 3.2 | tests/property/core/test_config_props.py |

## Notes

- This is the bootstrap spec — task group 1 must also create `pyproject.toml`
  and the basic package structure so that tests can import `agent_fox`.
- The `config.toml` template should match the existing `.agent-fox/config.toml`
  format with all sections commented out except essentials.
- Use `click.testing.CliRunner` for CLI integration tests.
- Use `tmp_path` and `monkeypatch` fixtures for filesystem-dependent tests.
- For init integration tests, create a temporary git repo with `git init`.
