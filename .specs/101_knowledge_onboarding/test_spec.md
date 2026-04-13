# Test Specification: Knowledge Onboarding

## Overview

Tests verify the onboarding CLI command, the six-phase pipeline orchestrator,
git pattern mining, LLM code analysis, LLM documentation mining, and result
reporting. Unit tests cover individual functions (LLM calls mocked). Property
tests verify invariants. Smoke tests trace the full pipeline end-to-end.

## Test Cases

### TS-101-1: Onboard Command Registration

**Requirement:** 101-REQ-1.1
**Type:** unit
**Description:** Verify onboard command is registered in the CLI group.

**Preconditions:** None.
**Input:** Inspect main CLI group commands.
**Expected:** `"onboard"` is a registered command name.

**Assertion pseudocode:**
```
from agent_fox.cli.app import cli
ASSERT "onboard" in [cmd.name for cmd in cli.commands.values()]
```

### TS-101-2: Onboard Default Path

**Requirement:** 101-REQ-1.2
**Type:** unit
**Description:** Verify onboard uses cwd when --path is not specified.

**Preconditions:** Mock run_onboard to capture args.
**Input:** Invoke onboard command without --path.
**Expected:** project_root argument is the current working directory.

**Assertion pseudocode:**
```
with mock(run_onboard) as m:
    invoke(onboard_cmd, [])
    ASSERT m.call_args.project_root == Path.cwd()
```

### TS-101-3: Entity Graph Phase Runs

**Requirement:** 101-REQ-2.1
**Type:** unit
**Description:** Verify entity graph phase calls analyze_codebase.

**Preconditions:** Mock analyze_codebase and LLM phases.
**Input:** Call run_onboard(project_root, config, db).
**Expected:** analyze_codebase called with project_root and conn.

**Assertion pseudocode:**
```
with mock(analyze_codebase) as m:
    result = await run_onboard(project_root, config, db)
    ASSERT m.called
    ASSERT result.entities_upserted >= 0
```

### TS-101-4: Entity Graph Phase Skippable

**Requirement:** 101-REQ-2.2
**Type:** unit
**Description:** Verify --skip-entities skips entity graph phase.

**Preconditions:** Mock analyze_codebase.
**Input:** Call run_onboard(project_root, config, db, skip_entities=True).
**Expected:** analyze_codebase NOT called, "entities" in phases_skipped.

**Assertion pseudocode:**
```
with mock(analyze_codebase) as m:
    result = await run_onboard(project_root, config, db, skip_entities=True)
    ASSERT not m.called
    ASSERT "entities" in result.phases_skipped
```

### TS-101-5: Ingestion Phase Runs

**Requirement:** 101-REQ-3.1
**Type:** unit
**Description:** Verify ingestion phase calls all three ingest functions.

**Preconditions:** Mock KnowledgeIngestor methods and LLM phases.
**Input:** Call run_onboard(project_root, config, db).
**Expected:** ingest_adrs, ingest_errata, ingest_git_commits all called.

**Assertion pseudocode:**
```
with mock(KnowledgeIngestor) as m:
    result = await run_onboard(project_root, config, db)
    ASSERT m.ingest_adrs.called
    ASSERT m.ingest_errata.called
    ASSERT m.ingest_git_commits.called
```

### TS-101-6: Ingestion Phase Skippable

**Requirement:** 101-REQ-3.2
**Type:** unit
**Description:** Verify --skip-ingestion skips ingestion phase.

**Preconditions:** Mock KnowledgeIngestor.
**Input:** Call run_onboard(project_root, config, db, skip_ingestion=True).
**Expected:** No ingest functions called, "ingestion" in phases_skipped.

**Assertion pseudocode:**
```
with mock(KnowledgeIngestor) as m:
    result = await run_onboard(project_root, config, db, skip_ingestion=True)
    ASSERT not m.ingest_adrs.called
    ASSERT "ingestion" in result.phases_skipped
```

### TS-101-7: Git Mining Detects Fragile Areas

**Requirement:** 101-REQ-4.1
**Type:** unit
**Description:** Verify mine_git_patterns creates fragile_area facts.

**Preconditions:** Mock _parse_git_numstat to return known data with one
file modified in 25 commits.
**Input:** mine_git_patterns(root, conn, fragile_threshold=20).
**Expected:** One fragile_area fact created with correct content.

**Assertion pseudocode:**
```
mock_data = {f"sha{i}": ["src/hot_file.py"] for i in range(25)}
with mock(_parse_git_numstat, return_value=mock_data):
    result = mine_git_patterns(root, conn, fragile_threshold=20)
    ASSERT result.fragile_areas_created == 1
    facts = load_facts_by_spec("onboard", conn)
    fragile = [f for f in facts if f.category == "fragile_area"]
    ASSERT len(fragile) == 1
    ASSERT "src/hot_file.py" in fragile[0].content
```

### TS-101-8: Git Mining Detects Co-Change Patterns

**Requirement:** 101-REQ-4.2
**Type:** unit
**Description:** Verify mine_git_patterns creates pattern facts for
co-changed files.

