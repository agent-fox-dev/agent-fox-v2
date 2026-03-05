# Test Specification: Dependency Interface Validation

## Overview

Tests for backtick identifier extraction, AI cross-reference validation,
batching behavior, graceful degradation, auto-fix for stale dependencies,
and integration with the `lint-spec --ai` pipeline.

## Test Cases

### TS-21-1: Extract backtick identifiers from Relationship text

**Requirement:** 21-REQ-1.1
**Type:** unit
**Description:** Verify backtick-delimited tokens are extracted from
dependency Relationship cells.

**Preconditions:**
- A prd.md with alt-format dependency table containing Relationship text:
  `Uses \`config.Config\` for settings and \`store.Store\` for persistence`

**Input:**
- `extract_relationship_identifiers("my_spec", prd_path)`

**Expected:**
- Returns 2 DependencyRef objects.
- Identifiers are `config.Config` and `store.Store`.

**Assertion pseudocode:**
```
refs = extract_relationship_identifiers("my_spec", prd_path)
ids = [r.identifier for r in refs]
ASSERT "config.Config" in ids
ASSERT "store.Store" in ids
ASSERT len(refs) == 2
```

---

### TS-21-2: Strip trailing parentheses from identifiers

**Requirement:** 21-REQ-1.2
**Type:** unit
**Description:** Verify `Delete()` becomes `Delete` after normalization.

**Preconditions:**
- A prd.md with Relationship text: `Calls \`store.Store.Delete()\` to remove`

**Input:**
- `extract_relationship_identifiers("my_spec", prd_path)`

**Expected:**
- Identifier is `store.Store.Delete` (parentheses stripped).

**Assertion pseudocode:**
```
refs = extract_relationship_identifiers("my_spec", prd_path)
ASSERT refs[0].identifier == "store.Store.Delete"
```

---

### TS-21-3: Preserve dotted paths

**Requirement:** 21-REQ-1.3
**Type:** unit
**Description:** Verify dotted identifiers are preserved as-is.

**Preconditions:**
- A prd.md with Relationship text: `Uses \`store.SnippetStore.Delete\``

**Input:**
- `extract_relationship_identifiers("my_spec", prd_path)`

**Expected:**
- Identifier is `store.SnippetStore.Delete` (unchanged).

**Assertion pseudocode:**
```
refs = extract_relationship_identifiers("my_spec", prd_path)
ASSERT refs[0].identifier == "store.SnippetStore.Delete"
```

---

### TS-21-4: Skip rows with no backtick tokens

**Requirement:** 21-REQ-1.E1
**Type:** unit
**Description:** Verify rows without backtick-delimited tokens produce no
DependencyRef objects.

**Preconditions:**
- A prd.md with Relationship text: `General configuration support`
  (no backticks).

**Input:**
- `extract_relationship_identifiers("my_spec", prd_path)`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
refs = extract_relationship_identifiers("my_spec", prd_path)
ASSERT len(refs) == 0
```

---

### TS-21-5: Standard library tokens are extracted

**Requirement:** 21-REQ-1.E2
**Type:** unit
**Description:** Verify standard library references like `slog` and
`context.Context` are extracted (the AI handles recognition).

**Preconditions:**
- A prd.md with Relationship text:
  `Uses \`slog\` for logging and \`context.Context\` for cancellation`

**Input:**
- `extract_relationship_identifiers("my_spec", prd_path)`

**Expected:**
- Returns 2 DependencyRef objects with identifiers `slog` and
  `context.Context`.

**Assertion pseudocode:**
```
refs = extract_relationship_identifiers("my_spec", prd_path)
ids = [r.identifier for r in refs]
ASSERT "slog" in ids
ASSERT "context.Context" in ids
```

---

### TS-21-6: AI validates identifiers against design.md

**Requirement:** 21-REQ-2.1, 21-REQ-2.3
**Type:** unit
**Description:** Verify AI cross-reference produces no findings for
identifiers that exist in the upstream design.

