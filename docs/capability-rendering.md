# Capability Rendering

A precise account of what capability rendering is, why it differs from filtering, and what it means for agent security.

---

## The core concept

Every agent execution environment has an ambient capability: the full set of actions its tools, APIs, and handlers can perform. Call this the **raw tool surface** — everything the environment could do if nothing constrained it.

**Capability rendering** is the process of constructing a constrained execution surface from that ambient capability. The rendered surface is not a filtered view of raw tools. It is a purpose-built surface — the manifest declares what exists, the compiled policy fixes the capability matrix, and the source identity determines which subset of the manifest is reachable. Actions outside the rendered surface were never present in it.

---

## Raw tools vs. rendered capabilities

| Concept | Definition |
|---|---|
| **Raw tools** | Ambient capability — every action the environment could expose; the full set of registerable operations |
| **Rendered capabilities** | The constrained execution surface for a specific source identity — what the agent can actually reach |

The manifest is the boundary between these two concepts. It declares a subset of raw tools as the intended world. Everything outside the manifest remains ambient capability — the environment could expose it, but the runtime does not.

The compiled capability matrix then renders a further subset of the manifest for each trust level. A `TRUSTED` identity reaches `{internal, external}` action types. An `UNTRUSTED` identity reaches `{internal}` only. The rendered surface for each identity contains only the actions at the intersection of the manifest and its trust-level capability.

---

## How the manifest produces a rendered surface

```
world_manifest.yaml
┌─────────────────────────────────────────────┐
│  actions:                                   │
│    read_data:       { type: internal }      │  ← declared in world
│    send_email:      { type: external }      │  ← declared in world
│    post_webhook:    { type: external }      │  ← declared in world
│    delete_database: (absent)                │  ← not in manifest
│                                             │
│  capabilities:                              │
│    trusted:   [internal, external]          │
│    untrusted: [internal]                    │
└─────────────────────────────────────────────┘
         │
         ▼
  compile_world()  →  CompiledPolicy (frozen)
         │
         ├─ identity: "user"  →  TRUSTED
         │       rendered surface: { read_data, send_email, post_webhook }
         │
         └─ identity: "external"  →  UNTRUSTED
                 rendered surface: { read_data }
```

`delete_database` is not in the manifest. It is not in any rendered surface. An agent cannot request it, name it, or construct an `IntentIR` for it. `IRBuilder.build("delete_database", ...)` raises `NonExistentAction` — not because a deny rule fired, but because the action does not exist in the compiled policy.

`send_email` is in the manifest but absent from the `UNTRUSTED` rendered surface. An `external` identity attempting to build an IR for `send_email` also raises `NonExistentAction`, for the same structural reason: the action is not representable from that identity's rendered surface.

---

## This is not filtering

A filtering architecture:

1. Receives a formed request
2. Looks up the action in a policy store
3. Evaluates allow/deny rules
4. Returns the result

The action exists as a request object at step 1. Filtering decides what to do with it.

Capability rendering:

1. Compiles the manifest into a frozen capability matrix at startup
2. Resolves source identity to trust level at channel creation
3. Constructs the rendered surface — the set of actions representable for this identity
4. `IRBuilder.build()` succeeds only if the named action is in the rendered surface

The action either exists in the rendered surface or it does not. No evaluation step occurs. No policy is consulted at request time. There is no request to evaluate if the action is absent.

**The distinction matters for reasoning about agent behavior.** A filtering system asks: "what will this agent be allowed to do?" A rendering system asks: "what can this agent do?" The answer to the second question is smaller and structurally enforced.

---

## Attack surface reduction

The attack surface of a filtering system includes every action the system knows about — the deny layer stands between the agent and all of them. Gaps in deny logic, misconfigurations, or edge cases in policy evaluation can expose actions that should be unreachable.

The attack surface of a rendering system is the rendered surface. Actions outside the rendered surface are structurally unreachable:

- They cannot be named in a valid `IntentIR`
- They produce no execution object that policy could mishandle
- They are not present as objects in the runtime's compiled state

Reducing the manifest reduces the rendered surface. Reducing the capability matrix reduces what each trust level can reach. Both reductions are structural — they shrink what the agent can do, not just what it is allowed to do.

---

## Forbidden actions are absent, not denied

This is the precise claim:

> An action not in the rendered surface is **absent** from the execution environment for that identity. It is not **denied** — denial implies an object that was evaluated and rejected. Absent means no object exists to evaluate.

The distinction is visible in `IRBuilder.build()`:

- `NonExistentAction` — action name not in the compiled policy for this identity. This is absence. No evaluation occurred.
- `ConstraintViolation` — action is in the rendered surface, but this source's trust level cannot reach it in this context. This is a policy constraint on a present action.
- `TaintViolation` — action is in the rendered surface, but tainted data cannot flow into it. This is a taint rule applied to a present action.

`NonExistentAction` is the rendering outcome. `ConstraintViolation` and `TaintViolation` are policy outcomes. Both are raised at `IRBuilder.build()`, before any execution occurs, but they represent different things.

---

## Rendering and taint

Taint propagation operates on the rendered surface, not on raw tools. A `TaintViolation` means: tainted data cannot flow into this action — and the action is in the rendered surface, so the taint rule fires.

If the action were absent, there would be no taint rule to fire. `NonExistentAction` would be raised first. Taint and rendering are independent mechanisms that both enforce at construction time.

---

## Terminology summary

| Term | Definition in this system |
|---|---|
| **Raw tools** | Ambient capability — full set of actions the environment could expose |
| **World manifest** | Declared subset of raw tools; the intended ontology |
| **CompiledPolicy** | Frozen capability matrix derived from the manifest at startup |
| **Rendered capability surface** | Actions representable as `IntentIR` for a specific source identity |
| **Absent** | Not in the rendered surface; raises `NonExistentAction` at `IRBuilder.build()` |
| **Capability rendering** | The process of constructing the rendered surface from manifest + source identity |
| **Filtering** | Evaluation of a formed request against policy; a different architectural model |