**Preconditions:** Mock _parse_git_numstat to return known data with two
files modified together in 6 commits.
**Input:** mine_git_patterns(root, conn, cochange_threshold=5).
**Expected:** One pattern fact created with both file names.

**Assertion pseudocode:**
```
mock_data = {f"sha{i}": ["a.py", "b.py"] for i in range(6)}
with mock(_parse_git_numstat, return_value=mock_data):
    result = mine_git_patterns(root, conn, cochange_threshold=5)
    ASSERT result.cochange_patterns_created == 1
    facts = load_facts_by_spec("onboard", conn)
    patterns = [f for f in facts if f.category == "pattern"]
    ASSERT len(patterns) == 1
    ASSERT "a.py" in patterns[0].content
    ASSERT "b.py" in patterns[0].content
```

### TS-101-9: Git Mining Skippable

**Requirement:** 101-REQ-4.7
**Type:** unit
**Description:** Verify --skip-mining skips git pattern mining.

**Preconditions:** Mock mine_git_patterns.
**Input:** Call run_onboard(project_root, config, db, skip_mining=True).
**Expected:** mine_git_patterns NOT called, "mining" in phases_skipped.

**Assertion pseudocode:**
```
with mock(mine_git_patterns) as m:
    result = await run_onboard(project_root, config, db, skip_mining=True)
    ASSERT not m.called
    ASSERT "mining" in result.phases_skipped
```

### TS-101-10: Git Mining Minimum Commit Threshold

**Requirement:** 101-REQ-4.E2
**Type:** unit
**Description:** Verify mining skips when fewer than 10 commits.

**Preconditions:** Mock _parse_git_numstat to return 5 commits.
**Input:** mine_git_patterns(root, conn).
**Expected:** Returns MiningResult with all zeros, no facts created.

**Assertion pseudocode:**
```
mock_data = {f"sha{i}": ["file.py"] for i in range(5)}
with mock(_parse_git_numstat, return_value=mock_data):
    result = mine_git_patterns(root, conn)
    ASSERT result.fragile_areas_created == 0
    ASSERT result.cochange_patterns_created == 0
```

### TS-101-11: Embedding Phase Generates Embeddings

**Requirement:** 101-REQ-7.1
**Type:** unit
**Description:** Verify embedding phase generates missing embeddings.

**Preconditions:** Facts exist in DB without embeddings. Mock
EmbeddingGenerator and LLM phases.
**Input:** Call run_onboard(project_root, config, db).
**Expected:** embeddings_generated > 0 in result.

**Assertion pseudocode:**
```
insert_test_facts(conn, count=3)
result = await run_onboard(project_root, config, db)
ASSERT result.embeddings_generated == 3
```

### TS-101-12: Embedding Phase Skippable

**Requirement:** 101-REQ-7.2
**Type:** unit
**Description:** Verify --skip-embeddings skips embedding phase.

**Preconditions:** None.
**Input:** Call run_onboard(project_root, config, db, skip_embeddings=True).
**Expected:** "embeddings" in phases_skipped.

**Assertion pseudocode:**
```
result = await run_onboard(project_root, config, db, skip_embeddings=True)
ASSERT "embeddings" in result.phases_skipped
```

### TS-101-13: OnboardResult Fields

**Requirement:** 101-REQ-8.1
**Type:** unit
**Description:** Verify OnboardResult has all required fields.

**Preconditions:** None.
**Input:** Construct OnboardResult().
**Expected:** All fields accessible with correct defaults.

**Assertion pseudocode:**
```
r = OnboardResult()
ASSERT r.entities_upserted == 0
ASSERT r.code_facts_created == 0
ASSERT r.doc_facts_created == 0
ASSERT r.phases_skipped == []
ASSERT r.phases_errored == []
ASSERT r.elapsed_seconds == 0.0
ASSERT isinstance(dataclasses.asdict(r), dict)
```

### TS-101-14: JSON Output Mode

**Requirement:** 101-REQ-1.5
**Type:** unit
**Description:** Verify JSON output mode emits OnboardResult as JSON.

**Preconditions:** Mock run_onboard to return known result.
**Input:** Invoke onboard command with --json flag.
**Expected:** stdout contains valid JSON with OnboardResult fields.

**Assertion pseudocode:**
```
with mock(run_onboard, return_value=OnboardResult(entities_upserted=5)):
    output = invoke(onboard_cmd, ["--json"])
    parsed = json.loads(output.stdout)
    ASSERT parsed["entities_upserted"] == 5
```

### TS-101-15: MiningResult Fields

**Requirement:** 101-REQ-4.6
**Type:** unit
**Description:** Verify MiningResult has required fields.

**Preconditions:** None.
**Input:** Construct MiningResult().
**Expected:** All fields accessible with correct defaults.

**Assertion pseudocode:**
```
r = MiningResult()
ASSERT r.fragile_areas_created == 0
ASSERT r.cochange_patterns_created == 0
ASSERT r.commits_analyzed == 0
ASSERT r.files_analyzed == 0
```

### TS-101-16: Duplicate Mining Fact Prevention

**Requirement:** 101-REQ-4.E3
**Type:** unit
**Description:** Verify mining skips facts that already exist.

