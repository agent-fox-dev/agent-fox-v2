# PRD: Core Foundation

**Source:** `.specs/prd.md` — Sections 1, 5 (Project Initialization, Security
partial), 6 (Configuration), 9 (Constraints).

## Overview

Establish the project skeleton for agent-fox v2: the CLI entry point, the
configuration system, the `init` command, the error hierarchy, the AI model
registry, logging infrastructure, and the terminal theme system. This is the
foundation every other spec builds on.

## Problem Statement

agent-fox v2 is a ground-up rewrite. Before any feature can be built, the
project needs a working CLI, a configuration system, a way to initialize
projects, structured error handling, and a model registry for AI provider
integration.

## Goals

- Provide a Click-based CLI with subcommand registration, versioning, and help
- Load and validate TOML configuration with sensible defaults
- Implement the `agent-fox init` command (REQ-001, REQ-002, REQ-003)
- Define a clean exception hierarchy for all error categories
- Provide an AI model registry with tiered pricing
- Set up structured logging
- Provide a Rich-based terminal theme with configurable colors

## Non-Goals

- Implementing any feature commands (plan, code, fix, etc.) — those are in
  later specs
- DuckDB setup — that's spec 11
- Actual coding session execution — that's spec 03

## Key Decisions

- **Click over Typer** — battle-tested, composable subcommands, custom group
  classes for themed banners
- **Pydantic v2 for config validation** — type-safe, excellent error messages,
  built-in TOML support via model validators
- **Plain dataclasses for domain types** — lightweight, no extra dependency,
  serialize/deserialize with dacite or manual
- **Rich for terminal output** — tables, progress bars, styled text, markdown
  rendering
- **uv as package manager** — fast, modern Python tooling
- **Hatchling as build backend** — simple, modern, PEP 517 compliant
- **ruff for linting** — fast, replaces flake8 + isort + black
- **mypy for type checking** — gradual typing, compatible with dataclasses
- **pytest + hypothesis for testing** — property-based testing for invariants
