"""
Demo: Ontological Runtime — "impossible instead of deny"

Old system flow:
    registry.get("send_email")               # string lookup, raises at get()
    ActionRequest(source=Source("user"),     # caller claims trust
                  taint=TaintState.TAINTED)  # caller asserts taint
    runtime.execute(request)                 # checks at execution time

New system flow:
    channel = runtime.channel("user")        # trust from compiled map
    source  = channel.source                 # sealed — cannot be fabricated
    ir = runtime.builder.build(              # ALL checks at construction time
        "send_email", source, params, *prior_outputs
    )
    result = runtime.sandbox.execute(ir)     # pure execution, zero checks

Scenarios:
  A) Undefined action    — build() raises before any execution path
  B) Sealed Source       — Source() constructor raises TypeError
  C) Taint propagation   — builder computes taint from prior outputs,
                            raises ConstructionError (trusted user, tainted input, external)
  D) Capability boundary — untrusted source, external action → ConstructionError at build
  E) Allowed execution   — happy path, returns TaintedValue
  F) Approval gate       — approval_required → ConstructionError at build
  G) Taint output        — taint propagates to output TaintedValue
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models import ConstructionError, TaintState, TrustLevel
from taint import TaintedValue
from channel import Source
from runtime import build_runtime


def run(label: str, fn):
    print(f"[{label}]")
    try:
        result = fn()
        print(f"  outcome : EXECUTED")
        print(f"  result  : {result}")
    except ConstructionError as e:
        print(f"  outcome : ConstructionError (IR impossible — not denied)")
        print(f"  reason  : {e.reason}")
    except TypeError as e:
        print(f"  outcome : TypeError (structural seal violated)")
        print(f"  reason  : {e}")
    print()


def main():
    runtime = build_runtime("world_manifest.yaml")

    # ── A: Undefined action — IR cannot be constructed ─────────────────────────
    # "delete_repository" is not in world_manifest.yaml.
    # builder.build() raises ConstructionError at construction.
    # No execution path is entered. The action does not exist — it is not denied.
    def demo_a():
        source = runtime.channel("user").source
        return runtime.builder.build("delete_repository", source, {})

    run("A — Undefined action: IR construction impossible", demo_a)

    # ── B: Sealed Source — cannot fabricate trust ──────────────────────────────
    # Old: Source("user") — any caller could claim any identity.
    # New: Source() raises TypeError — trust is derived from channel, not caller.
    print("[B — Sealed Source: direct construction raises TypeError]")
    try:
        Source(trust_level=TrustLevel.TRUSTED, identity="attacker")
        print("  BUG: Source construction should have raised")
    except TypeError as e:
        print(f"  Source(trust_level=TRUSTED, identity='attacker') → TypeError")
        print(f"  reason  : {e}")
    print()

    # ── C: Taint propagation — trusted user, tainted output used as input ──────
    # Step 1: simulate a tainted result (data from an external source).
    # Step 2: trusted user tries to use tainted data in an external action.
    # Taint is propagated from the prior output — caller cannot suppress it.
    def demo_c():
        tainted_read_result = TaintedValue(
            value={"data": "<externally-injected content>"},
            taint=TaintState.TAINTED,
        )
        source = runtime.channel("user").source  # TRUSTED
        return runtime.builder.build(
            "send_email",
            source,
            {"to": "target@example.com"},
            tainted_read_result,  # taint propagated from this prior output
        )

    run("C — Taint propagation: trusted user + tainted input + external action", demo_c)

    # ── D: Capability boundary — untrusted cannot reach external actions ────────
    # Old: runtime.execute() checked at execution time.
    # New: builder.build() raises ConstructionError at construction.
    def demo_d():
        source = runtime.channel("external").source  # UNTRUSTED
        return runtime.builder.build("send_email", source, {"to": "x@y.com"})

    run("D — Capability boundary: untrusted source, external action", demo_d)

    # ── E: Allowed execution — happy path ──────────────────────────────────────
    def demo_e():
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {"query": "SELECT *"})
        return runtime.sandbox.execute(ir)

    run("E — Allowed execution: trusted user, clean data, internal action", demo_e)

    # ── F: Approval gate at construction ──────────────────────────────────────
    # Old: Evaluator returned REQUIRE_APPROVAL → Runtime raised. Dead end (no path to success).
    # New: IRBuilder raises at build time with a message indicating what is needed.
    def demo_f():
        source = runtime.channel("user").source
        return runtime.builder.build("download_report", source, {"id": "r-001"})

    run("F — Approval gate: construction blocked until approval token provided", demo_f)

    # ── G: Taint propagation to output ────────────────────────────────────────
    print("[G — Taint output: taint propagates through sandbox to result]")
    source = runtime.channel("user").source
    tainted_input = TaintedValue(value={"q": "user data"}, taint=TaintState.TAINTED)
    # Internal action + tainted input is allowed (taint rule only blocks EXTERNAL)
    ir = runtime.builder.build("read_data", source, {"query": "x"}, tainted_input)
    result = runtime.sandbox.execute(ir)
    print(f"  ir.taint     : {ir.taint.value!r}    ← propagated from tainted_input")
    print(f"  result.taint : {result.taint.value!r} ← propagated to output")
    print(f"  result.value : {result.value}")
    print()

    print("Demo complete.")


if __name__ == "__main__":
    main()