**Preconditions:** Insert a fragile_area fact with fingerprint keyword.
**Input:** mine_git_patterns with data that would create the same fact.
**Expected:** fragile_areas_created == 0 (duplicate skipped).

**Assertion pseudocode:**
```
insert_fact(conn, category="fragile_area", keywords=["onboard:fragile:hot.py"])
mock_data = {f"sha{i}": ["hot.py"] for i in range(25)}
with mock(_parse_git_numstat, return_value=mock_data):
    result = mine_git_patterns(root, conn, fragile_threshold=20)
    ASSERT result.fragile_areas_created == 0
```

### TS-101-17: Parse Git Numstat

**Requirement:** 101-REQ-4.1
**Type:** unit
**Description:** Verify _parse_git_numstat correctly parses git output.

**Preconditions:** Mock subprocess.run.
**Input:** Known git log --numstat output.
**Expected:** Correct mapping of commit SHA to file paths.

**Assertion pseudocode:**
```
git_output = "sha1\n10\t5\tsrc/a.py\n3\t1\tsrc/b.py\n\nsha2\n1\t1\tsrc/a.py\n"
with mock(subprocess.run, stdout=git_output):
    result = _parse_git_numstat(root, days=365)
    ASSERT result == {"sha1": ["src/a.py", "src/b.py"], "sha2": ["src/a.py"]}
```

### TS-101-18: Compute File Frequencies

**Requirement:** 101-REQ-4.1
**Type:** unit
**Description:** Verify _compute_file_frequencies counts correctly.

**Preconditions:** None.
**Input:** Known commit_files mapping.
**Expected:** Correct per-file counts.

**Assertion pseudocode:**
```
commit_files = {"sha1": ["a.py", "b.py"], "sha2": ["a.py"], "sha3": ["a.py", "c.py"]}
result = _compute_file_frequencies(commit_files)
ASSERT result == {"a.py": 3, "b.py": 1, "c.py": 1}
```

### TS-101-19: Compute Co-Change Counts

**Requirement:** 101-REQ-4.2
**Type:** unit
**Description:** Verify _compute_cochange_counts counts correctly.

**Preconditions:** None.
**Input:** Known commit_files mapping.
**Expected:** Correct per-pair counts with sorted tuple keys.

**Assertion pseudocode:**
```
commit_files = {"sha1": ["a.py", "b.py"], "sha2": ["a.py", "b.py"], "sha3": ["a.py"]}
result = _compute_cochange_counts(commit_files)
ASSERT result == {("a.py", "b.py"): 2}
```

### TS-101-20: Code Analysis Creates Facts

**Requirement:** 101-REQ-5.1
**Type:** unit
**Description:** Verify analyze_code_with_llm creates facts from LLM output.

**Preconditions:** tmp_path with a source file (e.g. Python or Go). Mock
ai_call to return known JSON response. Mock _is_mining_fact_exists to
return False.
**Input:** analyze_code_with_llm(tmp_path, conn, model="STANDARD").
**Expected:** Facts created matching LLM response, with fingerprint keywords.

**Assertion pseudocode:**
```
llm_response = json.dumps([{
    "content": "Uses repository pattern for data access",
    "category": "pattern",
    "confidence": "high",
    "keywords": ["repository", "data access"]
}])
with mock(ai_call, return_value=(llm_response, None)):
    result = await analyze_code_with_llm(tmp_path, conn)
    ASSERT result.facts_created == 1
    ASSERT result.files_analyzed == 1
    facts = load_facts_by_spec("onboard", conn)
    ASSERT any("repository pattern" in f.content for f in facts)
    ASSERT any("onboard:code:" in kw for f in facts for kw in f.keywords)
```

### TS-101-21: Code Analysis File Prioritization

**Requirement:** 101-REQ-5.2
**Type:** unit
**Description:** Verify files are analyzed in import-count order.

**Preconditions:** Entity graph with file entities and import edges. Three
files (any language) where file_b has most imports.
**Input:** _get_files_by_priority(conn, project_root).
**Expected:** file_b appears first in the returned list.

**Assertion pseudocode:**
```
# Insert entities: file_a (0 imports), file_b (5 imports), file_c (2 imports)
# Files may be any language (e.g., .go, .rs, .ts) — entity graph is language-agnostic
files = _get_files_by_priority(conn, project_root)
ASSERT files[0].name == "file_b"  # most imported first, any language
```

### TS-101-22: Code Analysis Skippable

**Requirement:** 101-REQ-5.4
**Type:** unit
**Description:** Verify --skip-code-analysis skips the phase.

**Preconditions:** Mock analyze_code_with_llm.
**Input:** run_onboard(..., skip_code_analysis=True).
**Expected:** analyze_code_with_llm NOT called, "code_analysis" in skipped.

**Assertion pseudocode:**
```
with mock(analyze_code_with_llm) as m:
    result = await run_onboard(root, config, db, skip_code_analysis=True)
    ASSERT not m.called
    ASSERT "code_analysis" in result.phases_skipped
```

### TS-101-23: Code Analysis Result Fields

**Requirement:** 101-REQ-5.5
**Type:** unit
**Description:** Verify CodeAnalysisResult has required fields.

