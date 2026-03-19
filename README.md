# safe-agent-runtime-core

> A minimal deterministic runtime that makes unsafe actions structurally impossible.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What this is

Most agent safety systems filter actions at execution time — the action is formed as a request, a policy intercepts it, a decision is made. This repo takes a different approach: **actions not declared in the manifest cannot be constructed at all.**

There is no execution path for an unknown action. Everything goes through a typed IR (`IntentIR`). That IR is only produced by `IRBuilder.build()`, which validates all constraints at construction time. If `build()` returns, the action is valid. If it raises, the action does not exist in this world — not denied, not blocked, impossible.

Execution is separated from policy via a subprocess boundary. The main process does validation. A worker subprocess does execution. The main process holds no callable handlers.

---

## How this differs from guardrails

| Approach | When safety fires | What is prevented |
|---|---|---|
| Guardrails / policy engines | After action is formed | Execution of disallowed actions |
| This runtime | At IR construction | Formation of disallowed actions |

With guardrails: the action exists as a request, a policy intercepts it, and the system denies execution.

With this runtime: an undefined action cannot become a request. There is no object to intercept. The construction fails.

Taint works the same way. Tainted data flowing into an external action does not reach a policy check — `IRBuilder.build()` raises before the `ExecutionSpec` is created.

---

## LLM-in-the-loop demo

```bash
python demo_llm.py
```

The LLM only proposes tool calls — it turns natural language into a structured
`ToolRequest`. The `SafeMCPProxy` and ontology runtime are the enforcement point:
unsafe proposals are rejected at IR construction time and never reach the worker
subprocess. A real provider can be swapped in via `OPENAI_API_KEY`, but the
default path is deterministic and runs offline.

## Safe MCP Proxy demo

```bash
python demo_proxy.py
```

A thin proxy layer sits between an agent/LLM client and tool execution,
enforcing the ontology runtime before any tool call reaches execution.
All three demo scenarios — unknown tool, tainted external call, clean
internal call — demonstrate that the proxy is not advisory: it is the
only route. There is no side door to tool execution.

This is not a full MCP implementation. It demonstrates the enforcement shape:
agent request → proxy validation → runtime construction → worker subprocess.

---

## 60-second quickstart

```bash
pip install pyyaml
python demo.py
python demo_proxy.py
python demo_llm.py
pytest
```

**What you should see:**

- Demo 1: `ConstructionError` for `delete_repository` — not in the ontology, worker never called
- Demo 2: `ConstructionError` for tainted data into `post_webhook` (external) — taint rule fires at IR construction
- Demo 3: `[worker] executed read_data` — execution crossed the subprocess boundary

---

## Example output

```
============================================================
DEMO 1 — Unknown action (ontological absence)
Attempting to construct IR for: delete_repository
------------------------------------------------------------
ConstructionError : ConstructionError: Action 'delete_repository' does not exist in the compiled policy — undefined actions are impossible, not denied
Result            : action does not exist — IR cannot be formed, worker not called

============================================================
DEMO 2 — Taint containment
trusted source, tainted data → external action (post_webhook)
------------------------------------------------------------
ConstructionError : ConstructionError: Taint rule violation: Tainted data cannot flow into external actions — IR construction blocked — IR cannot be formed
Result            : taint blocks external boundary — worker not called

============================================================
DEMO 3 — Allowed internal action (crosses subprocess boundary)
trusted source, clean context → internal action (read_data)
→ worker subprocess will announce execution on stderr
------------------------------------------------------------
[worker] executed read_data
IR taint   : clean
Result     : TaintedValue(taint='clean', value={'data': 'sales Q1', 'source': 'db'})
```

`[worker] executed read_data` is printed by `worker.py` to stderr. It proves execution happened in a different process.

---

## What this is NOT

