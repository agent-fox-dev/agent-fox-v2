# Agent-Fox Memory

## Gotchas

- Critical path analysis must handle tied critical paths in disconnected graphs, where multiple paths may have equal length. _(spec: 20_plan_analysis, confidence: high)_

## Patterns

- Test files for events, progress display, property tests, and session runner activity callbacks can persist across coding sessions and remain valid for reuse without modification. _(spec: 18_live_progress, confidence: high)_
- Large test suites (1000+ tests) can pass completely after fixing isolated import ordering issues, indicating good test isolation and independence. _(spec: 18_live_progress, confidence: medium)_
- Task group 2 for spec 18_live_progress (event types and abbreviation) was completed in a prior session with all required implementations (ActivityEvent, TaskEvent, abbreviate_arg, format_duration) already in place. _(spec: 18_live_progress, confidence: high)_
- Task group completion should be verified against actual implementation state rather than assumed incomplete; the ProgressDisplay class was already fully implemented from a prior session with all subtasks satisfied. _(spec: 18_live_progress, confidence: high)_
- Task group completion can be verified by confirming all subtasks are implemented and passing the full test suite (1029 tests) with clean linting. _(spec: 18_live_progress, confidence: high)_
- Progress tracking implementation spans multiple components: task_callback on Orchestrator, TaskEvent emission from session result handlers, and ProgressDisplay integration in command execution. _(spec: 18_live_progress, confidence: high)_
- When implementing path abbreviation features, write both unit tests (covering specific cases) and property tests (validating general behavior patterns) to ensure comprehensive coverage of the new functionality. _(spec: 18_live_progress, confidence: high)_
- Trailing path component abbreviation requires validation against existing basename-only implementations to ensure backward compatibility and correct behavior transitions. _(spec: 18_live_progress, confidence: medium)_
- Path abbreviation algorithms should prefer trailing component preservation over simple basename extraction, keeping multiple path components when space permits and using an ellipsis prefix (…/) to indicate truncation. _(spec: 18_live_progress, confidence: high)_
- Path abbreviation with space constraints requires a fallback strategy: when trailing components don't fit within max_len even with ellipsis prefix, fall back to basename-only output. _(spec: 18_live_progress, confidence: high)_
- A comprehensive checkpoint should verify multiple validation criteria: test suite passage (1034 tests), linter compliance, and business logic properties (abbreviation idempotence). _(spec: 18_live_progress, confidence: high)_
- Idempotence is a critical property to verify for abbreviation/truncation operations to ensure repeated applications produce stable results. _(spec: 18_live_progress, confidence: high)_
- Multi-phase task completion (9 sequential groups) benefits from checkpoint verification that confirms all previous phases remain valid. _(spec: 18_live_progress, confidence: medium)_
- Git branch management utilities should include separate functions for checking local vs. remote branch existence to handle different operational contexts. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Default branch detection should be a dedicated function rather than hardcoded, as it varies by repository configuration. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Async branch management functions (like ensure_develop) should be properly wired through CLI initialization to maintain async/await consistency throughout the codebase. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- When removing git operations from agent prompts, audit all related documentation files (git-flow.md, coding.md, coordinator.md) to ensure consistency across the codebase. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- GitHubPlatform can be implemented using httpx with REST API instead of relying on the gh CLI tool, providing more direct control and fewer external dependencies. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Parse GitHub remote URLs (e.g., git@github.com:owner/repo.git) into structured components using a dedicated utility function for reusability across the codebase. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- When simplifying a configuration class, systematically remove associated factory functions and null/placeholder implementations that were built around the more complex structure. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- After major structural changes to a core module (like PlatformConfig), all related test files must be reviewed and updated or removed, including factory tests, protocol tests, and property-based tests. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Post-harvest remote integration should be wired into the session lifecycle via a static method on the session runner class, with conditional push/PR logic based on branch type and remote platform configuration. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Remote integration logic branches on two dimensions: branch type (develop vs feature) and platform settings (auto_merge enabled/disabled), determining whether to push directly or create a pull request. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Checkpoint validation for platform/git overhaul involves verifying 1040+ tests pass, spec tests pass, linter cleanliness, file deletion confirmation, and config simplification together as a cohesive acceptance criteria set. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- ensure_develop function should be integrated into session lifecycle rather than called ad-hoc, ensuring consistent develop branch management across the application. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- When implementing new features via TDD, create stub modules and functions first, then write comprehensive failing tests across multiple test file types (unit, property, integration) before implementing logic. _(spec: 20_plan_analysis, confidence: high)_
- Organizing tests across unit, property, and integration test files provides better coverage of different testing concerns and makes the test suite more maintainable. _(spec: 20_plan_analysis, confidence: high)_
- Plan analysis requires both forward and backward passes to compute Earliest Start (ES), Latest Start (LS), and float values for task scheduling. _(spec: 20_plan_analysis, confidence: high)_
- Phase grouping and alternative path detection are key components of comprehensive plan analysis alongside critical path tracing. _(spec: 20_plan_analysis, confidence: medium)_
- Dependency cycle detection can be implemented using depth-first search (DFS) with node coloring (white/gray/black states) to track visiting status and identify back edges that indicate cycles. _(spec: 20_plan_analysis, confidence: high)_
- Lint rules should be implemented as separate validation functions and wired into a central validate_specs() pipeline for consistent execution and maintainability. _(spec: 20_plan_analysis, confidence: high)_
- Dependency format checking can detect standard-format tables and recommend migration to group-level formats as a linting rule to encourage best practices. _(spec: 20_plan_analysis, confidence: medium)_
- When implementing multiple fixers that transform data structures, use an orchestrator function (like apply_fixes) to coordinate them with deduplication and error handling to prevent duplicate transformations and ensure robustness. _(spec: 20_plan_analysis, confidence: high)_
- Fixers that rewrite data formats (like converting standard dependency tables to group-level format) should be implemented as separate, composable functions rather than monolithic transformations. _(spec: 20_plan_analysis, confidence: high)_
- CLI flags like --analyze and --fix should trigger specific analysis or transformation functions and then re-validate/display results to confirm the operation completed successfully. _(spec: 20_plan_analysis, confidence: high)_
- Analysis output should include multiple dimensions (parallelism phases, critical path, float summary) to provide comprehensive insight into task scheduling and project timeline. _(spec: 20_plan_analysis, confidence: medium)_
- When specifying task dependencies for parallelism analysis, identify the earliest sufficient upstream group rather than just any upstream dependency to maximize parallel execution opportunities. _(spec: 20_plan_analysis, confidence: high)_
- When writing test cases for a new feature specification, organize them with clear naming (TS-ID format) and group them by functional areas (identifier extraction, validation, batching, auto-fix) to maintain test suite clarity and enable targeted implementation. _(spec: 21_dependency_interface_validation, confidence: high)_
- Expect most tests to fail initially (21 of 22) when implementing a new rule/feature, with only existing functionality tests passing; this validates that test cases are properly targeting new code paths. _(spec: 21_dependency_interface_validation, confidence: high)_
- When designing tests for a linting rule like stale-dependency, cover multiple dimensions: identifier extraction logic, AI validation integration, batch processing, and auto-fix behavior to ensure comprehensive rule coverage. _(spec: 21_dependency_interface_validation, confidence: medium)_
- Use dataclasses for structured data like DependencyRef to represent domain concepts with clear types and field definitions. _(spec: 21_dependency_interface_validation, confidence: high)_
- Organize validation logic into separate functions (extract_relationship_identifiers, validate_dependency_interfaces, run_stale_dependency_validation) to maintain modularity and testability. _(spec: 21_dependency_interface_validation, confidence: high)_
- When implementing a new fix rule, register it in FIXABLE_RULES to make it discoverable by the fix application system. _(spec: 21_dependency_interface_validation, confidence: high)_
- Fix implementations should use dataclasses to structure fix data (e.g., IdentifierFix) and parse finding messages to extract necessary information for applying the fix. _(spec: 21_dependency_interface_validation, confidence: high)_
- The apply_fixes() function needs to be extended with a handler for each new fix type to transform findings into concrete code modifications. _(spec: 21_dependency_interface_validation, confidence: high)_
- Task group 4 for specification 21_dependency_interface_validation integrates stale-dependency validation into the lint-spec pipeline by updating run_ai_validation() to accept a specs_dir parameter and call run_stale_dependency_validation(). _(spec: 21_dependency_interface_validation, confidence: high)_
- Integration tests for validation pipelines should verify that findings from multiple validators (AI and stale-dependency) appear together in the output. _(spec: 21_dependency_interface_validation, confidence: high)_