**Preconditions:** None.
**Input:** Construct CodeAnalysisResult().
**Expected:** All fields accessible with correct defaults.

**Assertion pseudocode:**
```
r = CodeAnalysisResult()
ASSERT r.facts_created == 0
ASSERT r.files_analyzed == 0
ASSERT r.files_skipped == 0
```

### TS-101-24: Code Analysis Dedup

**Requirement:** 101-REQ-5.6
**Type:** unit
**Description:** Verify code analysis skips previously analyzed files.

**Preconditions:** Insert fact with fingerprint keyword
"onboard:code:src/analyzed.py".
**Input:** analyze_code_with_llm on project containing src/analyzed.py.
**Expected:** src/analyzed.py skipped, files_skipped incremented.

**Assertion pseudocode:**
```
insert_fact(conn, keywords=["onboard:code:src/analyzed.py"])
result = await analyze_code_with_llm(tmp_path, conn)
ASSERT result.files_skipped >= 1
```

### TS-101-25: Doc Mining Creates Facts

**Requirement:** 101-REQ-6.1
**Type:** unit
**Description:** Verify mine_docs_with_llm creates facts from LLM output.

**Preconditions:** tmp_path with README.md. Mock ai_call to return known
JSON response.
**Input:** mine_docs_with_llm(tmp_path, conn, model="STANDARD").
**Expected:** Facts created matching LLM response, with fingerprint keywords.

**Assertion pseudocode:**
```
llm_response = json.dumps([{
    "content": "All PRs require two approvals before merge",
    "category": "convention",
    "confidence": "high",
    "keywords": ["PR", "review", "approval"]
}])
with mock(ai_call, return_value=(llm_response, None)):
    result = await mine_docs_with_llm(tmp_path, conn)
    ASSERT result.facts_created == 1
    ASSERT result.docs_analyzed == 1
    facts = load_facts_by_spec("onboard", conn)
    ASSERT any("onboard:doc:" in kw for f in facts for kw in f.keywords)
```

### TS-101-26: Doc Mining File Collection

**Requirement:** 101-REQ-6.2
**Type:** unit
**Description:** Verify _collect_doc_files finds correct files and
excludes ADR/errata directories.

**Preconditions:** tmp_path with README.md, docs/guide.md, docs/adr/01.md,
docs/errata/e1.md.
**Input:** _collect_doc_files(tmp_path).
**Expected:** Returns README.md and docs/guide.md. Excludes docs/adr/01.md
and docs/errata/e1.md.

**Assertion pseudocode:**
```
files = _collect_doc_files(tmp_path)
names = [f.name for f in files]
ASSERT "README.md" in names
ASSERT "guide.md" in names
ASSERT "01.md" not in names
ASSERT "e1.md" not in names
```

### TS-101-27: Doc Mining Skippable

**Requirement:** 101-REQ-6.3
**Type:** unit
**Description:** Verify --skip-doc-mining skips the phase.

**Preconditions:** Mock mine_docs_with_llm.
**Input:** run_onboard(..., skip_doc_mining=True).
**Expected:** mine_docs_with_llm NOT called, "doc_mining" in skipped.

**Assertion pseudocode:**
```
with mock(mine_docs_with_llm) as m:
    result = await run_onboard(root, config, db, skip_doc_mining=True)
    ASSERT not m.called
    ASSERT "doc_mining" in result.phases_skipped
```

### TS-101-28: Doc Mining Result Fields

**Requirement:** 101-REQ-6.4
**Type:** unit
**Description:** Verify DocMiningResult has required fields.

**Preconditions:** None.
**Input:** Construct DocMiningResult().
**Expected:** All fields accessible with correct defaults.

**Assertion pseudocode:**
```
r = DocMiningResult()
ASSERT r.facts_created == 0
ASSERT r.docs_analyzed == 0
ASSERT r.docs_skipped == 0
```

### TS-101-29: Doc Mining Dedup

**Requirement:** 101-REQ-6.6
**Type:** unit
**Description:** Verify doc mining skips previously mined documents.

**Preconditions:** Insert fact with fingerprint keyword
"onboard:doc:README.md".
**Input:** mine_docs_with_llm on project containing README.md.
**Expected:** README.md skipped, docs_skipped incremented.

**Assertion pseudocode:**
```
insert_fact(conn, keywords=["onboard:doc:README.md"])
result = await mine_docs_with_llm(tmp_path, conn)
ASSERT result.docs_skipped >= 1
```

### TS-101-30: Model Option Passed to LLM Phases

**Requirement:** 101-REQ-1.6
**Type:** unit
**Description:** Verify --model option is forwarded to LLM phases.

**Preconditions:** Mock analyze_code_with_llm and mine_docs_with_llm to
capture args.
**Input:** run_onboard(..., model="ADVANCED").
**Expected:** Both LLM phases called with model="ADVANCED".

**Assertion pseudocode:**
```
with mock(analyze_code_with_llm) as code_m, mock(mine_docs_with_llm) as doc_m:
    await run_onboard(root, config, db, model="ADVANCED")
    ASSERT code_m.call_args.model == "ADVANCED"
    ASSERT doc_m.call_args.model == "ADVANCED"
```

