# Erratum 110: TS-110-SMOKE-1 Embedder Bug

**Spec:** 110 (hunt_dedup_and_ignore)
**Identified by:** Coder (task group 4) — embedder choice caused test to be
unpassable regardless of implementation correctness.

## Issue

The smoke test `TestHuntScanPipelineSmoke::test_full_pipeline_only_novel_creates_issue`
(TS-110-SMOKE-1) was written in task group 1 with `_SameVectorEmbedder([1.0, 0.0, 0.0])`
as the embedder. This embedder returns `[1.0, 0.0, 0.0]` for **every** text, making
the cosine similarity between any two texts always 1.0.

The intended test behaviour was:
- Group B: similarity 1.0 to hunt issues → filtered by `filter_known_duplicates`
- Group C: similarity 1.0 to af:ignore issue → filtered by `filter_ignored`
- Group D: similarity 0.0 to everything → passes both gates

However, with `_SameVectorEmbedder`, Group D's embedding is also `[1.0, 0.0, 0.0]`
and its cosine similarity to hunt issues is also 1.0 > 0.85, so Group D is filtered
at the `filter_known_duplicates` stage along with B and C. The test assertion
`len(after_ignore) == 1` is therefore impossible to satisfy.

The test comment noted "For group_d vs anything: orthogonal → similarity 0.0 →
passes" — describing the intended behaviour — but the wrong embedder was chosen.

## Resolution

Replaced `_SameVectorEmbedder([1.0, 0.0, 0.0])` with `_SequenceEmbedder` that
returns distinct orthogonal vectors in the exact order they are consumed by the
two pipeline stages:

| Batch position | Text | Vector | Effect |
|---|---|---|---|
| 0 | Group B (dedup) | `[1,0,0]` | sim=1.0 vs hunt → dedup-filtered ✓ |
| 1 | Group C (dedup) | `[0,1,0]` | sim=0.0 vs hunt → passes dedup ✓ |
| 2 | Group D (dedup) | `[0,0,1]` | sim=0.0 vs hunt → passes dedup ✓ |
| 3 | hunt_issue_a (dedup) | `[1,0,0]` | |
| 4 | hunt_issue_b (dedup) | `[1,0,0]` | |
| 5 | Group C (ignore) | `[0,1,0]` | sim=1.0 vs ignore → ignore-filtered ✓ |
| 6 | Group D (ignore) | `[0,0,1]` | sim=0.0 vs ignore → passes ✓ |
| 7 | ignore_issue_c (ignore) | `[0,1,0]` | |

Both `filter_known_duplicates` and `filter_ignored` batch `[group_texts...,
issue_texts...]` in a single `embed_batch` call, so the indices are sequential
across both pipeline stages.

The test assertion (`len(after_ignore) == 1`, `after_ignore[0].title == "Group D -
novel"`) is unchanged. Only the embedder setup was corrected to make the assertion
achievable.