**Preconditions:**
- Mock AI response: `{"results": [{"identifier": "Config", "found": true,
  "explanation": "Defined as a dataclass", "suggestion": null}]}`

**Input:**
- `validate_dependency_interfaces("01_core", design_text, refs, model)`

**Expected:**
- Returns empty list (all identifiers found).

**Assertion pseudocode:**
```
findings = await validate_dependency_interfaces(
    "01_core", design_text, [ref], model
)
ASSERT len(findings) == 0
```

---

### TS-21-7: AI flags unresolved identifiers

**Requirement:** 21-REQ-2.4, 21-REQ-2.5
**Type:** unit
**Description:** Verify unresolved identifiers produce Warning findings
with explanation and suggestion.

**Preconditions:**
- Mock AI response: `{"results": [{"identifier": "SnippetStore",
  "found": false, "explanation": "Design defines Store, not SnippetStore",
  "suggestion": "Did you mean Store?"}]}`

**Input:**
- `validate_dependency_interfaces("01_core", design_text, refs, model)`

**Expected:**
- Returns 1 finding with severity=warning, rule="stale-dependency".
- Message contains the explanation and suggestion.

**Assertion pseudocode:**
```
findings = await validate_dependency_interfaces(
    "01_core", design_text, [ref], model
)
ASSERT len(findings) == 1
ASSERT findings[0].severity == "warning"
ASSERT findings[0].rule == "stale-dependency"
ASSERT "SnippetStore" in findings[0].message
ASSERT "Store" in findings[0].message
```

---

### TS-21-8: Missing design.md skips validation

**Requirement:** 21-REQ-2.E1
**Type:** unit
**Description:** Verify no findings when upstream spec has no design.md.

**Preconditions:**
- Upstream spec directory exists but has no design.md file.
- DependencyRef objects reference that upstream spec.

**Input:**
- `run_stale_dependency_validation(specs, specs_dir, model)`

**Expected:**
- Returns empty list. No AI call made.

**Assertion pseudocode:**
```
findings = await run_stale_dependency_validation(specs, specs_dir, model)
ASSERT len(findings) == 0
ASSERT mock_client.messages.create.call_count == 0
```

---

### TS-21-9: AI unavailable skips rule

**Requirement:** 21-REQ-2.E2
**Type:** unit
**Description:** Verify AI unavailability logs warning and returns empty.

**Preconditions:**
- AI client raises an exception (e.g., AuthenticationError).

**Input:**
- `run_stale_dependency_validation(specs, specs_dir, model)`

**Expected:**
- Returns empty list.
- Warning logged.

**Assertion pseudocode:**
```
findings = await run_stale_dependency_validation(specs, specs_dir, model)
ASSERT len(findings) == 0
# verify warning was logged
```

---

### TS-21-10: Malformed AI response logs warning

**Requirement:** 21-REQ-2.E3
**Type:** unit
**Description:** Verify malformed AI response is handled gracefully.

**Preconditions:**
- Mock AI response returns invalid JSON: `"not valid json {{}"`

**Input:**
- `validate_dependency_interfaces("01_core", design_text, refs, model)`

**Expected:**
- Returns empty list.
- Warning logged.

**Assertion pseudocode:**
```
findings = await validate_dependency_interfaces(
    "01_core", design_text, [ref], model
)
ASSERT len(findings) == 0
```

---

### TS-21-11: Batch multiple rows to same upstream spec

**Requirement:** 21-REQ-3.1, 21-REQ-3.2
**Type:** unit
**Description:** Verify multiple dependency rows referencing the same
upstream spec produce a single AI call.

**Preconditions:**
- Two specs each have dependency rows referencing upstream spec `01_core`.
- Each row has different identifiers.

**Input:**
- `run_stale_dependency_validation(specs, specs_dir, model)`

