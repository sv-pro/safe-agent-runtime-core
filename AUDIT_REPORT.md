# Architectural Audit Report — safe-agent-runtime-core

> **Audit date:** 2026-03-18
> **Auditor:** Claude (claude-sonnet-4-6)
> **Scope:** Deterministic execution model — "impossible vs. deny" principle

---

## Structured Report

```yaml
score:
  overall: 4
  determinism: 9
  ontological_enforcement: 4
  taint_model: 2
  execution_control: 1

verdict:
  - "partial implementation"
  - "actually a guardrail system"

critical_issues:
  - |
    DEAD CODE — Taint check at Step 4 is unreachable.
    The taint rule (`tainted = source == "external"; if tainted and action_type == "external"`)
    can NEVER fire. Before Step 4 is reached, Step 3 (capability check) already returns
    "impossible" for any external source attempting an external action, because:
      external source → untrusted trust level → allowed_types = ["internal"]
      "external" action type not in ["internal"] → return impossible at Step 3.
    Step 4 is dead code. The taint model appears implemented but is functionally void.
    Evidence: test_taint_containment_send_email asserts "not permitted" in reason — this
    string comes from Step 3, not Step 4. Step 4's message ("Tainted source cannot trigger
    external side-effects") is never reachable.

  - |
    NO EXECUTION BOUNDARY — evaluate() is advisory, not enforced.
    The system returns a decision string ("allow", "impossible", "require_approval").
    Nothing in the repository binds this decision to actual execution. An agent can call
    evaluate(), receive "impossible", and then execute the action directly. The runtime
    does not own execution — it is a policy consultant, not a constrained runtime.
    This is the defining characteristic of a guardrail system, not a safe-by-construction
    execution model.

  - |
    STRUCTURAL IMPOSSIBILITY IS NOT IMPLEMENTED — "impossible" is semantic, not structural.
    The tool_call dict can be constructed with ANY action name (e.g., "delete_repository",
    "launch_missile") and passed to evaluate(). The function processes the request, evaluates
    it, and returns "impossible". This IS handling an undefined action — the system receives
    and processes it. True structural impossibility would mean the action cannot be
    constructed at all (e.g., via an enum type, schema validation at ingestion, or a typed
    action registry that raises at parse time). The current implementation is a runtime
    filter that returns "impossible" — semantically equivalent to "deny".

architectural_violations:
  - |
    "Impossible" disguised as filtering: evaluate() accepts arbitrary dicts including
    undefined actions, processes them through a 5-step pipeline, and returns a decision.
    Undefined actions are handled (Step 1 returns "impossible"). Per the stated principles,
    "system attempts to handle unknown actions instead of failing construction" → FAIL.

  - |
    Taint model is decorative: The four-line taint block (runtime.py:61-66) is never
    exercised because the capability check subsumes it entirely. No test exists that
    isolates Step 4 from Step 3 — because no world configuration can reach Step 4 with
    the current trust/capability mapping.

  - |
    No execution binding: The boundary between decision and execution is absent.
    evaluate() is a pure function returning a string. The enforcement of that string
    depends entirely on the caller. This makes the system opt-in safety, not mandatory
    safety.

  - |
    Single hardcoded taint source: Taint is determined by `source == "external"` (a
    string literal, runtime.py:61). This is not configurable, not derived from the world
    definition, and is not data-level taint. Params are entirely ignored — tainted data
    arriving in params of an otherwise-allowed action is invisible to the system.

strengths:
  - Correct decision vocabulary: no "deny" or "block" values appear anywhere in the
    codebase. The vocabulary ("allow", "impossible", "require_approval") is coherent.
  - Fully deterministic: no LLM, no probabilistic logic, no randomization. Same input
    always produces same output. Score: 9/10 (only deduction: taint source is a magic
    string literal rather than derived from world.yaml).
  - World definition as single source of truth: world.yaml defines actions, trust levels,
    and capability mappings cleanly.
  - Unknown source defaults to untrusted (fail-secure default) — correct direction.
  - Explicit test that no "deny"/"block" decisions exist (test_no_deny_decision).
  - Minimal codebase — no accidental complexity or scope creep.

missing_components:
  - Execution enforcement layer: a component that actually invokes tools and is
    architecturally incapable of invoking a tool without a prior "allow" decision from
    evaluate(). Without this, the runtime is advisory only.
  - Structural action registry: a type-safe or schema-validated ingestion layer that
    rejects (at parse/construction time) any action not in the registry. Currently, any
    string is a valid action name in the tool_call dict.
  - Data-level taint propagation: params are passed through opaquely. Tainted data in
    params is invisible to the evaluator. A taint model that only tracks source identity
    (not data content) is incomplete.
  - Taint configuration in world.yaml: the taint rule is hardcoded in Python as
    `source == "external"`. It should be expressed in the world definition alongside
    trust and capability mappings so the world is the single authoritative source.
  - Reachability test for Step 4: no test (or world configuration) exercises the taint
    check independently of the capability check. The dead code path is not detected by
    the test suite.
  - Approval enforcement: "require_approval" is returned but there is no mechanism
    for receiving, validating, or recording that approval. The approval gate exists at
    the decision layer but has no implementation at the execution layer.

recommendations:
  - Fix the dead taint code: either (a) introduce a trusted-but-tainted source in
    world.yaml so Step 4 is reachable, or (b) remove the redundant Step 4 and move
    taint into the capability model explicitly. The current setup gives a false
    impression of a working taint system.
  - Implement an execution layer: a ToolExecutor class (or equivalent) that wraps all
    tool calls, calls evaluate() internally, and raises a hard exception (not returns
    an error string) if the decision is not "allow". Make bypass structurally impossible
    by ensuring tools are only callable through this executor.
  - Move taint definition into world.yaml: add a "tainted_sources" list so taint is
    part of the world definition, not a magic string in runtime.py:61.
  - Consider a typed ActionRequest class instead of a raw dict: this allows schema
    validation at construction time, moving unknown-action detection from runtime
    evaluation to parse time.
  - Add a test that explicitly reaches Step 4 (taint message, not capability message)
    to prove the taint check is live.

summary: |
  The system correctly articulates the "impossible vs. deny" philosophy and implements
  it with clean vocabulary and deterministic logic. However, it is architecturally a
  policy evaluator (guardrail/filter), not a constrained execution runtime. Two critical
  failures undermine the model: (1) the taint check at Step 4 is dead code — the
  capability check subsumes it entirely, making the taint model decorative; (2) evaluate()
  returns a string decision with no binding to actual execution — the agent can ignore
  the decision and act freely. Until an execution boundary is enforced structurally, this
  system cannot claim "unsafe actions are impossible"; it can only claim "unsafe actions
  are advised against".
```