### TS-101-31: Parse LLM Facts

**Requirement:** 101-REQ-5.1
**Type:** unit
**Description:** Verify _parse_llm_facts correctly parses JSON response.

**Preconditions:** None.
**Input:** Valid JSON array with fact objects.
**Expected:** Returns list of Fact objects with correct fields.

**Assertion pseudocode:**
```
raw = json.dumps([{
    "content": "Uses singleton pattern",
    "category": "pattern",
    "confidence": "high",
    "keywords": ["singleton"]
}])
facts = _parse_llm_facts(raw, spec_name="onboard", file_path="main.py", source_type="code")
ASSERT len(facts) == 1
ASSERT facts[0].content == "Uses singleton pattern"
ASSERT facts[0].category == "pattern"
ASSERT facts[0].spec_name == "onboard"
ASSERT "onboard:code:main.py" in facts[0].keywords
```

## Edge Case Tests

### TS-101-E1: Invalid Path

**Requirement:** 101-REQ-1.E1
**Type:** unit
**Description:** Verify error on non-existent path.

**Preconditions:** None.
**Input:** Invoke onboard with --path /nonexistent.
**Expected:** Exit code 2 (click validation error) or exit code 1.

**Assertion pseudocode:**
```
result = invoke(onboard_cmd, ["--path", "/nonexistent"])
ASSERT result.exit_code != 0
```

### TS-101-E2: Not a Git Repository

**Requirement:** 101-REQ-1.E2
**Type:** unit
**Description:** Verify git phases skipped for non-git directory.

**Preconditions:** tmp_path with no .git directory. Mock LLM phases.
**Input:** run_onboard(tmp_path, config, db).
**Expected:** Git ingestion and mining skipped, no error.

**Assertion pseudocode:**
```
result = await run_onboard(tmp_path, config, db)
ASSERT result.git_commits_ingested == 0
ASSERT result.fragile_areas_created == 0
```

### TS-101-E3: Entity Graph Phase Failure

**Requirement:** 101-REQ-2.E1
**Type:** unit
**Description:** Verify entity graph failure doesn't abort pipeline.

**Preconditions:** Mock analyze_codebase to raise RuntimeError.
**Input:** run_onboard(project_root, config, db).
**Expected:** "entities" in phases_errored, other phases still run.

**Assertion pseudocode:**
```
with mock(analyze_codebase, side_effect=RuntimeError("parse error")):
    result = await run_onboard(project_root, config, db)
    ASSERT "entities" in result.phases_errored
    ASSERT result.adrs_ingested >= 0
```

### TS-101-E4: Individual Ingestion Source Failure

**Requirement:** 101-REQ-3.E1
**Type:** unit
**Description:** Verify one ingestion source failing doesn't block others.

**Preconditions:** Mock ingest_adrs to raise, others to succeed.
**Input:** run_onboard(project_root, config, db).
**Expected:** Errata and git commits still ingested.

**Assertion pseudocode:**
```
with mock(ingest_adrs, side_effect=Exception("adr error")):
    result = await run_onboard(project_root, config, db)
    ASSERT result.errata_ingested >= 0
    ASSERT result.git_commits_ingested >= 0
```

### TS-101-E5: Embedding Generation Failure

**Requirement:** 101-REQ-7.E1
**Type:** unit
**Description:** Verify embedding failures are best-effort.

**Preconditions:** Mock embed_text to return None for some facts.
**Input:** run_onboard with facts in DB.
**Expected:** embeddings_failed > 0, no exception raised.

**Assertion pseudocode:**
```
result = await run_onboard(project_root, config, db)
ASSERT result.embeddings_failed > 0
ASSERT result.embeddings_generated > 0
```

### TS-101-E6: Non-Git Ingestion Phase

**Requirement:** 101-REQ-3.3
**Type:** unit
**Description:** Verify non-git directory still ingests ADRs and errata.

**Preconditions:** tmp_path with docs/adr/ containing an ADR file. Mock
LLM phases.
**Input:** run_onboard(tmp_path, config, db).
**Expected:** ADRs ingested, git commits skipped.

**Assertion pseudocode:**
```
result = await run_onboard(tmp_path, config, db)
ASSERT result.adrs_ingested >= 1
ASSERT result.git_commits_ingested == 0
```

### TS-101-E7: Code Analysis LLM Failure Per File

**Requirement:** 101-REQ-5.E1
**Type:** unit
**Description:** Verify LLM failure for one file doesn't block others.

**Preconditions:** Two source files in tmp_path. Mock ai_call to raise on
first call, succeed on second.
**Input:** analyze_code_with_llm(tmp_path, conn).
**Expected:** files_skipped == 1, files_analyzed == 1.

**Assertion pseudocode:**
```
with mock(ai_call, side_effect=[Exception("LLM error"), (llm_json, None)]):
    result = await analyze_code_with_llm(tmp_path, conn)
    ASSERT result.files_skipped == 1
    ASSERT result.files_analyzed == 1
```

### TS-101-E8: Code Analysis Empty Entity Graph

