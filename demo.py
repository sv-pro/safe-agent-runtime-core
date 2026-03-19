"""
Ontology runtime demo — subprocess execution boundary.

Demonstrates the process boundary between policy/IR logic and execution.

Run:  python demo.py

What this demo proves:
  1. Unknown actions fail at construction — worker is never invoked.
  2. Tainted data cannot cross an external boundary — IR blocked before worker.
  3. Allowed internal actions cross the process boundary to the worker.

The worker announces itself on stderr when it executes:
  [worker] executed read_data

This proves the execution happened in a different process.
"""

from __future__ import annotations

import os

from runtime import build_runtime
from runtime.models import ConstructionError, TaintState
from runtime.taint import TaintContext, TaintedValue

SEP = "=" * 60

runtime = build_runtime(os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_manifest.yaml"))


# ── Demo 1: Unknown action — ontological absence ───────────────────────────────
#
# Attempt to build an IR for an action that does not exist in the world.
# Expected: ConstructionError raised at IRBuilder.build() — worker never called.
# The action cannot be represented; the process boundary is never crossed.

print(SEP)
print("DEMO 1 — Unknown action (ontological absence)")
print("Attempting to construct IR for: delete_repository")
print("-" * 60)
try:
    channel = runtime.channel("user")
    source = channel.source
    ir = runtime.builder.build(
        "delete_repository",
        source,
        {},
        TaintContext.clean(),
    )
    print("BUG: should not reach here")
except ConstructionError as e:
    print(f"ConstructionError : {e}")
    print("Result            : action does not exist — IR cannot be formed, worker not called")
print()


# ── Demo 2: Taint containment — tainted data vs external boundary ─────────────
#
# A trusted source holds tainted data and attempts an external action.
# Expected: ConstructionError at IRBuilder.build() — taint rule fires before
# the ExecutionSpec is created. Worker process is never invoked.

print(SEP)
print("DEMO 2 — Taint containment")
print("trusted source, tainted data → external action (post_webhook)")
print("-" * 60)
try:
    channel = runtime.channel("user")   # trusted
    source = channel.source

    tainted_prior = TaintedValue(value={"data": "untrusted content"}, taint=TaintState.TAINTED)
    ctx = TaintContext.from_outputs(tainted_prior)

    ir = runtime.builder.build(
        "post_webhook",
        source,
        {"url": "https://external.example.com", "body": tainted_prior.value},
        ctx,
    )
    print("BUG: should not reach here")
except ConstructionError as e:
    print(f"ConstructionError : {e}")
    print("Result            : taint blocks external boundary — worker not called")
    print("                    this is not a guardrail, it is a law of construction")
print()


# ── Demo 3: Allowed internal action — crosses subprocess boundary ──────────────
#
# A trusted source uses a clean context for an INTERNAL action (read_data).
# Expected: IRBuilder.build() succeeds, ExecutionSpec is sent to the worker
# subprocess, worker executes and returns result, TaintedValue returned.
#
# Watch for: [worker] executed read_data  (printed by worker.py to stderr)
# This line is your proof the execution happened in a different process.

print(SEP)
print("DEMO 3 — Allowed internal action (crosses subprocess boundary)")
print("trusted source, clean context → internal action (read_data)")
print("→ worker subprocess will announce execution on stderr")
print("-" * 60)

channel = runtime.channel("user")
source = channel.source

ctx = TaintContext.clean()
ir = runtime.builder.build("read_data", source, {"query": "sales Q1"}, ctx)
result = runtime.sandbox.execute(ir)   # dispatches to worker.py subprocess

print(f"IR taint   : {ir.taint.value}")
print(f"Result     : {result}")
print(f"Output     : {result.value}")
print(f"Taint out  : {result.taint.value}")
print("Result     : execution crossed process boundary — worker ran handler, returned result")
print()
print("Demo complete.")
print()
print("Architecture summary:")
print("  - Process boundary:   handlers live only in runtime/worker.py (separate process)")
print("  - Execution path:     IRBuilder.build() → ExecutionSpec → worker subprocess")
print("  - Taint boundary:     TaintContext required by IRBuilder.build(); cannot be omitted")
print("  - Policy boundary:    worker does no policy evaluation; main process does no execution")
print("  - Demo path:          runtime/runtime.py / compile.py / ir.py / executor.py / worker.py")
