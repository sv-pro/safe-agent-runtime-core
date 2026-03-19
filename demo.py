"""
Ontology runtime demo — new architecture.

Demonstrates the closed execution boundary and structural taint threading.

Run:  python demo.py

What this demo proves:
  1. Unknown actions fail at construction — they cannot be represented at all.
  2. Tainted data cannot cross an external boundary — IR construction is blocked.
  3. Tainted internal actions succeed — taint is not a blanket block.

This demo uses ONLY the new ontology runtime (compile / ir / sandbox / runtime).
The old src/ advisory runtime is NOT the canonical path. See src/ for the
legacy implementation, which remains for reference only.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models import ConstructionError
from runtime import build_runtime
from taint import TaintContext

SEP = "=" * 60

runtime = build_runtime(os.path.join(_ROOT, "world_manifest.yaml"))


# ── Demo 1: Unknown action — ontological absence ───────────────────────────────
#
# Attempt to build an IR for an action that does not exist in the world.
# Expected: ConstructionError raised at IRBuilder.build() — no execution path.
# This is not a runtime denial. The action cannot be represented at all.
# The world does not contain this action; therefore it cannot be constructed.

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
    print("Result            : action does not exist in this world — IR cannot be formed")
print()


# ── Demo 2: Taint containment — tainted data vs external boundary ─────────────
#
# A trusted source reads internal data → gets back a TaintedValue (tainted
# because it came from a tainted-source channel in this scenario).
#
# The caller then attempts to send that tainted data via an external action.
# Expected: ConstructionError at IRBuilder.build() — the taint rule fires
# before any execution is attempted. Taint is real physics, not a label.
#
# Note: We simulate taint by using an "external" channel (untrusted, auto-tainted
# by the taint rule) to read data, then attempt to forward it externally.
# The "external" channel maps to UNTRUSTED → can only reach INTERNAL actions.
# To make Demo 2 clearer, we use a trusted channel but manually carry a TAINTED
# TaintContext, which is what would happen if the data source were tainted.

print(SEP)
print("DEMO 2 — Taint containment")
print("trusted source, tainted data (TaintContext.from_outputs of TAINTED result)")
print("→ attempts external action (post_webhook)")
print("-" * 60)
try:
    channel = runtime.channel("user")   # trusted
    source = channel.source

    # Simulate: prior pipeline step produced a tainted result
    # (e.g., data was read from an untrusted source earlier in the chain)
    from taint import TaintedValue
    from models import TaintState
    tainted_prior = TaintedValue(value={"data": "untrusted content"}, taint=TaintState.TAINTED)

    # Build context carrying the taint forward (structural — cannot be omitted)
    ctx = TaintContext.from_outputs(tainted_prior)

    # Attempt to use tainted data in an external action
    ir = runtime.builder.build(
        "post_webhook",
        source,
        {"url": "https://external.example.com", "body": tainted_prior.value},
        ctx,
    )
    print("BUG: should not reach here")
except ConstructionError as e:
    print(f"ConstructionError : {e}")
    print("Result            : taint blocks external boundary — IR cannot be formed")
    print("                    this is not a guardrail, it is a law of construction")
print()


# ── Demo 3: Allowed tainted internal action ────────────────────────────────────
#
# A trusted source uses tainted data for an INTERNAL action (read_data).
# Expected: IRBuilder.build() succeeds, sandbox.execute() runs, TaintedValue returned.
# Not everything tainted is impossible — only tainted + external is impossible.
# The taint is preserved in the output (monotonic propagation).

print(SEP)
print("DEMO 3 — Tainted internal action (allowed)")
print("trusted source, tainted context → internal action (read_data)")
print("-" * 60)
channel = runtime.channel("user")
source = channel.source

tainted_input = TaintedValue(value={"query": "user-supplied query"}, taint=TaintState.TAINTED)
ctx = TaintContext.from_outputs(tainted_input)

ir = runtime.builder.build("read_data", source, tainted_input.value, ctx)
result = runtime.sandbox.execute(ir)

print(f"IR taint   : {ir.taint.value}")
print(f"Result     : {result}")
print(f"Output     : {result.value}")
print(f"Taint out  : {result.taint.value}  ← taint preserved, not silently dropped")
print("Result     : tainted internal action executes — taint blocks only external crossing")
print()
print("Demo complete.")
print()
print("Architecture summary:")
print("  - Execution boundary: CompiledAction has no _invoke(); only Sandbox.execute() runs handlers")
print("  - Taint boundary:     TaintContext required by IRBuilder.build(); cannot be dropped by omission")
print("  - Demo path:          uses runtime.py / compile.py / ir.py / sandbox.py (NOT src/)")
