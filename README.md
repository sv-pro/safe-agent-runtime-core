# safe-agent-runtime-core

A deterministic policy kernel for agent execution pipelines.

This is not a product. It is a reusable runtime dependency — an execution
kernel and taint/provenance evaluation layer consumed by higher-level systems
such as `agent-world-compiler`. Import it, call `build_runtime()`, use the
returned `Runtime` object.

---

## What this system is

`safe-agent-runtime-core` is a **Safe MCP Proxy** — an **Agent Runtime Firewall**
that sits between an agent and its tools. It is not a guardrail. It is not a
filter. It is an execution environment: the only actions that can run are the
ones that can be constructed.

```
  Agent / LLM
      │
      ▼
┌─────────────────────────┐
│   Safe MCP Proxy        │  ← you are here
│   (IRBuilder + Sandbox) │
│   compiled policy       │
└─────────────────────────┘
      │
      ▼
  Tools / Executors
```

**Enforcement is by construction, not by interception:**

| Scenario | What happens |
|---|---|
| Agent requests an unsafe tool (e.g. `delete_database`) | `NonExistentAction` — the object does not exist; there is nothing to intercept |
| Agent requests a constrained tool (e.g. `send_email`) with tainted data | `TaintViolation` raised at `IRBuilder.build()` — execution never begins |
| Agent requests an allowed tool with clean data and sufficient trust | `IntentIR` produced; `Executor.execute()` called |

This means:

- **Unsafe tool → does not exist.** Actions absent from `world_manifest.yaml`
  are unrepresentable as `IntentIR`. The proxy has no deny rule for them — they
  simply have no corresponding object.
- **Constrained tool → enforced.** Actions present in the manifest are checked
  at construction time against trust level, taint state, and approval
  requirements. A constraint failure raises before any side effect occurs.

The runtime firewall boundary is the `IRBuilder.build()` call. Anything that
returns an `IntentIR` has already passed every constraint. Anything that raises
`ConstructionError` never touches an executor.

---

## What this kernel does

- **Deterministic policy evaluation**: Given a manifest, a source identity, and
  a taint context, `IRBuilder.build()` always produces the same decision. No
  randomness, no side effects, no external calls at decision time.

- **Construction-time enforcement**: All constraint checking happens at IR
  construction (`IRBuilder.build()`), not at execution time. If `build()`
  returns an `IntentIR`, every constraint has already been satisfied. If it
  raises, nothing executes.

- **Taint propagation**: `TaintedValue` wraps every executor result. `TaintContext`
  threads taint across pipeline stages. Taint is monotonic — it cannot decrease.
  TAINTED + EXTERNAL action = `TaintViolation` at construction time.

- **Capability enforcement**: Source identities resolve to trust levels via the
  compiled policy. Trust levels are checked against a `frozenset` capability
  matrix — O(1), no string comparison, no YAML re-parsing.

- **Ontological absence**: Actions not in `world_manifest.yaml` are
  unrepresentable. They cannot be expressed as `IntentIR`. There is no
  execution-time deny — there is no object to execute.

- **Manifest compilation**: `compile_world(path)` reads the manifest once at
  startup and returns a frozen `CompiledPolicy`. After that, no file I/O
  occurs on the decision path.

---

## What this kernel does NOT do

- No UI, no API server, no HTTP endpoints
- No LLM routing or prompt handling
- No workflow orchestration or task scheduling
- No dynamic action registration (manifest is static at startup)
- No audit logging (add this in the layer above)
- No OS-level isolation (no seccomp, containers, or namespaces)
- No approval token support yet (`ApprovalRequired` is raised; deferred)

---

## Terminology

| Term | Meaning in this kernel |
|---|---|
| **Action** | A named operation defined in the manifest |
| **Ontology** | The set of registered actions in the compiled policy |
| **Policy** | The compiled capability matrix + taint rules |
| **Trust level** | `TRUSTED` or `UNTRUSTED`, resolved from source identity |
| **Capability** | Whether a trust level may perform an action type |
| **Enforcement** | IR construction — constraints evaluated here, not at execution |
| **Decision** | The result of `IRBuilder.build()`: success (IntentIR) or typed error |
| **Taint** | `CLEAN` or `TAINTED`; monotonic, propagated through TaintContext |
| **Provenance** | Source identity carried in `Source`, derived by `Channel` |

---

## Denial reasons

When `IRBuilder.build()` raises, the exception type identifies the reason.
Catch the base `ConstructionError` if you don't need to distinguish; use the
typed subclasses when you do.

