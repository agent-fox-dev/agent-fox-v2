# Audit Report: 86_spec_generator

**Overall Verdict:** FAIL
**Date:** 2026-04-07 16:54:58 UTC
**Attempt:** 1

## Per-Entry Results

| TS Entry | Verdict | Test Functions | Notes |
|----------|---------|----------------|-------|
| TS-86-1 | PASS | tests/unit/platform/test_platform_extensions.py::TestRemoveLabel::test_sends_delete_to_correct_endpoint | Verifies DELETE request to correct endpoint with URL encoding. Checks method, URL, and call count. |
| TS-86-2 | PASS | tests/unit/platform/test_platform_extensions.py::TestRemoveLabelIdempotent::test_404_succeeds_silently | Mocks 404 response and verifies no exception raised. |
| TS-86-3 | PASS | tests/unit/platform/test_platform_extensions.py::TestListIssueComments::test_returns_ordered_comments | Verifies two IssueComment objects with correct fields (id, body, user, created_at), correct order, and correct API endpoint. |
| TS-86-4 | PASS | tests/unit/platform/test_platform_extensions.py::TestGetIssue::test_returns_issue_result | Verifies IssueResult with number, title, html_url, body fields. |
| TS-86-5 | PASS | tests/unit/platform/test_platform_extensions.py::TestPlatformProtocol::test_github_platform_satisfies_protocol | Checks isinstance, hasattr, and callable for all three new methods. |
| TS-86-6 | PASS | tests/unit/nightshift/test_spec_gen.py::TestDiscoverAfSpecIssues::test_polls_both_labels | Verifies both af:spec and af:spec-pending labels are queried. |
| TS-86-7 | PASS | tests/unit/nightshift/test_spec_gen.py::TestSequentialProcessing::test_processes_only_oldest | Verifies only the oldest issue (number=1) is processed via assert_called_once and checking processed_issue.number. |
| TS-86-8 | PASS | tests/unit/nightshift/test_spec_gen.py::TestPendingIssueReanalysis::test_new_human_comment_triggers_transition | Verifies assign_label(10, 'af:spec-analyzing') and remove_label(10, 'af:spec-pending') are called. |
| TS-86-9 | PASS | tests/unit/nightshift/test_spec_gen.py::TestPendingIssueSkipped::test_no_new_comment_skips | Verifies process_issue is not called when no new human comment. |
| TS-86-10 | PASS | tests/unit/nightshift/test_spec_gen.py::TestLabelTransitionOrder::test_assign_before_remove | Tracks call order and asserts ['assign', 'remove'] ordering. |
| TS-86-11 | PASS | tests/unit/nightshift/test_spec_gen.py::TestInitialTransitionToAnalyzing::test_transitions_to_analyzing | Verifies assign_label called with LABEL_ANALYZING. |
| TS-86-12 | PASS | tests/unit/nightshift/test_spec_gen.py::TestTransitionToGenerating::test_clear_transitions_to_generating | Verifies assign_label called with LABEL_GENERATING after clear analysis. |
| TS-86-13 | PASS | tests/unit/nightshift/test_spec_gen.py::TestTransitionToDone::test_done_and_closed | Verifies outcome is GENERATED, LABEL_DONE assigned, close_issue called with correct issue number. |
| TS-86-14 | WEAK | tests/unit/nightshift/test_spec_gen.py::TestAnalysisContext::test_sends_full_context | Only asserts isinstance(result, AnalysisResult) and mock_ai.assert_called_once(). Does NOT verify prompt content includes issue body, comments, referenced issues, existing specs, and steering as required by TS spec pseudocode. |
| TS-86-15 | PASS | tests/unit/nightshift/test_spec_gen.py::TestAmbiguousAnalysis::test_ambiguous_posts_clarification | Verifies outcome is PENDING, comment posted with '## Agent Fox' and question content. |
| TS-86-16 | PASS | tests/unit/nightshift/test_spec_gen.py::TestHarvestReferences::test_parses_and_fetches_references | Verifies two ReferencedIssue objects returned with correct numbers. Mocks get_issue and list_issue_comments correctly. |
| TS-86-17 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCountClarificationRounds::test_counts_fox_clarification_comments | Verifies count of 2 for two fox clarification comments with human replies interspersed. |
| TS-86-18 | PASS | tests/unit/nightshift/test_spec_gen.py::TestEscalationAfterMaxRounds::test_escalates_at_max_rounds | Verifies outcome is BLOCKED, comment contains 'Specification Blocked' or 'blocked', and LABEL_BLOCKED assigned. |
| TS-86-19 | PASS | tests/unit/nightshift/test_spec_gen.py::TestFoxCommentDetection::test_fox_comment_detected, tests/unit/nightshift/test_spec_gen.py::TestFoxCommentDetection::test_human_comment_not_detected, tests/unit/nightshift/test_spec_gen.py::TestFoxCommentDetection::test_whitespace_prefix_detected, tests/unit/nightshift/test_spec_gen.py::TestFoxCommentDetection::test_partial_match_not_detected | Covers fox, human, whitespace, and partial match cases. Exceeds TS spec requirements. |
| TS-86-20 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestGenerateSpecPackage::test_produces_five_files | Verifies all 5 files present in SpecPackage and all have non-empty content. |
| TS-86-21 | PASS | tests/unit/nightshift/test_spec_gen.py::TestPrdSourceSection::test_prd_contains_source_section | Verifies '## Source' and issue URL in prd.md content. |
| TS-86-22 | PASS | tests/unit/nightshift/test_spec_gen.py::TestSpecNumbering::test_increments_from_max | Uses tmp_path with 84/85/86 folders, verifies returns 87. |
| TS-86-23 | WEAK | tests/unit/nightshift/test_spec_gen.py::TestSpecGenModelTier::test_uses_configured_model | Assertion uses 'assert "claude-sonnet-4-6" in str(call_kwargs)' which is a fragile string comparison against stringified call args. Should check model kwarg directly. |
| TS-86-24 | PASS | tests/unit/nightshift/test_spec_gen.py::TestDuplicateDetection::test_detects_duplicate | Verifies AI-based duplicate detection with correct is_duplicate and overlapping_spec values. |
| TS-86-25 | PASS | tests/unit/nightshift/test_spec_gen.py::TestDuplicatePostsComment::test_duplicate_posts_comment_and_pending | Verifies outcome is PENDING and comment contains 'supersede' or 'duplicate'. |
| TS-86-26 | PASS | tests/unit/nightshift/test_spec_gen.py::TestSupersedeGeneratesSection::test_supersede_includes_section | Verifies '## Supersedes' and '42_webhook_support' in prd.md content. |
| TS-86-27 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestLandSpec::test_creates_branch_and_commits | Uses real git repo in tmp_path. Verifies commit hash non-empty, prd.md exists, commit message contains expected pattern. |
| TS-86-28 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestDirectMergeStrategy::test_merges_and_deletes_branch | Uses real git repo. Verifies on develop branch and feature branch deleted. |
| TS-86-29 | PASS | tests/unit/nightshift/test_spec_gen.py::TestPRMergeStrategy::test_creates_draft_pr | Verifies create_pull_request called once and branch name in call args. |
| TS-86-30 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCompletionComment::test_completion_comment_content | Verifies completion comment contains spec name, commit hash. Verifies close_issue called. |
| TS-86-31 | PASS | tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigDefaults::test_max_clarification_rounds_default, tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigDefaults::test_max_budget_usd_default, tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigDefaults::test_spec_gen_model_tier_default | All three default values verified: 3, 2.0, 'ADVANCED'. |
| TS-86-32 | WEAK | tests/unit/nightshift/test_spec_gen.py::TestCostTracking::test_tracks_cumulative_cost | Only asserts result.cost > 0. TS spec pseudocode requires verifying cumulative cost at intermediate points ($0.50, $0.80, $1.20). Test mocks most methods and only verifies final cost is positive. |
| TS-86-33 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCostCapAbort::test_aborts_when_budget_exceeded | Verifies outcome is BLOCKED and comment contains 'budget'. |
| TS-86-34 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCostReportedToSharedBudget::test_reports_cost | Verifies budget.total_cost >= 1.50 after run_once with cost=1.50 result. |
| TS-86-E1 | PASS | tests/unit/platform/test_platform_extensions.py::TestRemoveLabelError::test_500_raises_integration_error | Verifies IntegrationError raised on 500 response. |
| TS-86-E2 | PASS | tests/unit/platform/test_platform_extensions.py::TestListIssueCommentsEmpty::test_empty_comments_returns_empty_list | Verifies empty list returned for empty JSON array response. |
| TS-86-E3 | PASS | tests/unit/platform/test_platform_extensions.py::TestGetIssueNotFound::test_404_raises_integration_error | Verifies IntegrationError raised on 404 response. |
| TS-86-E4 | PASS | tests/unit/nightshift/test_spec_gen.py::TestNoIssuesNoOp::test_no_op_on_empty | Verifies process_issue not called when no issues returned. |
| TS-86-E5 | WEAK | tests/unit/nightshift/test_spec_gen.py::TestStaleIssueSkipped::test_stale_issue_skipped_with_warning | Test wraps run_once and the assertion in pytest.raises(Exception). If run_once skips correctly (no exception), pytest.raises will fail. If it raises, the process_issue assertion inside won't execute. Also does not verify warning logged. Structure is incorrect for testing skip behavior. |
| TS-86-E6 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCrashRecoveryAnalyzing::test_resets_stale_analyzing | Verifies assign_label(10, 'af:spec') and remove_label(10, 'af:spec-analyzing') called. |
| TS-86-E7 | PASS | tests/unit/nightshift/test_spec_gen.py::TestCrashRecoveryGenerating::test_resets_stale_generating | Verifies assign_label(10, 'af:spec') and remove_label(10, 'af:spec-generating') called. |
| TS-86-E8 | PASS | tests/unit/nightshift/test_spec_gen.py::TestInaccessibleReferenceSkipped::test_skips_inaccessible_reference | Verifies len(refs) == 0 when get_issue raises IntegrationError. Missing log warning assertion but core behavior verified. |
| TS-86-E9 | WEAK | tests/unit/nightshift/test_spec_gen.py::TestEmptyBodyAmbiguous::test_empty_body_is_ambiguous | Mocks _analyze_issue to return ambiguous rather than testing the system's actual treatment of empty bodies. The test proves process_issue handles ambiguous results (already covered by TS-86-15), not that empty bodies trigger ambiguity. |
| TS-86-E10 | PASS | tests/unit/nightshift/test_spec_gen.py::TestMaxRoundsFirstAnalysis::test_escalation_at_one_round | Verifies escalation with max_clarification_rounds=1 and 1 prior round. |
| TS-86-E11 | PASS | tests/unit/nightshift/test_spec_gen.py::TestApiFailureAborts::test_api_failure_blocks_issue | Verifies outcome is BLOCKED and LABEL_BLOCKED assigned when generation raises exception. |
| TS-86-E12 | PASS | tests/unit/nightshift/test_spec_gen.py::TestNoExistingSpecsPrefix::test_empty_specs_returns_one | Verifies returns 1 when .specs/ exists but has no NN_ folders. |
| TS-86-E13 | PASS | tests/unit/nightshift/test_spec_gen.py::TestNoSpecsSkipsDuplicates::test_skips_when_no_specs | Verifies is_duplicate=False returned and AI not called when empty specs list. |
| TS-86-E14 | PASS | tests/unit/nightshift/test_spec_gen.py::TestBranchCollision::test_appends_suffix_on_collision | Mocks subprocess to simulate branch collision and verifies recovery. |
| TS-86-E15 | PASS | tests/unit/nightshift/test_spec_gen.py::TestMergeFailureBlocks::test_merge_failure_posts_branch | Verifies outcome is BLOCKED and comment contains branch/spec name. |
| TS-86-E16 | PASS | tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigClamping::test_zero_clamped_to_one, tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigClamping::test_negative_clamped_to_one, tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigClamping::test_one_stays_one, tests/unit/nightshift/test_spec_gen_config.py::TestSpecGenConfigClamping::test_valid_value_unchanged | Tests 0, -5, 1, and 5 values. Comprehensive edge case coverage. |
| TS-86-E17 | PASS | tests/unit/nightshift/test_spec_gen.py::TestInvalidModelTierFallback::test_invalid_tier_uses_advanced | Uses TIER_DEFAULTS[ModelTier.ADVANCED] for expected model (not hardcoded). Checks gen._model_id. |
| TS-86-E18 | PASS | tests/unit/nightshift/test_spec_gen.py::TestUnlimitedBudget::test_zero_budget_no_enforcement | Verifies outcome is GENERATED with max_budget_usd=0 and expensive AI calls. |
| TS-86-P1 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P1_label_transition_assign_before_remove | Uses Hypothesis with sampled_from label set. Tracks call order and asserts assign < remove. |
| TS-86-P2 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P2_clarification_round_count_bounded | Uses Hypothesis with mixed fox/human comment lists. Verifies 0 <= rounds <= fox_count. |
| TS-86-P3 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P3_fox_comment_detection_consistent | Uses Hypothesis text strategy. Verifies _is_fox_comment matches body.strip().startswith('## Agent Fox'). |
| TS-86-P4 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P4_spec_number_exceeds_existing | Uses Hypothesis with sets of integers. Creates real spec dirs in tmp_path. Verifies > max or == 1 if empty. |
| TS-86-P5 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P5_remove_label_idempotency | Uses Hypothesis text for labels. Randomly mocks 204/404 responses. Verifies no exception. |
| TS-86-P6 | WEAK | tests/property/test_spec_gen_props.py::test_TS_86_P6_cost_monotonically_nondecreasing | Pure arithmetic test - does not test any implementation class (CostTracker or SpecGenerator). Just proves addition of non-negative floats is monotonic. TS spec requires testing an actual cost tracker implementation. |
| TS-86-P7 | PASS | tests/property/test_spec_gen_props.py::test_TS_86_P7_spec_name_valid_folder_name | Uses Hypothesis with text/integers. Verifies regex pattern and determinism. |
| TS-86-SMOKE-1 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestSmokeHappyPath::test_happy_path_end_to_end | Full pipeline with real git repo. Verifies spec files exist, issue closed, done label, cost reported. |
| TS-86-SMOKE-2 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestSmokeAmbiguousIssue::test_ambiguous_posts_clarification | Verifies clarification comment with '## Agent Fox', pending label, no close. |
| TS-86-SMOKE-3 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestSmokePendingReanalysis::test_pending_reanalysis_generates_spec | Full pipeline from pending with human reply to spec generation. Uses real git repo. |
| TS-86-SMOKE-4 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestSmokeMaxRoundsEscalation::test_escalation_at_max_rounds | Verifies escalation comment, blocked label, and NOT closed. |
| TS-86-SMOKE-5 | PASS | tests/integration/test_spec_gen_lifecycle.py::TestSmokeCostCapExceeded::test_cost_cap_aborts | Verifies budget comment, blocked label, and cost still reported. |

## Summary

6 WEAK entries found (TS-86-14, TS-86-23, TS-86-32, TS-86-E5, TS-86-E9, TS-86-P6). TS-86-14: does not verify AI prompt contents include all required context. TS-86-23: fragile stringified assertion for model tier. TS-86-32: only asserts cost > 0, not cumulative tracking. TS-86-E5: pytest.raises wrapping prevents correct skip/warning verification. TS-86-E9: mocks _analyze_issue instead of testing empty body detection. TS-86-P6: pure arithmetic, does not test any CostTracker implementation.
