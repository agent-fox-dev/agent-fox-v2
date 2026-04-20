# Test Specification: Prompt Caching

## Overview

Tests validate cache policy configuration, the cached message helper's
marker injection logic, threshold gating, and auxiliary module migration.
All tests use mocked Anthropic clients — no real API calls.

## Test Cases

### TS-77-1: Default Cache Policy

**Requirement:** 77-REQ-1.2
**Type:** unit
**Description:** Verifies that omitting the `[caching]` section defaults
to `DEFAULT` policy.

**Preconditions:**
- No `[caching]` section in config dict.

**Input:**
- Empty dict passed to `AgentFoxConfig()`.

**Expected:**
- `config.caching.cache_policy` equals `CachePolicy.DEFAULT`.

**Assertion pseudocode:**
```
config = AgentFoxConfig()
ASSERT config.caching.cache_policy == CachePolicy.DEFAULT
```

---

### TS-77-2: Cache Policy Parsing

**Requirement:** 77-REQ-1.1
**Type:** unit
**Description:** Verifies that all three policy values are accepted
(case-insensitive).

**Preconditions:**
- None.

**Input:**
- Config dicts with `cache_policy` set to `"NONE"`, `"default"`,
  `"Extended"`.

**Expected:**
- Each parses to the corresponding `CachePolicy` enum member.

**Assertion pseudocode:**
```
FOR EACH (input_str, expected_enum) IN [
    ("NONE", CachePolicy.NONE),
    ("default", CachePolicy.DEFAULT),
    ("Extended", CachePolicy.EXTENDED),
]:
    config = CachingConfig(cache_policy=input_str)
    ASSERT config.cache_policy == expected_enum
```

---

### TS-77-3: NONE Policy Passthrough

**Requirement:** 77-REQ-1.3, 77-REQ-2.4, 77-REQ-5.1
**Type:** unit
**Description:** Verifies that NONE policy produces no `cache_control`
in the API request.

**Preconditions:**
- Mock Anthropic client that captures the kwargs passed to
  `messages.create()`.

**Input:**
- `cached_messages_create()` called with `cache_policy=NONE`,
  `system="You are a helpful assistant."`, model, max_tokens, messages.

**Expected:**
- The `system` kwarg passed to the underlying `messages.create()` is
  the plain string `"You are a helpful assistant."` (unchanged).
- No `cache_control` key appears anywhere in the request.

**Assertion pseudocode:**
```
client = MockAsyncAnthropic()
result = await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="You are a helpful assistant.",
    cache_policy=CachePolicy.NONE,
)
captured = client.last_call_kwargs
ASSERT captured["system"] == "You are a helpful assistant."
ASSERT "cache_control" NOT IN str(captured)
```

---

### TS-77-4: DEFAULT Policy Marker

**Requirement:** 77-REQ-1.4, 77-REQ-2.2
**Type:** unit
**Description:** Verifies that DEFAULT policy attaches 5-min ephemeral
`cache_control` to the last system block.

**Preconditions:**
- Mock client. System prompt long enough to exceed threshold.

**Input:**
- `cached_messages_create()` with `cache_policy=DEFAULT`,
  `system="x" * 20000` (well above threshold).

**Expected:**
- `system` kwarg is a list with one block containing
  `cache_control: {"type": "ephemeral"}`.

**Assertion pseudocode:**
```
client = MockAsyncAnthropic()
long_prompt = "x" * 20000
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system=long_prompt, cache_policy=CachePolicy.DEFAULT,
)
system_blocks = client.last_call_kwargs["system"]
ASSERT isinstance(system_blocks, list)
ASSERT system_blocks[-1]["cache_control"] == {"type": "ephemeral"}
```

---

### TS-77-5: EXTENDED Policy Marker

**Requirement:** 77-REQ-1.5
**Type:** unit
**Description:** Verifies that EXTENDED policy uses 1-hour TTL.

**Preconditions:**
- Mock client. System prompt above threshold.

**Input:**
- `cached_messages_create()` with `cache_policy=EXTENDED`,
  `system="x" * 20000`.

**Expected:**
- Last system block has `cache_control: {"type": "ephemeral", "ttl": "1h"}`.