| Exception | Meaning |
|---|---|
| `NonExistentAction` | Action name not in the compiled policy (ontological absence) |
| `ConstraintViolation` | Source trust level cannot perform this action type |
| `TaintViolation` | Tainted context cannot flow into this action (taint rule fired) |
| `ApprovalRequired` | Action requires an approval token (not yet supported) |

All four are subclasses of `ConstructionError`.

---

## Quick start

```python
from runtime import build_runtime, TaintContext, TaintedValue
from runtime import NonExistentAction, TaintViolation, ConstraintViolation

# 1. Compile manifest once at startup
rt = build_runtime("world_manifest.yaml")

# 2. Resolve source identity to a trust-bearing channel
channel = rt.channel("user")   # trust level resolved from manifest
source = channel.source

# 3. Build IR — all constraints checked here
try:
    ir = rt.builder.build(
        action_name="read_data",
        source=source,
        params={"query": "hello"},
        taint_context=TaintContext.clean(),
    )
except NonExistentAction:
    ...  # action not registered
except ConstraintViolation:
    ...  # trust level insufficient
except TaintViolation:
    ...  # tainted data cannot reach this action

# 4. Execute — only reached if build() succeeded
result: TaintedValue = rt.sandbox.execute(ir)
print(result.value, result.taint)
```

### Taint propagation

```python
# Thread taint through a pipeline
step1 = rt.sandbox.execute(ir_step1)             # TaintedValue
ctx   = TaintContext.from_outputs(step1)          # carries step1's taint
ir2   = rt.builder.build("summarize", source, {}, ctx)
step2 = rt.sandbox.execute(ir2)                  # taint is monotonic: CLEAN v TAINTED = TAINTED
```

### Using the proxy

`SafeMCPProxy` is an in-path enforcement layer for callers that send tool
requests as dicts (e.g. MCP clients, LLM tool-call adapters). It maps tool
names to action names and delegates all constraint checking to `IRBuilder`.

```python
from runtime.proxy import SafeMCPProxy

proxy = SafeMCPProxy(rt)
response = proxy.handle({"tool": "read_data", "params": {}, "source": "user", "taint": False})
print(response.status)       # "ok" | "impossible" | "require_approval"
print(response.denial_kind)  # "non_existent_action" | "taint_violation" | ...
```

---

## Manifest format

```yaml
actions:
  read_data:       { type: internal }
  send_email:      { type: external }
  download_report: { type: internal, approval_required: true }
  post_webhook:    { type: external }

trust:
  user:     trusted
  system:   trusted
  external: untrusted

capabilities:
  trusted:   [internal, external]
  untrusted: [internal]

taint_rules:
  - taint: tainted
    action_type: external
    reason: "Tainted data cannot flow into external actions"
```

---

## API surface

The stable, importable API surface:

```
runtime.build_runtime(manifest_path) -> Runtime
runtime.compile_world(manifest_path) -> CompiledPolicy

Runtime.channel(identity: str) -> Channel
Runtime.builder -> IRBuilder
Runtime.sandbox  -> Executor
Runtime.policy   -> CompiledPolicy

IRBuilder.build(action_name, source, params, taint_context) -> IntentIR

Executor.execute(ir: IntentIR) -> TaintedValue

TaintContext.clean() -> TaintContext
TaintContext.from_outputs(*tvs: TaintedValue) -> TaintContext

TaintedValue.map(f) -> TaintedValue
TaintedValue.join(*tvs) -> TaintState

# Enumerations
TaintState.CLEAN / TAINTED
TrustLevel.TRUSTED / UNTRUSTED
ActionType.INTERNAL / EXTERNAL

# Errors
ConstructionError       (base)
  NonExistentAction
  ConstraintViolation
  TaintViolation
  ApprovalRequired
```

Keep the above stable. Higher-level systems (`agent-world-compiler`, etc.)
import from `runtime` and depend on this surface not changing shape.

---

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

Tests cover: construction-time enforcement, process boundary invariants,
proxy layer, taint propagation, determinism, and typed denial reasons.

---

## How other repos consume this

```toml
# In pyproject.toml of the consuming repo:
[project]
dependencies = [
    "safe-agent-runtime-core @ git+https://github.com/your-org/safe-agent-runtime-core",
]
```

```python
# In the consuming repo:
from runtime import build_runtime, TaintContext, ConstructionError
```

The consuming repo is responsible for: manifest authoring, LLM routing,
approval tokens, audit logging, orchestration, and UI. None of those belong
here.

---

## License

MIT