**Requirement:** 101-REQ-5.E2
**Type:** unit
**Description:** Verify fallback to disk scan when entity graph is empty
(e.g., entity graph phase was skipped or no source files were parseable).

**Preconditions:** Empty entity graph tables (no file entities for any
language). tmp_path with source files (any language). Mock ai_call.
**Input:** analyze_code_with_llm(tmp_path, conn).
**Expected:** Files found via disk scan using SOURCE_EXTENSIONS,
files_analyzed > 0.

**Assertion pseudocode:**
```
# Entity graph has no file entities
result = await analyze_code_with_llm(tmp_path, conn)
ASSERT result.files_analyzed > 0
```

### TS-101-E9: Code Analysis Unparseable LLM Response

**Requirement:** 101-REQ-5.E3
**Type:** unit
**Description:** Verify unparseable LLM response skips file.

**Preconditions:** Mock ai_call to return non-JSON text.
**Input:** analyze_code_with_llm(tmp_path, conn).
**Expected:** files_skipped incremented, no exception.

**Assertion pseudocode:**
```
with mock(ai_call, return_value=("not valid json", None)):
    result = await analyze_code_with_llm(tmp_path, conn)
    ASSERT result.files_skipped >= 1
    ASSERT result.facts_created == 0
```

### TS-101-E10: Doc Mining LLM Failure Per Doc

**Requirement:** 101-REQ-6.E1
**Type:** unit
**Description:** Verify LLM failure for one doc doesn't block others.

**Preconditions:** Two markdown files. Mock ai_call to fail on first.
**Input:** mine_docs_with_llm(tmp_path, conn).
**Expected:** docs_skipped == 1, docs_analyzed == 1.

**Assertion pseudocode:**
```
with mock(ai_call, side_effect=[Exception("LLM error"), (llm_json, None)]):
    result = await mine_docs_with_llm(tmp_path, conn)
    ASSERT result.docs_skipped == 1
    ASSERT result.docs_analyzed == 1
```

### TS-101-E11: No Documentation Files Found

**Requirement:** 101-REQ-6.E2
**Type:** unit
**Description:** Verify phase skips when no docs found.

**Preconditions:** tmp_path with no markdown files.
**Input:** mine_docs_with_llm(tmp_path, conn).
**Expected:** docs_analyzed == 0, docs_skipped == 0.

**Assertion pseudocode:**
```
result = await mine_docs_with_llm(tmp_path, conn)
ASSERT result.docs_analyzed == 0
ASSERT result.facts_created == 0
```

### TS-101-E12: Doc Mining Unparseable LLM Response

**Requirement:** 101-REQ-6.E3
**Type:** unit
**Description:** Verify unparseable LLM response skips document.

**Preconditions:** Mock ai_call to return non-JSON text.
**Input:** mine_docs_with_llm(tmp_path, conn).
**Expected:** docs_skipped incremented, no exception.

**Assertion pseudocode:**
```
with mock(ai_call, return_value=("not valid json", None)):
    result = await mine_docs_with_llm(tmp_path, conn)
    ASSERT result.docs_skipped >= 1
```

## Property Test Cases

### TS-101-P1: Mining Threshold Monotonicity

**Property:** Property 1 from design.md
**Validates:** 101-REQ-4.1, 101-REQ-4.4
**Type:** property
**Description:** Higher fragile threshold produces fewer or equal facts.

**For any:** threshold_low, threshold_high where threshold_low <= threshold_high.
**Invariant:** fragile_areas at threshold_high <= fragile_areas at threshold_low.

**Assertion pseudocode:**
```
FOR ANY threshold_low: int(1..50), threshold_high: int(threshold_low..100):
    result_low = mine_git_patterns(root, conn1, fragile_threshold=threshold_low)
    result_high = mine_git_patterns(root, conn2, fragile_threshold=threshold_high)
    ASSERT result_high.fragile_areas_created <= result_low.fragile_areas_created
```

### TS-101-P2: Onboard Idempotency

**Property:** Property 2 from design.md
**Validates:** 101-REQ-8.2
**Type:** property
**Description:** Second run creates zero new facts.

**For any:** N/A (deterministic check against fixed test data).
**Invariant:** Second run's creation counts are all zero.

**Assertion pseudocode:**
```
result1 = await run_onboard(project_root, config, db)
result2 = await run_onboard(project_root, config, db)
ASSERT result2.adrs_ingested == 0
ASSERT result2.errata_ingested == 0
ASSERT result2.git_commits_ingested == 0
ASSERT result2.fragile_areas_created == 0
ASSERT result2.cochange_patterns_created == 0
ASSERT result2.code_facts_created == 0
ASSERT result2.doc_facts_created == 0
```

### TS-101-P3: Mining Fact Validity

**Property:** Property 3 from design.md
**Validates:** 101-REQ-4.1, 101-REQ-4.2
**Type:** property
**Description:** Every mined fact has required fields correctly set.

**For any:** Git history with arbitrary file paths.
**Invariant:** All created facts have non-empty content, valid category,
spec_name="onboard", non-empty keywords, confidence in [0.0, 1.0].

