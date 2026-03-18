# safe-agent-runtime-core

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-43%20passing-brightgreen)

An ontological AI agent runtime that enforces safety constraints at **construction time** rather than execution time. Invalid action combinations cannot be represented as IR objects at all — they raise an error before any execution path is entered.

> **Core principle:** *Impossible instead of deny.*
> A constraint violation means the action cannot be built, not that it is blocked at runtime.

---

## Overview

Traditional agent runtimes check safety constraints during execution: a policy engine evaluates each action request and returns "allowed" or "denied". This approach has a fundamental weakness — there is always an execution path to bypass.

`safe-agent-runtime-core` takes a different approach: the **Intent IR** (intermediate representation) is a sealed object that can only be produced by `IRBuilder.build()`. All constraint checking happens at IR construction time. If `build()` returns, the IR is guaranteed valid. The sandbox executor has **zero policy checks** — it simply executes whatever IR it receives.

```
world_manifest.yaml
      │
      ▼
compile_world()  ──────────────────────► CompiledPolicy (frozen)
      │                                       │
      │              ┌────────────────────────┤
      │              │                        │
      ▼              ▼                        ▼
   Channel       IRBuilder               Sandbox
(trust from    (construction-time      (pure executor,
 compiled map)  constraint checks)      no checks)
      │              │                        │
      ▼              ▼                        ▼
    Source  ──►  IntentIR  ──────────►  TaintedValue
```

---

## Features

- **Construction-time validation** — constraint violations are `ConstructionError` at IR build time, not execution-time denials
- **Sealed types** — `Source` and `IntentIR` have private constructors; they can only be produced through the sanctioned factories (`Channel`, `IRBuilder`)
- **Monotonic taint propagation** — `TaintedValue[T]` carries a `TaintState`; taint can only increase (CLEAN → TAINTED, never the reverse)
- **Frozen compiled policy** — `CompiledPolicy` is fully immutable after `compile_world()`; capability matrix stored as a `frozenset` for O(1) lookups
- **Ontology-driven** — actions, trust levels, capability grants, and taint rules are declared in `world_manifest.yaml`, not hardcoded

---

## Requirements

- Python 3.10+
- PyYAML 6.0+

---

## Installation

```bash
# Install from source
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

---

## Quick Start

```python
from runtime import build_runtime
from models import ConstructionError

# 1. Compile the world manifest once at startup
runtime = build_runtime("world_manifest.yaml")

# 2. Resolve trust from the compiled map — callers cannot inject trust
channel = runtime.channel("user")   # TrustLevel.TRUSTED
source  = channel.source            # sealed Source, cannot be fabricated

# 3. Build the Intent IR — all checks happen here
try:
    ir = runtime.builder.build(
        "send_email",
        source,
        {"to": "user@example.com"},
        # pass prior TaintedValue outputs to propagate taint automatically
    )
except ConstructionError as e:
    print(f"IR impossible: {e.reason}")
    raise

# 4. Execute — pure, no policy checks
result = runtime.sandbox.execute(ir)
print(result.value)   # {"sent": True, "to": "user@example.com"}
print(result.taint)   # TaintState.CLEAN
```

Run the bundled demo to see all scenarios:

```bash
python demo.py
```

---

## World Manifest

Actions, trust assignments, capability grants, and taint rules are declared in `world_manifest.yaml`:

```yaml
actions:
  read_data:        { type: internal }
  send_email:       { type: external }
  download_report:  { type: internal, approval_required: true }
  post_webhook:     { type: external }

trust_map:
  user:     trusted
  system:   trusted
  external: untrusted

capability_matrix:
  trusted:   [internal, external]
  untrusted: [internal]

taint_rules:
  - if_taint: tainted
    then_block: external
```

---

## Constraint Enforcement

| Violation | When raised | Mechanism |
|---|---|---|
| Undefined action | `build()` call | Action not in compiled policy |
| Capability violation | `build()` call | (trust_level, action_type) not in capability frozenset |
| Taint + external action | `build()` call | Taint rule match on propagated taint state |
| Approval required | `build()` call | Action has `approval_required: true` |
| Fabricated Source | `Source()` constructor | Structural seal (`_SOURCE_SEAL` sentinel) |
| Fabricated IntentIR | `IntentIR()` constructor | Structural seal (`_IR_SEAL` sentinel) |

---

## Module Reference

| Module | Responsibility |
|---|---|
| `models.py` | Primitive enums: `TaintState`, `ActionType`, `TrustLevel`, `ConstructionError` |
| `compile.py` | `compile_world()` — transforms YAML manifest into frozen `CompiledPolicy` |
| `channel.py` | `Channel` + sealed `Source` — trust derivation from compiled map |
| `taint.py` | `TaintedValue[T]` — generic taint-carrying wrapper with monotonic join |
| `ir.py` | Sealed `IntentIR` + `IRBuilder` — construction-time constraint enforcement |
| `sandbox.py` | `Sandbox` — pure executor, zero policy checks |
| `runtime.py` | `Runtime` + `build_runtime()` — top-level assembler and entry point |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy .

# Lint
ruff check .

# Format
ruff format .
```

### Running Tests

```bash
pytest -v
```

43 tests cover:

- Undefined actions raise `ConstructionError` at build time
- `Source` cannot be fabricated directly (sealed constructor)
- `IntentIR` cannot be fabricated directly (sealed constructor)
- Taint propagation is monotonic and automatic
- Capability violations raise at build time, not execution time
- Sandbox performs pure execution with no re-checks
- Approval gate blocks at build time
- Compiled policy artifacts are fully immutable

---

## License

MIT