**Assertion pseudocode:**
```
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="x" * 20000, cache_policy=CachePolicy.EXTENDED,
)
ASSERT client.last_call_kwargs["system"][-1]["cache_control"] == {
    "type": "ephemeral", "ttl": "1h"
}
```

---

### TS-77-6: Multi-Block System Prompt

**Requirement:** 77-REQ-2.2
**Type:** unit
**Description:** When system is a list of blocks, `cache_control` is
attached only to the last block.

**Preconditions:**
- Mock client.

**Input:**
- `system` as a list of two text blocks, total content above threshold.

**Expected:**
- First block has no `cache_control`. Last block has `cache_control`.

**Assertion pseudocode:**
```
system_blocks = [
    {"type": "text", "text": "a" * 10000},
    {"type": "text", "text": "b" * 10000},
]
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system=system_blocks, cache_policy=CachePolicy.DEFAULT,
)
result = client.last_call_kwargs["system"]
ASSERT "cache_control" NOT IN result[0]
ASSERT result[-1]["cache_control"] == {"type": "ephemeral"}
```

---

### TS-77-7: No System Parameter

**Requirement:** 77-REQ-2.3
**Type:** unit
**Description:** When no `system` parameter is provided, no
`cache_control` is added anywhere.

**Preconditions:**
- Mock client.

**Input:**
- `cached_messages_create()` called without `system` kwarg.

**Expected:**
- No `system` key in captured kwargs, or `system` is None.
- No `cache_control` in any message block.

**Assertion pseudocode:**
```
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    cache_policy=CachePolicy.DEFAULT,
)
ASSERT "system" NOT IN client.last_call_kwargs OR client.last_call_kwargs["system"] IS None
ASSERT "cache_control" NOT IN str(client.last_call_kwargs)
```

---

### TS-77-8: Auxiliary Module Uses Helper

**Requirement:** 77-REQ-3.1, 77-REQ-3.2
**Type:** unit
**Description:** Verifies that each auxiliary module imports and calls
`cached_messages_create` (or its sync variant) instead of raw
`client.messages.create()`.

**Preconditions:**
- Source files for all 9 auxiliary modules.

**Input:**
- Read source of each module.

**Expected:**
- No direct `client.messages.create()` calls remain.
- Each module imports `cached_messages_create` or
  `cached_messages_create_sync` from `agent_fox.core.client`.

**Assertion pseudocode:**
```
FOR EACH module_path IN AUXILIARY_MODULES:
    source = read_file(module_path)
    ASSERT "cached_messages_create" IN source
    ASSERT ".messages.create(" NOT IN source
```

---

### TS-77-9: Token Threshold Estimation

**Requirement:** 77-REQ-4.3
**Type:** unit
**Description:** Verifies the characters ÷ 4 heuristic.

**Preconditions:**
- None.

**Input:**
- Strings of length 0, 100, 8192, 16384.

**Expected:**
- Returns 0, 25, 2048, 4096 respectively.

**Assertion pseudocode:**
```
ASSERT _estimate_tokens("") == 0
ASSERT _estimate_tokens("x" * 100) == 25
ASSERT _estimate_tokens("x" * 8192) == 2048
ASSERT _estimate_tokens("x" * 16384) == 4096
```

---

### TS-77-10: Threshold Gating Skips Small Prompts

**Requirement:** 77-REQ-4.2
**Type:** unit
**Description:** System prompt below the model threshold should not get
`cache_control`.

**Preconditions:**
- Mock client. Short system prompt (e.g., 100 chars = ~25 tokens).

**Input:**
- `cached_messages_create()` with `system="short"`,
  `cache_policy=DEFAULT`, model `claude-sonnet-4-6` (threshold 2048).

**Expected:**
- `system` passed through as plain string, no `cache_control`.

**Assertion pseudocode:**
```
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="short prompt", cache_policy=CachePolicy.DEFAULT,
)
ASSERT client.last_call_kwargs["system"] == "short prompt"
```

## Edge Case Tests

### TS-77-E1: Invalid Cache Policy Value

**Requirement:** 77-REQ-1.E1
**Type:** unit
**Description:** Unrecognized policy value raises validation error.

**Preconditions:**
- None.

**Input:**
- `CachingConfig(cache_policy="AGGRESSIVE")`.

