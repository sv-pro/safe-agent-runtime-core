"""
Ontology runtime demo — three scenarios.

This prototype demonstrates a constrained action world where undefined actions
cannot be constructed and tainted data cannot trigger external side effects.

Run:  python demo.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.errors import ImpossibleActionError, UnknownActionError
from src.runtime import Runtime
from src.world_loader import load_world

registry, world = load_world(os.path.join(_ROOT, "world.yaml"))
runtime = Runtime(world)

SEP = "=" * 60


# ── Demo 1: Ontological absence ────────────────────────────────────────────────
#
# Attempt to construct an action that does not exist in the ontology.
# Expected: UnknownActionError raised at construction — no execution path entered.
# This is not a runtime denial. The action cannot be represented at all.

print(SEP)
print("DEMO 1 — Ontological absence")
print("Attempting to construct: delete_repository")
print("-" * 60)
try:
    req = registry.build_request("delete_repository", source="user", params={})
    print("BUG: should not reach here")
except UnknownActionError as e:
    print(f"UnknownActionError : {e}")
    print("Result             : action does not exist in this world — construction failed")
print()


# ── Demo 2: Taint containment ──────────────────────────────────────────────────
#
# Trusted source (system) with explicit taint=True attempts an external action.
# Capability check passes (trusted → [internal, external]).
# Taint check fires: tainted data cannot cross external boundary.
# This proves taint is real physics, not a guardrail label.

print(SEP)
print("DEMO 2 — Taint containment")
print("source=system (trusted), taint=True, action=send_email (external)")
print("-" * 60)
try:
    req = registry.build_request(
        "send_email",
        source="system",
        params={"to": "target@example.com", "body": "message"},
        taint=True,
    )
    result = runtime.execute(req)
    print(f"BUG: should not reach here, got: {result}")
except ImpossibleActionError as e:
    print(f"ImpossibleActionError : {e}")
    print("Result               : taint blocks external boundary crossing — not a guardrail, a law")
print()


# ── Demo 3: Allowed tainted internal action ────────────────────────────────────
#
# External source (auto-tainted by tainted_sources rule) requests summarize.
# summarize is internal → taint rule does not fire.
# Action executes normally. Not everything tainted is impossible —
# only tainted + external is impossible.

print(SEP)
print("DEMO 3 — Allowed tainted internal action")
print("source=external (auto-tainted), action=summarize (internal)")
print("-" * 60)
req = registry.build_request(
    "summarize",
    source="external",
    params={"content": "some content from an external user"},
)
result = runtime.execute(req)
print(f"Decision : {result.decision}")
print(f"Output   : {result.output}")
print("Result   : tainted internal action executes — only tainted boundary crossing is impossible")
print()
print("Demo complete.")