## Decisions

- The develop branch setup should be integrated early in the session lifecycle, specifically before worktree creation, to ensure proper initialization order. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Git push instructions should be removed from agent prompt templates to prevent unintended repository modifications. This includes push retry logic in FAILURE POLICY sections. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Simplifying a Platform protocol to a single responsibility method (create_pr) makes the interface more maintainable and easier to implement across different platforms. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Spec-versioned tests (e.g., spec-10 tests) may become obsolete during major overhauls and should be identified and removed rather than patched during structural changes. _(spec: 19_git_and_platform_overhaul, confidence: medium)_
- PlatformConfig should be simplified as part of platform overhaul work, reducing configuration complexity alongside git and platform infrastructure changes. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- The lint-spec CLI must be updated to pass the specs_dir parameter when invoking the validation pipeline to enable stale-dependency checks. _(spec: 21_dependency_interface_validation, confidence: high)_

## Conventions

- Import ordering in Python test files is subject to linter checks and should be reviewed when running linting passes across a test suite. _(spec: 18_live_progress, confidence: high)_
- When verifying completed task groups, ensure all 1029 tests pass and linting is clean before marking as complete to maintain code quality standards. _(spec: 18_live_progress, confidence: high)_
- A comprehensive test suite (1029 tests passing including 14 progress display specific tests) combined with clean linting provides confidence in marking a task group as complete. _(spec: 18_live_progress, confidence: high)_
- Use test naming conventions (TS-##-#) to organize and track related tests in test suites, especially when implementing multi-faceted features like path abbreviation. _(spec: 18_live_progress, confidence: medium)_
- When refactoring core utility functions like path abbreviation, update all existing tests to match the new behavior rather than reverting to old logic, then validate against full test suite. _(spec: 18_live_progress, confidence: high)_
- Package exports should be updated when refactoring internal implementations to maintain clean public API contracts. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- Updating a module's __init__.py exports is essential after deleting or restructuring internal files to prevent broken imports and ensure the public API remains clean. _(spec: 19_git_and_platform_overhaul, confidence: high)_
- A helper function like get_remote_url() in git.py is needed to abstract remote URL retrieval for use in integration workflows. _(spec: 19_git_and_platform_overhaul, confidence: medium)_
- Supersession banners should already be present in earlier specification files (e.g., spec 10) when implementing platform overhaul work, avoiding duplicate implementation. _(spec: 19_git_and_platform_overhaul, confidence: medium)_
- Always verify that newly added failing tests do not cause regressions in existing passing tests when setting up a TDD workflow. _(spec: 20_plan_analysis, confidence: high)_
- Separate formatting logic (format_analysis) from analysis computation (analyze_plan) for better modularity and terminal display management. _(spec: 20_plan_analysis, confidence: medium)_
- Comprehensive unit test coverage (14 tests for fixer implementations) helps validate that individual fixers work correctly before integration, reducing debugging complexity in orchestration logic. _(spec: 20_plan_analysis, confidence: high)_
- Fix summaries and diagnostic output should be printed to stderr while valid results go to stdout, maintaining clean separation between data output and diagnostic information. _(spec: 20_plan_analysis, confidence: high)_
- The standard two-column dependency format is prohibited in dependency specifications; use a three-column format with explicit justification in the Relationship column instead. _(spec: 20_plan_analysis, confidence: high)_
- Use sentinel value 0 (not 1) to indicate upstream specs that do not have a tasks.md file. _(spec: 20_plan_analysis, confidence: high)_
- Test extraction, validation, and batching logic comprehensively before implementing dependent fixer functionality to catch integration issues early. _(spec: 21_dependency_interface_validation, confidence: high)_

## Anti-Patterns

- Template code should not contain direct git push commands; push operations must be wired through proper lifecycle management (e.g., session lifecycle) instead. _(spec: 19_git_and_platform_overhaul, confidence: high)_