**Expected:**
- Raises `ValidationError`.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    CachingConfig(cache_policy="AGGRESSIVE")
```

---

### TS-77-E2: String System Prompt Conversion

**Requirement:** 77-REQ-2.E1
**Type:** unit
**Description:** Plain string system prompt is converted to content-block
list when caching is active.

**Preconditions:**
- Mock client. String long enough to exceed threshold.

**Input:**
- `system="x" * 20000`, `cache_policy=DEFAULT`.

**Expected:**
- Captured `system` is a list of one dict with keys `type`, `text`,
  `cache_control`.

**Assertion pseudocode:**
```
await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="x" * 20000, cache_policy=CachePolicy.DEFAULT,
)
blocks = client.last_call_kwargs["system"]
ASSERT isinstance(blocks, list)
ASSERT len(blocks) == 1
ASSERT blocks[0]["type"] == "text"
ASSERT blocks[0]["text"] == "x" * 20000
ASSERT blocks[0]["cache_control"] == {"type": "ephemeral"}
```

---

### TS-77-E3: Cache Control API Error Retry

**Requirement:** 77-REQ-2.E2
**Type:** unit
**Description:** On API error mentioning `cache_control`, the helper
retries without caching.

**Preconditions:**
- Mock client that raises `BadRequestError` with message containing
  "cache_control" on first call, succeeds on second.

**Input:**
- `cached_messages_create()` with `cache_policy=DEFAULT`.

**Expected:**
- Helper retries. Second call has no `cache_control`. Returns
  successful response.

**Assertion pseudocode:**
```
client = MockAsyncAnthropic(
    fail_first_with=BadRequestError("invalid cache_control")
)
result = await cached_messages_create(
    client, model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="x" * 20000, cache_policy=CachePolicy.DEFAULT,
)
ASSERT client.call_count == 2
ASSERT "cache_control" NOT IN str(client.last_call_kwargs)
ASSERT result IS NOT None
```

---

### TS-77-E4: Unknown Model Uses Default Threshold

**Requirement:** 77-REQ-4.E1
**Type:** unit
**Description:** Unrecognized model ID uses highest threshold (4096).

**Preconditions:**
- Mock client.

**Input:**
- `model="claude-unknown-99"`, system prompt of ~12000 chars
  (3000 estimated tokens — below 4096 default threshold).

**Expected:**
- No `cache_control` added (3000 < 4096).

**Assertion pseudocode:**
```
await cached_messages_create(
    client, model="claude-unknown-99", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
    system="x" * 12000, cache_policy=CachePolicy.DEFAULT,
)
ASSERT client.last_call_kwargs["system"] == "x" * 12000
```

## Property Test Cases

### TS-77-P1: Policy Fidelity

**Property:** Property 1 from design.md
**Validates:** 77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5, 77-REQ-2.2, 77-REQ-2.4
**Type:** property
**Description:** For any policy and sufficiently large system prompt, the
correct cache_control marker (or none) is attached.

**For any:** `policy` drawn from `CachePolicy` enum; `system_text` drawn
from `text(min_size=20000)` (above all thresholds).
**Invariant:** The `cache_control` value on the last system block matches
the policy's expected marker, or is absent for NONE.

**Assertion pseudocode:**
```
FOR ANY policy IN CachePolicy, system_text IN text(min_size=20000):
    client = MockAsyncAnthropic()
    await cached_messages_create(
        client, model="claude-sonnet-4-6", max_tokens=1024,
        messages=[{"role": "user", "content": "hi"}],
        system=system_text, cache_policy=policy,
    )
    IF policy == NONE:
        ASSERT "cache_control" NOT IN str(client.last_call_kwargs)
    ELIF policy == DEFAULT:
        ASSERT last_block(client)["cache_control"] == {"type": "ephemeral"}
    ELIF policy == EXTENDED:
        ASSERT last_block(client)["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
```

---

### TS-77-P2: String-to-Block Normalization

**Property:** Property 2 from design.md
**Validates:** 77-REQ-2.E1
**Type:** property
**Description:** Any string system prompt is normalized to a content-block
list when caching is active and above threshold.

**For any:** `system_text` drawn from `text(min_size=20000)`;
`policy` drawn from `{DEFAULT, EXTENDED}`.
**Invariant:** `system` kwarg is a list of dicts, each with `type` and
`text` keys.

**Assertion pseudocode:**
```
FOR ANY system_text IN text(min_size=20000), policy IN {DEFAULT, EXTENDED}:
    client = MockAsyncAnthropic()
    await cached_messages_create(
        client, model="claude-sonnet-4-6", max_tokens=1024,
        messages=[{"role": "user", "content": "hi"}],
        system=system_text, cache_policy=policy,
    )
    blocks = client.last_call_kwargs["system"]
    ASSERT isinstance(blocks, list)
    ASSERT ALL(b["type"] == "text" FOR b IN blocks)
```

---

### TS-77-P3: Threshold Gate

**Property:** Property 3 from design.md
**Validates:** 77-REQ-4.1, 77-REQ-4.2, 77-REQ-4.3
**Type:** property
**Description:** System prompts below the model's token threshold never
receive `cache_control`.

**For any:** `n` drawn from `integers(1, 8000)` (char count);
`model` drawn from known models; `policy` drawn from `{DEFAULT, EXTENDED}`.
**Invariant:** If `n // 4 < threshold(model)`, no `cache_control` appears.

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 8000), model IN KNOWN_MODELS, policy IN {DEFAULT, EXTENDED}:
    client = MockAsyncAnthropic()
    system_text = "x" * n
    await cached_messages_create(
        client, model=model, max_tokens=1024,
        messages=[{"role": "user", "content": "hi"}],
        system=system_text, cache_policy=policy,
    )
    threshold = THRESHOLDS.get(model, 4096)
    IF n // 4 < threshold:
        ASSERT "cache_control" NOT IN str(client.last_call_kwargs)