**Assertion pseudocode:**
```
FOR ANY file_paths: list[str], commit_count: int(20..50):
    mine_git_patterns(root, conn, fragile_threshold=10)
    facts = load_facts_by_spec("onboard", conn)
    FOR fact IN facts:
        ASSERT fact.content != ""
        ASSERT fact.category in {"fragile_area", "pattern"}
        ASSERT fact.spec_name == "onboard"
        ASSERT len(fact.keywords) >= 1
        ASSERT 0.0 <= fact.confidence <= 1.0
```

### TS-101-P4: Phase Independence

**Property:** Property 4 from design.md
**Validates:** 101-REQ-2.2, 101-REQ-3.2, 101-REQ-4.7, 101-REQ-5.4,
101-REQ-6.3, 101-REQ-7.2
**Type:** property
**Description:** Skipped phases do not affect non-skipped phases.

**For any:** Combination of skip flags.
**Invariant:** The mining facts created by a non-skipped mining phase are
the same regardless of which other phases are skipped.

**Assertion pseudocode:**
```
FOR ANY skip_entities: bool, skip_ingestion: bool:
    r1 = await run_onboard(root, config, db1, skip_entities=skip_entities,
                           skip_ingestion=skip_ingestion, skip_mining=False)
    r2 = await run_onboard(root, config, db2, skip_entities=True,
                           skip_ingestion=True, skip_mining=False)
    ASSERT r1.fragile_areas_created == r2.fragile_areas_created
    ASSERT r1.cochange_patterns_created == r2.cochange_patterns_created
```

### TS-101-P5: LLM Fact Validity

**Property:** Property 5 from design.md
**Validates:** 101-REQ-5.1, 101-REQ-6.1
**Type:** property
**Description:** Every LLM-derived fact has required fields correctly set.

**For any:** Valid LLM JSON response with arbitrary content.
**Invariant:** All parsed facts have non-empty content, valid category,
spec_name="onboard", non-empty keywords with fingerprint, confidence
in [0.0, 1.0].

**Assertion pseudocode:**
```
FOR ANY content: str, category: Category, confidence: str("high"|"medium"|"low"):
    raw = json.dumps([{"content": content, "category": category,
                       "confidence": confidence, "keywords": ["test"]}])
    facts = _parse_llm_facts(raw, "onboard", "file.py", "code")
    FOR fact IN facts:
        ASSERT fact.content != ""
        ASSERT fact.category in Category.__members__.values()
        ASSERT fact.spec_name == "onboard"
        ASSERT any("onboard:code:file.py" in kw for kw in fact.keywords)
        ASSERT 0.0 <= fact.confidence <= 1.0
```

## Integration Smoke Tests

### TS-101-SMOKE-1: Full Onboard Pipeline

**Execution Path:** Path 1 from design.md
**Description:** Verify the full onboarding pipeline end-to-end.

**Setup:** Real DuckDB with migrations. tmp_path with source files (any
language), docs/adr/, and README.md. Mock subprocess for git commands
(git log, git rev-parse). Mock ai_call for LLM phases. Mock
EmbeddingGenerator.

**Trigger:** `await run_onboard(tmp_path, config, db)`

**Expected side effects:**
- Entity graph populated (entities_upserted > 0)
- ADR facts ingested (adrs_ingested > 0)
- Git commit facts ingested (git_commits_ingested > 0)
- Mining facts created (if mock data has enough commits)
- Code analysis facts created (code_facts_created > 0)
- Doc mining facts created (doc_facts_created > 0)
- Embeddings generated for all facts
- elapsed_seconds > 0

**Must NOT satisfy with:** Mocking run_onboard or any phase orchestration.

**Assertion pseudocode:**
```
result = await run_onboard(tmp_path, config, db)
ASSERT result.entities_upserted > 0
ASSERT result.adrs_ingested > 0
ASSERT result.code_facts_created > 0
ASSERT result.doc_facts_created > 0
ASSERT result.elapsed_seconds > 0
ASSERT result.phases_errored == []
```

### TS-101-SMOKE-2: Git Mining End-to-End

**Execution Path:** Path 3 from design.md
**Description:** Verify git mining produces correct facts from realistic data.

**Setup:** Real DuckDB with migrations. Mock subprocess to return git log
output with known commit/file data: one file modified 25 times, two files
co-modified 8 times.

**Trigger:** `mine_git_patterns(project_root, conn, fragile_threshold=20,
cochange_threshold=5)`

**Expected side effects:**
- One fragile_area fact for the hot file
- One pattern fact for the co-changed pair
- Facts stored in DuckDB with correct content, category, keywords

**Must NOT satisfy with:** Mocking mine_git_patterns.

**Assertion pseudocode:**
```
result = mine_git_patterns(root, conn, fragile_threshold=20, cochange_threshold=5)
ASSERT result.fragile_areas_created == 1
ASSERT result.cochange_patterns_created == 1
facts = load_facts_by_spec("onboard", conn)
ASSERT len(facts) == 2
```

### TS-101-SMOKE-3: Code Analysis End-to-End

**Execution Path:** Path 4 from design.md
**Description:** Verify code analysis produces facts from source files.