**Expected:**
- AI client called exactly once (for `01_core`).
- All identifiers from both rows included in the single call.

**Assertion pseudocode:**
```
findings = await run_stale_dependency_validation(specs, specs_dir, model)
ASSERT mock_client.messages.create.call_count == 1
prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
ASSERT "Config" in prompt
ASSERT "Store" in prompt
```

---

### TS-21-12: No backtick tokens means zero AI calls

**Requirement:** 21-REQ-3.E1
**Type:** unit
**Description:** Verify no AI calls when no Relationship text has backticks.

**Preconditions:**
- All dependency rows have plain-text Relationship cells (no backticks).

**Input:**
- `run_stale_dependency_validation(specs, specs_dir, model)`

**Expected:**
- Returns empty list.
- AI client never called.

**Assertion pseudocode:**
```
findings = await run_stale_dependency_validation(specs, specs_dir, model)
ASSERT len(findings) == 0
ASSERT mock_client.messages.create.call_count == 0
```

---

### TS-21-13: Findings have correct severity and format

**Requirement:** 21-REQ-4.1, 21-REQ-4.2, 21-REQ-4.3
**Type:** unit
**Description:** Verify stale-dependency findings are Warning severity and
integrate with existing output.

**Preconditions:**
- Mock AI flags one identifier as not found.

**Input:**
- `run_ai_validation(specs, model, specs_dir)`

**Expected:**
- stale-dependency findings have severity="warning".
- Findings are sortable alongside other finding types.

**Assertion pseudocode:**
```
findings = await run_ai_validation(specs, model, specs_dir)
stale = [f for f in findings if f.rule == "stale-dependency"]
ASSERT all(f.severity == "warning" for f in stale)
# verify sort_findings() handles them
sorted_f = sort_findings(findings)
ASSERT sorted_f is not None
```

---

### TS-21-14: Multiple upstream specs produce separate AI calls

**Requirement:** 21-REQ-3.1
**Type:** unit
**Description:** Verify different upstream specs get separate AI calls.

**Preconditions:**
- Dependency rows reference two different upstream specs: `01_core` and
  `02_store`.

**Input:**
- `run_stale_dependency_validation(specs, specs_dir, model)`

**Expected:**
- AI client called exactly twice (once per upstream spec).

**Assertion pseudocode:**
```
findings = await run_stale_dependency_validation(specs, specs_dir, model)
ASSERT mock_client.messages.create.call_count == 2
```

---

### TS-21-15: Fix replaces stale identifier with AI suggestion

**Requirement:** 21-REQ-5.1, 21-REQ-5.2
**Type:** unit
**Description:** Verify fixer replaces the backtick-delimited identifier
in prd.md Relationship text with the AI-suggested correction.

**Preconditions:**
- A prd.md with Relationship text containing `\`SnippetStore\``.
- IdentifierFix(original="SnippetStore", suggestion="Store",
  upstream_spec="01_core").

**Input:**
- `fix_stale_dependency("my_spec", prd_path, [fix])`

**Expected:**
- prd.md now contains `\`Store\`` instead of `\`SnippetStore\``.
- Returns 1 FixResult with description mentioning the change.

**Assertion pseudocode:**
```
results = fix_stale_dependency("my_spec", prd_path, [fix])
ASSERT len(results) == 1
content = prd_path.read_text()
ASSERT "`Store`" in content
ASSERT "`SnippetStore`" not in content
ASSERT "SnippetStore" in results[0].description
ASSERT "Store" in results[0].description
```

---

### TS-21-16: Fix skips findings without suggestion

**Requirement:** 21-REQ-5.E1
**Type:** unit
**Description:** Verify fixer skips findings where AI provided no
suggestion.

**Preconditions:**
- A prd.md with Relationship text containing `\`SnippetStore\``.
- IdentifierFix(original="SnippetStore", suggestion="",
  upstream_spec="01_core").

