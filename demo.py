"""
Demo scenarios for the Safe Agent Runtime Core.

Demonstrates:
  A) Ontological absence  — an action that does not exist in the world is impossible.
  B) Taint containment    — an external (tainted) source cannot trigger external effects.
"""

import json
from runtime import evaluate, load_world


def run(label, tool_call, world):
    result = evaluate(tool_call, world)
    print(f"[{label}]")
    print(f"  tool_call : {json.dumps(tool_call)}")
    print(f"  decision  : {result['decision']}")
    print(f"  reason    : {result['reason']}")
    print()
    return result


def main():
    world = load_world("world.yaml")

    # ── Demo A: Ontological absence ───────────────────────────────────────────
    # The action "delete_repository" is not defined in the world at all.
    # It is not blocked — it simply cannot be constructed.
    demo_a = run(
        "Demo A — Ontological absence",
        tool_call={
            "action": "delete_repository",
            "params": {},
            "source": "external",
        },
        world=world,
    )
    assert demo_a["decision"] == "impossible", f"Expected 'impossible', got {demo_a['decision']!r}"

    # ── Demo B: Taint containment ─────────────────────────────────────────────
    # The action "send_email" exists and is of type "external".
    # Source "external" is tainted; a tainted source cannot trigger external effects.
    demo_b = run(
        "Demo B — Taint containment",
        tool_call={
            "action": "send_email",
            "params": {"to": "client"},
            "source": "external",
        },
        world=world,
    )
    assert demo_b["decision"] == "impossible", f"Expected 'impossible', got {demo_b['decision']!r}"

    # ── Bonus: trusted user reading internal data — allowed ───────────────────
    run(
        "Bonus — Trusted user reads internal data",
        tool_call={
            "action": "read_data",
            "params": {},
            "source": "user",
        },
        world=world,
    )

    # ── Bonus: approval-required action ───────────────────────────────────────
    run(
        "Bonus — Trusted user downloads report (approval required)",
        tool_call={
            "action": "download_report",
            "params": {},
            "source": "user",
        },
        world=world,
    )

    print("All assertions passed.")


if __name__ == "__main__":
    main()