**Setup:** Real DuckDB with migrations. tmp_path with source files (mix of
languages, e.g. .py and .go). Mock ai_call to return structured JSON. Real
_parse_llm_facts.

**Trigger:** `await analyze_code_with_llm(tmp_path, conn, model="STANDARD")`

**Expected side effects:**
- Facts stored in DuckDB with correct categories and fingerprint keywords
- files_analyzed matches number of source files
- facts_created > 0

**Must NOT satisfy with:** Mocking analyze_code_with_llm.

**Assertion pseudocode:**
```
result = await analyze_code_with_llm(tmp_path, conn)
ASSERT result.facts_created > 0
ASSERT result.files_analyzed > 0
facts = load_facts_by_spec("onboard", conn)
ASSERT any("onboard:code:" in kw for f in facts for kw in f.keywords)
```

### TS-101-SMOKE-4: Doc Mining End-to-End

**Execution Path:** Path 5 from design.md
**Description:** Verify doc mining produces facts from documentation.

**Setup:** Real DuckDB with migrations. tmp_path with README.md and
docs/guide.md. Mock ai_call to return structured JSON. Real _parse_llm_facts.

**Trigger:** `await mine_docs_with_llm(tmp_path, conn, model="STANDARD")`

**Expected side effects:**
- Facts stored in DuckDB with correct categories and fingerprint keywords
- docs_analyzed matches number of doc files (2)
- facts_created > 0

**Must NOT satisfy with:** Mocking mine_docs_with_llm.

**Assertion pseudocode:**
```
result = await mine_docs_with_llm(tmp_path, conn)
ASSERT result.facts_created > 0
ASSERT result.docs_analyzed == 2
facts = load_facts_by_spec("onboard", conn)
ASSERT any("onboard:doc:" in kw for f in facts for kw in f.keywords)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 101-REQ-1.1 | TS-101-1 | unit |
| 101-REQ-1.2 | TS-101-2 | unit |
| 101-REQ-1.5 | TS-101-14 | unit |
| 101-REQ-1.6 | TS-101-30 | unit |
| 101-REQ-1.E1 | TS-101-E1 | unit |
| 101-REQ-1.E2 | TS-101-E2 | unit |
| 101-REQ-2.1 | TS-101-3 | unit |
| 101-REQ-2.2 | TS-101-4 | unit |
| 101-REQ-2.E1 | TS-101-E3 | unit |
| 101-REQ-3.1 | TS-101-5 | unit |
| 101-REQ-3.2 | TS-101-6 | unit |
| 101-REQ-3.3 | TS-101-E6 | unit |
| 101-REQ-3.E1 | TS-101-E4 | unit |
| 101-REQ-4.1 | TS-101-7, TS-101-17, TS-101-18 | unit |
| 101-REQ-4.2 | TS-101-8, TS-101-19 | unit |
| 101-REQ-4.3 | TS-101-17 | unit |
| 101-REQ-4.4 | TS-101-7 | unit |
| 101-REQ-4.5 | TS-101-8 | unit |
| 101-REQ-4.6 | TS-101-15 | unit |
| 101-REQ-4.7 | TS-101-9 | unit |
| 101-REQ-4.E1 | TS-101-E2 | unit |
| 101-REQ-4.E2 | TS-101-10 | unit |
| 101-REQ-4.E3 | TS-101-16 | unit |
| 101-REQ-5.1 | TS-101-20, TS-101-31 | unit |
| 101-REQ-5.2 | TS-101-21 | unit |
| 101-REQ-5.3 | TS-101-30 | unit |
| 101-REQ-5.4 | TS-101-22 | unit |
| 101-REQ-5.5 | TS-101-23 | unit |
| 101-REQ-5.6 | TS-101-24 | unit |
| 101-REQ-5.E1 | TS-101-E7 | unit |
| 101-REQ-5.E2 | TS-101-E8 | unit |
| 101-REQ-5.E3 | TS-101-E9 | unit |
| 101-REQ-6.1 | TS-101-25 | unit |
| 101-REQ-6.2 | TS-101-26 | unit |
| 101-REQ-6.3 | TS-101-27 | unit |
| 101-REQ-6.4 | TS-101-28 | unit |
| 101-REQ-6.5 | TS-101-30 | unit |
| 101-REQ-6.6 | TS-101-29 | unit |
| 101-REQ-6.E1 | TS-101-E10 | unit |
| 101-REQ-6.E2 | TS-101-E11 | unit |
| 101-REQ-6.E3 | TS-101-E12 | unit |
| 101-REQ-7.1 | TS-101-11 | unit |
| 101-REQ-7.2 | TS-101-12 | unit |
| 101-REQ-7.E1 | TS-101-E5 | unit |
| 101-REQ-8.1 | TS-101-13 | unit |
| 101-REQ-8.2 | TS-101-16, TS-101-24, TS-101-29 | unit |
| 101-REQ-8.3 | TS-101-13 | unit |
| Property 1 | TS-101-P1 | property |
| Property 2 | TS-101-P2 | property |
| Property 3 | TS-101-P3 | property |
| Property 4 | TS-101-P4 | property |
| Property 5 | TS-101-P5 | property |
