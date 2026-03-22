# Architecture

## System Positioning

This system is an execution-layer runtime. It sits between an LLM and execution.

**Roles:**

- **LLM** — proposes actions (tool calls, steps, intents)
- **Runtime** — defines what actions exist; actions outside the manifest are unrepresentable
- **Engine** — enforces constraints deterministically at IR construction time, not at execution time

The LLM cannot propose an action the runtime has not declared. There is no object to evaluate, intercept, or deny — the action cannot be constructed.

**Execution flow:**

```
LLM
 ↓
Intent / Step
 ↓
World Manifest
 ↓
Rendered Capability Surface
 ↓
Enforcement Engine
 ↓
Execution
```

At **World Manifest**, the declared ontology determines what actions exist. At **Rendered Capability Surface**, the source identity and trust level determine which subset of those actions are reachable. At **Enforcement Engine** (`IRBuilder.build()`), taint rules and capability constraints are checked. If `build()` returns, all constraints are satisfied. If it raises, nothing proceeds.

---

## Key Distinction

**Guardrail systems** evaluate behavior: a request is formed, a policy examines it, and the system allows or denies.

**This system** defines possible behavior: a request that references an undeclared action cannot be formed. There is no evaluation step because there is no object to evaluate.

Two categories of restriction apply:

- **ABSENT** — the action is not in the capability surface. `IRBuilder.build()` raises `NonExistentAction`. No decision is made; the action is structurally unrepresentable.
- **POLICY** — the action exists but is constrained. `build()` raises `ConstraintViolation` (trust level insufficient) or `TaintViolation` (tainted context cannot reach this action type). The action is representable in principle; this source, in this context, cannot reach it.

These are not two names for the same thing. ABSENT means the action does not exist in the compiled policy. POLICY means the action exists but the current source or taint context fails a constraint. The distinction is visible in the exception type returned by `build()`.
