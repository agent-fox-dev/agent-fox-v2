---
name: af-reverse-engineer
description: Reverse-engineer a Product Requirements Document (PRD) from an existing codebase.
---

# Reverse-Engineer PRD from Codebase

Act as a **senior Product Manager** who has just inherited a product with no
documentation. Your job is to figure out what this product *does for users*
and write a PRD that a new engineer or a business stakeholder could read to
understand the product — without ever looking at the code.

## Project Steering Directives

If `.specs/steering.md` exists in the project root, read it and follow any
directives it contains before proceeding. These project-level directives apply
to all agents and skills working on this project.

---

## The Prime Directive: WHAT, Never HOW

The single most important rule in this entire skill:

> **A PRD describes observable behavior from the user's perspective.
> It never describes implementation.**

Before writing any sentence, ask: *"Could a non-technical stakeholder
understand this without knowing anything about how it's built?"* If no —
rewrite it.

**Forbidden in PRDs:**
- Class names, function names, module names, file paths
- Database schema details, SQL, ORM patterns
- Algorithm descriptions ("uses BFS to traverse...", "sorts by...")
- Library or framework internals ("leverages React's context API...")
- Infrastructure details (queue names, container configs, memory limits)
- Code-level error types or exception names

**Allowed and encouraged:**
- What a user can do ("Users can filter results by date range")
- What the system does in response ("The system confirms the action and
  updates the view within 2 seconds")
- What happens under specific conditions ("When no results match, the user
  sees an empty state with a prompt to adjust their search")
- Acceptance criteria a QA engineer could test against the UI or API

---

## Step 1: Orient — Read for Intent, Not Implementation


Work through the repository in this order. Your goal at each step is to
answer *user and product questions*, not technical ones.

### Source of Truth: The Code Wins

**1. Explore the codebase:** run `ls`, read key source files, understand the
   module structure and how components interact.

**2. The code is the single source of truth.** Documentation (READMEs, wikis,
inline comments, commit messages, etc.) frequently diverges from what was
actually implemented. When documentation and code disagree, **the code is
always right**. Read the code in depth, understand how the system works. Don't skim.

**Important:** Only read files tracked by git. Skip anything matched by
`.gitignore`. When in doubt, run `git ls-files` to see what's tracked.

**3. README and any docs folder**
Extract: What problem does this solve? Who is it for? What does the
user/operator do to get value from it? Treat all claims as unverified until
confirmed against the code.

**4. Entry points and public interfaces**
Find the CLI commands, API routes, event handlers, or UI screens — anything
a user or integrating system directly invokes. List these as *capabilities*,
not function signatures. These are the skeleton of your Functional Requirements.

**5. Configuration surface**
What can an operator or user configure? What are the defaults? What values
are valid? This becomes your Configuration section — expressed as user-facing
options, not config struct fields.

**6. Tests**
Tests often describe *intent* more clearly than source. Look for:
- Happy-path scenarios (core workflows)
- Edge cases (boundary conditions the product handles)
- Error scenarios (what the product does when something goes wrong)
Read test descriptions and assertions, not the test mechanics.

**REMEMBER: Code is your evidence. It is not your vocabulary.**

---

## Step 2: Translate — Think Like a PM

Think about the following:

- **Who** is the target user?
- **What problem** does this tool solve for them?
- **What** are the key capabilities and user workflows?
- **What** are the inputs, outputs, and configuration options?
- **What** are the boundaries -- what does this tool intentionally *not* do?

Before writing a single line of the PRD, perform this translation exercise
mentally (or in a scratch note):

For every major thing you observed in the code, answer:

| Code observation | User-facing translation |
|---|---|
| `processPayment()` calls Stripe API | Users can pay with credit card; payments are processed in real time |
| `RetryQueue` with 3 attempts | Failed operations are automatically retried up to 3 times before the user is notified |
| `role: enum(admin, editor, viewer)` | Three access levels exist: Admin, Editor, and Viewer — each with distinct permissions |
| `ffmpeg` dependency | Video files can be transcoded to a standard web format upon upload |

**If you cannot complete the right column — the behavior isn't clear enough
to document yet. Mark it as an open question, not a guess.**

---

## Step 3: Write the PRD

Create `prd.md` using the structure below. Keep it concise. A tight 3-page
PRD is more valuable than a sprawling 10-page one.

```markdown
# Product Requirements Document
<!-- Version, Author, Date, Status -->

## 1. Product Overview

One paragraph. What is this product, who is it for, and what problem does it
solve? Focus on the user's world, not the system's internals.

## 2. Goals & Non-Goals

**Goals** — The outcomes this product exists to achieve. Express as user or
business outcomes, not technical milestones.
- ✅ [Goal]

**Non-Goals** — What is explicitly out of scope, and why this matters.
- 🚫 [Non-Goal] — [brief rationale]

## 3. User Personas

For each persona: who they are, what they're trying to accomplish, and what
would make the product succeed for them. Keep to 2–4 personas max. If only
one type of user exists, one is fine.

| Persona | Description | Primary Need |
|---|---|---|
| | | |

## 4. User Workflows

Describe the main end-to-end journeys a user takes. Use narrative steps from
the user's perspective. No system internals.

**Workflow: [Name]**
1. User does X
2. System responds with Y
3. User then does Z
4. Outcome: [what the user has accomplished]

Include the primary success path and the most important failure paths.

## 5. Functional Requirements

Organized by capability area. Use EARS syntax (see patterns below).
Each requirement must be independently testable.

**Capability Area: [Name]**
- [REQ-001] When [trigger], the system shall [behavior].
- [REQ-002] The system shall [behavior] [qualifier].
- [REQ-003] If [condition], the system shall [response].

EARS patterns:
- **Ubiquitous:** "The system shall [behavior]."
- **Event-driven:** "When [trigger], the system shall [behavior]."
- **Conditional:** "If [condition], the system shall [behavior]."
- **Optional:** "Where [feature is included], the system shall [behavior]."
- **Unwanted behavior:** "If [unwanted condition], the system shall [protection]."

❌ Do not write: "The system uses a background worker to process the queue"
✅ Write: "When a job is submitted, the system processes it asynchronously
   and notifies the user upon completion."

## 6. Configuration & Input Specification

What can users or operators configure? Expressed as named options with
plain-language descriptions — not code flags or environment variable dumps.

| Option | Description | Default | Valid Values |
|---|---|---|---|
| | | | |

## 7. Output Specification

What does the product produce? Describe format, structure, and naming from
the user's perspective. Include examples where helpful.

## 8. Error Handling & User Feedback

What does the user see or experience when things go wrong? Cover:
- Invalid input — what feedback is given
- External dependency failure — how gracefully it degrades
- Partial success — what state the user is left in
- Retry behavior — is it automatic or user-initiated

Express as user-observable behavior. Not exception types.

## 9. Constraints & Assumptions

Hard constraints the product operates within (platform requirements,
compliance boundaries, known limitations). Also document key assumptions
that, if wrong, would require revisiting requirements.

## 10. Open Questions

Behaviors that are unclear from the code, apparent inconsistencies, or
features partially implemented. Flag these honestly rather than guessing.

| # | Question | Why it matters |
|---|---|---|
| | | |

## 11. Future Considerations (Optional)

Patterns in the code suggesting planned-but-unfinished capabilities.
Describe them as product possibilities, not code stubs.
```

---

## Writing Guidelines

- **Audience:** Product stakeholder or new team member, not the original developer.
- **Abstraction:** Describe *what* and *why*, not *how*. Avoid referencing
  specific classes, functions, or variable names.
- **Tone:** Professional, concise. Prefer bullet points and tables over prose.
- **Accuracy:** Only document behavior verifiable from the code. If
  documentation claims a feature that the code doesn't support (or vice
  versa), trust the code and note the divergence as an open question.
- **Completeness:** Cover all user-facing capabilities.

## Quality Check Before Saving

Before finalizing `prd.md`, scan every sentence against these filters:

**The Stakeholder Test**
Read it aloud as if presenting to a VP of Product or a business stakeholder
with no engineering background. If any sentence would cause confusion — rewrite it.

**The Implementation Leak Test**
Search the document for: class names, file names, function names, library
names, SQL keywords, HTTP methods used as concepts (rather than interface
descriptions), and infrastructure terms. Remove or translate every hit.

**The Testability Test**
For every functional requirement: could a QA engineer write a test case
against this requirement using only the PRD? If not, it's either too vague
or too implementation-specific.

**The "So What" Test**
For every bullet point, ask: *why does this matter to a user?* If the
answer is "it doesn't — it's an internal detail" — delete it.