```

---

### TS-77-P4: NONE-Policy Passthrough

**Property:** Property 4 from design.md
**Validates:** 77-REQ-2.4, 77-REQ-5.1
**Type:** property
**Description:** NONE policy never modifies the system prompt.

**For any:** `system_text` drawn from `text(min_size=1)`.
**Invariant:** `system` kwarg equals the original string (unchanged).

**Assertion pseudocode:**
```
FOR ANY system_text IN text(min_size=1):
    client = MockAsyncAnthropic()
    await cached_messages_create(
        client, model="claude-sonnet-4-6", max_tokens=1024,
        messages=[{"role": "user", "content": "hi"}],
        system=system_text, cache_policy=CachePolicy.NONE,
    )
    ASSERT client.last_call_kwargs["system"] == system_text
```

## Coverage Matrix

| Requirement   | Test Spec Entry | Type     |
|---------------|-----------------|----------|
| 77-REQ-1.1    | TS-77-2         | unit     |
| 77-REQ-1.2    | TS-77-1         | unit     |
| 77-REQ-1.3    | TS-77-3, TS-77-P1 | unit, property |
| 77-REQ-1.4    | TS-77-4, TS-77-P1 | unit, property |
| 77-REQ-1.5    | TS-77-5, TS-77-P1 | unit, property |
| 77-REQ-1.E1   | TS-77-E1        | unit     |
| 77-REQ-2.1    | TS-77-4         | unit     |
| 77-REQ-2.2    | TS-77-4, TS-77-6, TS-77-P1 | unit, property |
| 77-REQ-2.3    | TS-77-7         | unit     |
| 77-REQ-2.4    | TS-77-3, TS-77-P4 | unit, property |
| 77-REQ-2.E1   | TS-77-E2, TS-77-P2 | unit, property |
| 77-REQ-2.E2   | TS-77-E3        | unit     |
| 77-REQ-3.1    | TS-77-8         | unit     |
| 77-REQ-3.2    | TS-77-8         | unit     |
| 77-REQ-3.3    | TS-77-8         | unit     |
| 77-REQ-3.E1   | TS-77-7         | unit     |
| 77-REQ-4.1    | TS-77-P3        | property |
| 77-REQ-4.2    | TS-77-10, TS-77-P3 | unit, property |
| 77-REQ-4.3    | TS-77-9, TS-77-P3 | unit, property |
| 77-REQ-4.E1   | TS-77-E4        | unit     |
| 77-REQ-5.1    | TS-77-3, TS-77-P4 | unit, property |
| 77-REQ-5.2    | (no change needed — existing tests cover) | — |