- **Not a full sandbox.** The subprocess is a plain Python process — no OS-level isolation, no seccomp, no namespaces.
- **Not OS-level isolation.** The worker inherits the parent's filesystem, environment, and network access.
- **Not production-ready security.** This is a runtime model, not a hardened deployment.
- **Not a generic policy engine.** There is no rule language, deny list, or middleware stack. The world is defined by the manifest; everything outside it is unconstructible.

---

## Architecture

```
world_manifest.yaml
      │
      ▼
compile_world()  ──────────────────► CompiledPolicy (frozen metadata, no handlers)
      │                                    │
      ▼                                    ▼
   Channel                            IRBuilder
(trust from compiled map)       (construction-time checks:
      │                          ontology, capability, taint)
      ▼                                    │
    Source  ──────────────────────►  IntentIR
                                          │
                                          ▼
                                    Executor (transport only)
                                          │
                                     stdin/stdout
                                          │
                                          ▼
                                    worker.py subprocess
                                    (handlers live here)
                                          │
                                          ▼
                                    TaintedValue
```

**Main process:** policy, validation, IR construction. No handlers.
**Worker process:** execution only. No policy evaluation.

The only thing that crosses the subprocess boundary is an `ExecutionSpec` (action name + params). No handler functions, no policy objects, no taint metadata cross the wire.

---

## Key properties

**Ontological absence** — Actions not in `world_manifest.yaml` do not exist in the runtime. Attempting to construct IR raises `ConstructionError` before any execution path is entered — not a runtime denial, a construction failure.

**Deterministic validation** — `CompiledPolicy` is frozen at startup: `MappingProxyType` action registry, `frozenset` capability matrix, `tuple` taint rules. No dynamic rule evaluation at request time.

**Taint containment** — `TAINTED` + `EXTERNAL` → `ConstructionError`. Taint is derived from prior `TaintedValue` outputs via `TaintContext`, a required (non-variadic) argument to `build()`. Dropping taint requires explicitly calling `TaintContext.clean()`.

**Process boundary** — The main process holds no handler functions. `Executor` spawns a subprocess, sends a serialized spec, and reads a JSON response. The worker has its own closed registry; unknown action names fail there too.

---

## Repo structure

```
safe-agent-runtime-core/
├── world_manifest.yaml          # declares actions, trust, capabilities, taint rules
├── demo.py                      # three scenarios: unknown action, taint block, subprocess exec
├── demo_proxy.py                # proxy layer demo: unknown tool, tainted call, allowed call
├── demo_llm.py                  # LLM-in-the-loop demo: proposer → proxy → runtime → worker
├── runtime/
│   ├── models.py                # TaintState, ActionType, TrustLevel, ConstructionError
│   ├── compile.py               # manifest → frozen CompiledPolicy
│   ├── channel.py               # Channel + sealed Source (trust from policy, not caller)
│   ├── taint.py                 # TaintedValue[T], TaintContext
│   ├── ir.py                    # sealed IntentIR + IRBuilder (all checks at construction)
│   ├── executor.py              # subprocess transport — no handlers
│   ├── worker.py                # standalone subprocess; closed handler registry
│   ├── runtime.py               # build_runtime() — wires everything
│   ├── protocol.py              # ToolRequest / ProxyResponse (proxy surface types)
│   ├── proxy.py                 # SafeMCPProxy — in-path enforcement layer
│   └── llm_demo.py              # MockLLMProposer + optional OpenAIProposer
└── tests/
    ├── test_new_runtime.py      # core invariant tests
    ├── test_process_boundary.py # boundary property tests
    ├── test_proxy.py            # proxy layer tests
    └── test_llm_demo.py         # LLM demo invariant tests
```

---

## Limitations

- Worker is a local subprocess — no container, seccomp, or namespace isolation
- World manifest is static at startup; no dynamic action registration
- No audit log or provenance tracking
- `approval_required: true` actions currently fail at construction (honestly documented)
- Taint is binary (clean/tainted); no labeled taint or flow tracking

---

## Requirements

Python 3.10+, PyYAML 6.0+

For more on the design rationale: [docs/why-this-matters.md](docs/why-this-matters.md)
