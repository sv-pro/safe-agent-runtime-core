"""
Demo scenarios for the Constrained Execution Runtime.

Demonstrates the architectural invariant:
  Unsafe actions are not denied — they are impossible to execute.

Scenarios:
  A) Ontological absence  — unknown action cannot be constructed (registry raises).
  B) Taint containment    — trusted user with tainted data cannot trigger external action.
  C) Capability boundary  — untrusted source cannot perform external actions.
  D) Allowed execution    — trusted user with clean data executes successfully.
  E) Approval gate        — approval-required action is blocked with clear error.
"""

from registry import ActionRequest
from runtime import build_runtime
from models import ImpossibleActionError, Source, TaintState


def run_demo(label, fn):
    print(f"[{label}]")
    try:
        result = fn()
        print(f"  result    : {result}")
        print(f"  outcome   : EXECUTED")
    except ImpossibleActionError as e:
        print(f"  raised    : ImpossibleActionError")
        print(f"  reason    : {e.reason}")
    print()


def main():
    runtime, registry = build_runtime("world.yaml")

    # ── Demo A: Ontological absence ───────────────────────────────────────────
    # "delete_repository" is not in the registry.
    # registry.get() raises immediately — the action cannot be constructed at all.
    print("[Demo A — Ontological absence]")
    try:
        registry.get("delete_repository")
        raise AssertionError("Should have raised")
    except ImpossibleActionError as e:
        print(f"  registry.get('delete_repository') raised ImpossibleActionError")
        print(f"  reason : {e.reason}")
    print()

    # ── Demo B: Taint containment ─────────────────────────────────────────────
    # A TRUSTED user carries tainted params (e.g., data from an external source).
    # The capability check passes (user is trusted → can do external).
    # The taint rule fires (tainted data + external action → impossible).
    # This proves taint is distinct from trust and is live, reachable code.
    def demo_b():
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("user"),           # trusted source
            params={"to": "target@example.com", "body": "<external injection>"},
            taint=TaintState.TAINTED,        # data came from external source
        )
        return runtime.execute(request)

    run_demo("Demo B — Taint containment (trusted user, tainted data, external action)", demo_b)

    # ── Demo C: Capability boundary ───────────────────────────────────────────
    # Untrusted source cannot perform external actions — capability check fires.
    def demo_c():
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("external"),       # untrusted
            params={"to": "target@example.com"},
            taint=TaintState.CLEAN,
        )
        return runtime.execute(request)

    run_demo("Demo C — Capability boundary (untrusted source, external action)", demo_c)

    # ── Demo D: Allowed execution ─────────────────────────────────────────────
    # Trusted user, clean data, internal action → executes.
    def demo_d():
        action = registry.get("read_data")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"query": "SELECT *"},
            taint=TaintState.CLEAN,
        )
        return runtime.execute(request)

    run_demo("Demo D — Allowed execution (trusted user, clean data, internal action)", demo_d)

    # ── Demo E: Approval gate ─────────────────────────────────────────────────
    # Approval-required action raises even for trusted user with clean data.
    def demo_e():
        action = registry.get("download_report")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"id": "report-001"},
            taint=TaintState.CLEAN,
        )
        return runtime.execute(request)

    run_demo("Demo E — Approval gate (trusted user, clean data, approval_required)", demo_e)

    print("Demo complete.")


if __name__ == "__main__":
    main()