---

## Detailed Analysis

### 1. "Impossible" vs "Deny" — PARTIAL PASS

The vocabulary is correct. No `"deny"` or `"block"` values appear in the decision output, and the test suite explicitly verifies this. The docstring correctly states the intent.

**However:** "impossible" is implemented as a runtime return value, not as structural impossibility. The engine receives and processes every request — including undefined ones — and returns a decision. Compare:

- **Claimed model:** undefined action → cannot be constructed
- **Actual model:** undefined action → processed by evaluate() → returns `"impossible"`

The distinction matters: the second is a filter with different output labels, not a world where the action cannot exist.

### 2. Ontological Enforcement — FAIL

`world.yaml` defines 4 actions. Any string can appear as `tool_call["action"]`. The engine receives it, enters the 5-step pipeline, and exits at Step 1 with `"impossible"`. This is action handling, not ontological absence.

**FAIL criterion met:** "system attempts to handle unknown actions instead of failing construction."

### 3. Determinism — PASS (9/10)

No LLM, no probabilistic logic, no dynamic rule generation. All decisions derive from static YAML configuration and deterministic Python conditionals. Minor deduction: the taint source (`"external"`) is a hardcoded string literal rather than a world-derived value, making it an out-of-band rule that could diverge from world.yaml.

### 4. Taint Model — FAIL (Dead Code)

**Execution trace for the canonical taint scenario:**

```
tool_call = {"action": "send_email", "source": "external", "params": {"to": "client"}}

Step 1: "send_email" in world["actions"]  → True, continue
Step 2: trust_map["external"] = "untrusted"
Step 3: capabilities["untrusted"] = ["internal"]
        "external" (action type) not in ["internal"] → RETURN IMPOSSIBLE
              reason: "Source 'external' (trust: untrusted) is not permitted
                       to perform actions of type 'external'"
Step 4: ← NEVER REACHED
```

The taint check at `runtime.py:61-66` requires:
- `source == "external"` (tainted = True), AND
- `action_type == "external"`

But for `source="external"` the trust level is `"untrusted"`, and `"untrusted"` capabilities are `["internal"]`. Step 3 will always catch external→external before Step 4 can.

For Step 4 to be reachable, a source would need to be simultaneously tainted (`source == "external"`) but trusted enough to reach Step 4 with an external action type. This combination cannot occur with the current world.yaml.

**Evidence from the test suite:** `test_taint_containment_send_email` asserts `"not permitted" in result["reason"]` — this is the Step 3 message. If Step 4 were reached, the message would be `"Tainted source cannot trigger external side-effects"`. The test inadvertently proves Step 4 is dead.

### 5. Capability Model — PARTIAL PASS

The capability mapping is correct and evaluated before "allow" is returned. Unknown sources default to untrusted (fail-secure). However, capabilities are enforced at evaluation time, not at construction time, and the enforcement is advisory (the caller must respect the decision).

### 6. Execution Boundary — FAIL

`evaluate()` is a pure function returning `{"decision": str, "reason": str}`. There is no:

- Tool executor that enforces the decision
- Mechanism preventing direct tool invocation
- Architectural constraint that makes bypass impossible

The system is a decision oracle. The agent consults it, then decides whether to comply. This is the definition of a guardrail system.

### 7. Architectural Smell — CONFIRMED: Guardrail System

The system exhibits all three degraded patterns:

| Pattern | Evidence |
|---|---|
| **Rule engine** | 5-step conditional pipeline evaluating a request against rules |
| **Guardrail/filter** | Returns decisions that the caller may or may not enforce |
| **Advisory system** | No execution binding; decisions are strings, not constraints |

The system does NOT exhibit the constrained-world model where unsafe actions cannot be constructed or invoked. It exhibits a policy evaluation model where unsafe actions are evaluated and labeled.

---

*End of audit.*
