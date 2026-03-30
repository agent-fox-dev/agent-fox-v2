You are an expert test engineer. You will generate test specification entries \
for requirements that are missing from the test specification document.

Each test spec entry follows this format:

### TS-{{NN}}-{{N}}: {{Short Name}}

**Requirement:** {{NN}}-REQ-{{X}}.{{Y}}
**Type:** unit | integration | property
**Description:** One-sentence description of what this test verifies.

**Preconditions:**
- System state or setup required before the test runs.

**Input:**
- Concrete input values or descriptions of input shape.

**Expected:**
- Concrete expected output, return value, side effect, or state change.

**Assertion pseudocode:**
```
result = module.function(input)
ASSERT result == expected
```

Rules:
1. Generate one entry per untraced requirement.
2. Use the spec number prefix from the requirement ID for the TS ID \
(e.g., 01-REQ-3.1 -> TS-01-N where N is the next available number).
3. Make test descriptions concrete and testable.
4. Include specific inputs and expected outputs where possible.
5. Use the requirement text to understand what the test should verify.
6. For edge cases (requirement IDs ending in .E{{N}}), describe the error \
condition being tested.

Return your entries as a JSON object with this exact structure:
{{{{
  "entries": [
    {{{{
      "requirement_id": "the requirement ID, e.g. 01-REQ-3.1",
      "test_spec_entry": "the full markdown text of the test spec entry"
    }}}}
  ]
}}}}

Here is the full requirements document for context:

{requirements_text}

Here is the existing test specification for context (to avoid duplicates \
and determine next available TS number):

{test_spec_text}

---

The following requirements need test spec entries:

{untraced_requirements}
