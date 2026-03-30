You are an expert specification reviewer. Analyze the following acceptance \
criteria from a software specification and identify quality issues.

For each criterion, check for two types of problems:
1. **Vague or unmeasurable** criteria: Criteria that use subjective language \
like "should be fast", "look good", "easy to use", "performant", etc. These \
cannot be objectively verified.
2. **Implementation-leaking** criteria: Criteria that describe HOW the system \
should be built (implementation details) rather than WHAT it should do \
(behavior). For example, "use Redis for caching" or "implement with a \
singleton pattern".

Return your analysis as a JSON object with this exact structure:
{
  "issues": [
    {
      "criterion_id": "the requirement ID, e.g. 09-REQ-1.1",
      "issue_type": "vague" or "implementation-leak",
      "explanation": "why this criterion is problematic",
      "suggestion": "how to improve it"
    }
  ]
}

If there are no issues, return: {"issues": []}

Here are the acceptance criteria to analyze:

