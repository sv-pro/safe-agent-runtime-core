# Deterministic Ontology Runtime for Safe Agent Execution

## Problem

LLM agents call tools. In most systems:

- the model proposes an action as a string
- the runtime constructs a request
- a policy layer checks it and may deny execution

The action exists as an object before enforcement happens. Filtering occurs after construction.

This means unsafe actions are **representable**. The enforcement question is: will they be denied?

## Key Idea

Define a closed world of allowed actions in a manifest. Compile it once at startup into a frozen policy.

When an agent proposes an action:

1. A typed IR is constructed via `IRBuilder.build()`
2. Construction checks: does the action exist? does the source have capability? does taint allow it?
3. If any check fails, construction raises `ConstructionError` — no IR is produced
4. Only a valid, sealed `IntentIR` can be passed to the executor

Unsafe or undefined actions cannot be constructed. They have no representation in the runtime.

## What Is Different

- No "deny after construction" — invalid actions never become objects
- No string-based permission matching at execution time
- Enforcement is at construction, not execution
- Taint flows through a required `TaintContext` argument — cannot be dropped silently
- Trust is derived from policy at channel creation, not supplied by the caller
- The worker subprocess holds no policy — it only executes what arrives over the boundary

## Minimal Architecture

```
LLM → SafeMCPProxy → IRBuilder → Executor → Worker (subprocess)
           ↑                ↑
     ToolRequest      CompiledPolicy (frozen)
```

The proxy is the only entry point. `IRBuilder` enforces all constraints. `Executor` sends a minimal `ExecutionSpec` (action name + params only) to a subprocess. The worker has its own closed handler registry.

## What This Repo Shows

- **Construction-time impossibility**: undefined actions raise `ConstructionError` before any execution structure exists
- **Taint-aware validation**: tainted data flowing into external actions is blocked at IR construction
- **Subprocess execution boundary**: main process holds no callable handlers; only `ExecutionSpec` crosses the process boundary
- **Structural sealing**: `IntentIR`, `CompiledAction`, and `Source` objects cannot be forged — construction outside the runtime raises `TypeError`
- **LLM-in-the-loop demo**: model proposes, proxy enforces; three scenarios with deterministic outcomes

## What This Is Not

- Not a full agent framework
- Not an OS-level sandbox or seccomp boundary
- Not production-ready isolation
- Not a general policy engine

It is a demonstration of a specific property: **unsafe actions are impossible to construct**, not merely likely to be denied.