**Input:**
- `fix_stale_dependency("my_spec", prd_path, [fix])`

**Expected:**
- Returns empty list.
- prd.md unchanged.

**Assertion pseudocode:**
```
content_before = prd_path.read_text()
results = fix_stale_dependency("my_spec", prd_path, [fix])
ASSERT len(results) == 0
ASSERT prd_path.read_text() == content_before
```

---

### TS-21-17: Fix skips when suggestion already present

**Requirement:** 21-REQ-5.E3
**Type:** unit
**Description:** Verify fixer does not duplicate text when the suggested
identifier already exists in the Relationship text.

**Preconditions:**
- A prd.md with Relationship text already containing `\`Store\``.
- IdentifierFix(original="SnippetStore", suggestion="Store",
  upstream_spec="01_core").
- But `\`SnippetStore\`` is no longer in the text (was already manually
  fixed).

**Input:**
- `fix_stale_dependency("my_spec", prd_path, [fix])`

**Expected:**
- Returns empty list.
- prd.md unchanged.

**Assertion pseudocode:**
```
content_before = prd_path.read_text()
results = fix_stale_dependency("my_spec", prd_path, [fix])
ASSERT len(results) == 0
ASSERT prd_path.read_text() == content_before
```

---

### TS-21-18: Fix preserves surrounding text

**Requirement:** 21-REQ-5.2
**Type:** unit
**Description:** Verify fixer only replaces the target identifier, leaving
all other content in the file intact.

**Preconditions:**
- A prd.md with Relationship text:
  `Uses \`SnippetStore\` for persistence and \`Config\` for settings`
- IdentifierFix(original="SnippetStore", suggestion="Store",
  upstream_spec="01_core").

**Input:**
- `fix_stale_dependency("my_spec", prd_path, [fix])`

**Expected:**
- Relationship text becomes:
  `Uses \`Store\` for persistence and \`Config\` for settings`
- `\`Config\`` is unchanged.

**Assertion pseudocode:**
```
results = fix_stale_dependency("my_spec", prd_path, [fix])
content = prd_path.read_text()
ASSERT "`Store`" in content
ASSERT "`Config`" in content
ASSERT "`SnippetStore`" not in content
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 21-REQ-1.1 | TS-21-1 | unit |
| 21-REQ-1.2 | TS-21-2 | unit |
| 21-REQ-1.3 | TS-21-3 | unit |
| 21-REQ-1.E1 | TS-21-4 | unit |
| 21-REQ-1.E2 | TS-21-5 | unit |
| 21-REQ-2.1 | TS-21-6 | unit |
| 21-REQ-2.2 | TS-21-8, TS-21-11 | unit |
| 21-REQ-2.3 | TS-21-6 | unit |
| 21-REQ-2.4 | TS-21-7 | unit |
| 21-REQ-2.5 | TS-21-7 | unit |
| 21-REQ-2.E1 | TS-21-8 | unit |
| 21-REQ-2.E2 | TS-21-9 | unit |
| 21-REQ-2.E3 | TS-21-10 | unit |
| 21-REQ-3.1 | TS-21-11, TS-21-14 | unit |
| 21-REQ-3.2 | TS-21-11 | unit |
| 21-REQ-3.E1 | TS-21-12 | unit |
| 21-REQ-4.1 | TS-21-13 | unit |
| 21-REQ-4.2 | TS-21-13 | unit |
| 21-REQ-4.3 | TS-21-13 | unit |
| 21-REQ-5.1 | TS-21-15 | unit |
| 21-REQ-5.2 | TS-21-15, TS-21-18 | unit |
| 21-REQ-5.3 | -- | integration |
| 21-REQ-5.4 | TS-21-15 | unit |
| 21-REQ-5.E1 | TS-21-16 | unit |
| 21-REQ-5.E2 | -- | integration |
| 21-REQ-5.E3 | TS-21-17 | unit |
