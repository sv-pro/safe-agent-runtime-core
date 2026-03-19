# safe-agent-runtime-core

Minimal ontology runtime with construction-time validation and a subprocess execution boundary.

---

## The Core Idea

Most agent safety systems sit between intent and execution — they check a request and decide "allow" or "deny". This repo does something structurally different: **it defines the set of actions that can exist, then makes anything outside that set unconstructible.**

There is no raw execution path. Every action goes through a typed IR (`IntentIR`). That IR can only be produced by `IRBuilder.build()`, which validates all constraints at construction time. If `build()` returns an object, the action is valid. If it raises, the action is not possible — not denied, not blocked, not possible.

Execution is separated from policy: the main process does validation and decision. A worker subprocess does execution. The main process holds no callable handlers.

---

## What This Repo Demonstrates

- **Unknown actions cannot be constructed.** An action not in `world_manifest.yaml` raises `ConstructionError` at `IRBuilder.build()`. The worker is never invoked.
- **Tainted data cannot cross an external boundary.** If a prior output is tainted and the next action is `EXTERNAL`, IR construction fails. The subprocess never receives the request.
- **Execution happens only via subprocess worker.** The main process holds no handler functions. `Executor` is a transport-only facade that serializes an `ExecutionSpec` and sends it to `worker.py` via stdin/stdout.
- **Runtime is deterministic.** Same input → same policy decision. No LLM in the execution path.
- **Taint cannot be dropped by casual omission.** `IRBuilder.build()` requires a `TaintContext` argument (not variadic). Dropping taint requires explicitly writing `TaintContext.clean()` — a visible, auditable act.

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

## Key Properties

### Ontological absence
Actions not declared in `world_manifest.yaml` do not exist in the runtime. Attempting to construct IR for an unknown action raises `ConstructionError` before any execution path is entered — not a runtime denial, a construction failure.

### Deterministic validation
`CompiledPolicy` is frozen at startup: `MappingProxyType` action registry, `frozenset` capability matrix, `tuple` taint rules. Capability checks are O(1) frozenset membership. No dynamic rule evaluation at request time.

### Taint containment
`TAINTED` + `EXTERNAL` → `ConstructionError`. Taint is derived from prior `TaintedValue` outputs via `TaintContext`, which is a required (non-variadic) argument to `build()`. Taint is monotonic: once introduced, it does not decrease.

### Process boundary
The main process cannot invoke action handlers directly — there are none. `Executor` spawns a subprocess for each execution, sends a serialized spec, and reads a JSON response. The worker has its own closed registry; unknown action names fail there too.

---

## Quick Start

```bash
pip install pyyaml
python demo.py
pytest
```

**What you should see:**

- Demo 1: `ConstructionError` for `delete_repository` — not in the ontology, worker never called.
- Demo 2: `ConstructionError` for tainted data into `post_webhook` (external) — taint rule fires at IR construction.
- Demo 3: `[worker] executed read_data` — execution crossed the subprocess boundary.

---

## Example Output

```
============================================================
DEMO 1 — Unknown action (ontological absence)
Attempting to construct IR for: delete_repository
------------------------------------------------------------
ConstructionError : Action 'delete_repository' does not exist in the compiled policy — undefined actions are impossible, not denied
Result            : action does not exist — IR cannot be formed, worker not called

============================================================
DEMO 2 — Taint containment
trusted source, tainted data → external action (post_webhook)
------------------------------------------------------------
ConstructionError : Taint rule violation: Tainted data cannot flow into external actions — IR construction blocked
Result            : taint blocks external boundary — worker not called

============================================================
DEMO 3 — Allowed internal action (crosses subprocess boundary)
trusted source, clean context → internal action (read_data)
------------------------------------------------------------
[worker] executed read_data
IR taint   : clean
Result     : TaintedValue(taint='clean', value={'data': 'sales Q1', 'source': 'db'})
```

`[worker] executed read_data` is printed by `worker.py` to stderr. It proves execution happened in a different process.

---

## What This Is NOT

- **Not a full sandbox.** The subprocess is a plain Python process — no OS-level isolation, no seccomp, no namespaces.
- **Not OS-level isolation.** The worker inherits the parent's filesystem, environment, and network access.
- **Not production-ready security.** This is a runtime model, not a hardened deployment.
- **Not a generic policy engine.** There is no rule language, no deny list, no middleware stack. The world is defined by the manifest; everything else is unconstructible.

---

## Limitations

- Worker is a local subprocess — no container, seccomp, or namespace isolation
- World manifest is static at startup; no dynamic action registration
- No provenance tracking (who requested what, audit log)
- No approval workflow — `approval_required: true` actions currently fail at construction (deferred, honestly documented)
- Taint is binary (clean/tainted); no taint labels or flow tracking
- No signing or integrity verification of worker artifacts

---

## Where This Can Go

- Replace subprocess with a container or gVisor-isolated worker
- Sign worker artifacts; verify before execution
- Richer taint model (labeled taint, flow tracking, provenance)
- Dynamic world shaping per session (per-agent manifest slices)
- Approval token path for `approval_required` actions

---

## File Structure

| File | Role |
|---|---|
| `world_manifest.yaml` | Declares actions, trust, capabilities, taint rules |
| `compile.py` | Compiles manifest into frozen `CompiledPolicy` at startup |
| `channel.py` | `Channel` + sealed `Source` — trust from compiled map, not caller-supplied |
| `models.py` | Primitive enums: `TaintState`, `ActionType`, `TrustLevel`, `ConstructionError` |
| `taint.py` | `TaintedValue[T]`, `TaintContext` — structural taint propagation |
| `ir.py` | Sealed `IntentIR` + `IRBuilder` — all constraint checking at construction |
| `executor.py` | `Executor` — subprocess transport facade, no handlers |
| `worker.py` | Standalone subprocess; owns all handlers; closed registry |
| `runtime.py` | `build_runtime()` — wires everything together |
| `demo.py` | Three scenarios: unknown action, taint block, subprocess execution |

---

## Requirements

Python 3.10+, PyYAML 6.0+
