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

## Capability Rendering

**Capability Rendering** is the process by which a world manifest and a source identity are combined to produce the rendered tool surface — the set of actions that are structurally representable for that identity.

### Definitions

- **Raw tools** — ambient capability: every action that the execution environment could expose. The full set of registerable, invocable operations before any identity-based constraint is applied.
- **Rendered capabilities** — the constrained execution surface produced for a specific source identity: the intersection of declared actions and what that identity's trust level permits.

### The rendering pipeline

```
Raw tools (environment capability)
        │
        ▼
world_manifest.yaml
  declares the intended ontology — a subset of raw tools
        │
        ▼
compile_world()  →  CompiledPolicy
  frozen capability matrix, compiled once at startup
        │
        ▼
channel(identity)  →  TrustLevel
  source identity resolved to TRUSTED or UNTRUSTED
        │
        ▼
capability matrix[trust_level] → {action_types}
  determines which action types this identity can reach
        │
        ▼
Rendered Capability Surface
  actions the agent can represent as IntentIR
```

### Agent visibility

The agent only sees the rendered surface. An action absent from the manifest is invisible: it cannot be named, constructed, or requested. An action present in the manifest but outside the agent's trust-level capability is equally invisible — it is not in the rendered surface for that identity.

This is not access control in the traditional sense. Access control maintains a list of resources and decides who may use each. Capability rendering constructs the list itself per identity. The agent does not receive a "denied" response for absent actions — there is no response because there is no request representable.

### Construction vs. filtering

| Property | Filtering | Capability Rendering |
|---|---|---|
| Decision point | Evaluation of a formed request | Construction of the request itself |
| Forbidden action | Exists as an object; policy denies it | Does not exist in the rendered surface |
| Bypass risk | Any gap in the deny logic | None: object cannot be constructed |
| Attack surface | All actions (filtered at runtime) | Rendered surface only |

Filtering says: "this request is denied." Capability rendering says: "this request cannot be formed."

---

## Key Distinction

**Guardrail systems** evaluate behavior: a request is formed, a policy examines it, and the system allows or denies.

**This system** defines possible behavior: a request that references an undeclared action cannot be formed. There is no evaluation step because there is no object to evaluate.

Two categories of restriction apply:

- **ABSENT** — the action is not in the capability surface. `IRBuilder.build()` raises `NonExistentAction`. No decision is made; the action is structurally unrepresentable.
- **POLICY** — the action exists but is constrained. `build()` raises `ConstraintViolation` (trust level insufficient) or `TaintViolation` (tainted context cannot reach this action type). The action is representable in principle; this source, in this context, cannot reach it.

These are not two names for the same thing. ABSENT means the action does not exist in the compiled policy. POLICY means the action exists but the current source or taint context fails a constraint. The distinction is visible in the exception type returned by `build()`.
