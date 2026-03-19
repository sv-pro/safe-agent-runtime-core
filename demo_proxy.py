#!/usr/bin/env python3
"""
Safe MCP Proxy — Demo
=====================

Three scenarios showing how the proxy sits between an agent client and the
ontology runtime, enforcing constraints before any tool reaches execution.

The proxy is not advisory. It is the only route. There is no side door.

Run:
    python demo_proxy.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy


def separator(title: str) -> None:
    print("=" * 60)
    print(title)
    print("-" * 60)


def show_response(response) -> None:
    d = response.to_dict()
    for key, val in d.items():
        print(f"  {key:<8}: {val}")


def main() -> None:
    rt = build_runtime()
    proxy = SafeMCPProxy(rt)

    # ── Demo 1: Unknown tool ──────────────────────────────────────────────────
    separator("DEMO 1 — Unknown tool (ontological absence)")
    print('Request: {"tool": "delete_repository", "source": "user", "taint": false}')
    print()

    response = proxy.handle({
        "tool": "delete_repository",
        "params": {},
        "source": "user",
        "taint": False,
    })

    show_response(response)
    print()
    print("→ tool not in world manifest — IR never constructed, worker never called")
    print()

    # ── Demo 2: Tainted external tool call ────────────────────────────────────
    separator("DEMO 2 — Tainted external tool call (taint containment)")
    print('Request: {"tool": "send_email", "source": "user", "taint": true}')
    print()

    response = proxy.handle({
        "tool": "send_email",
        "params": {"to": "client", "body": "hello"},
        "source": "user",
        "taint": True,
    })

    show_response(response)
    print()
    print("→ taint blocks external boundary at IR construction — worker never called")
    print()

    # ── Demo 3: Allowed internal tool call ────────────────────────────────────
    separator("DEMO 3 — Allowed internal tool call (crosses subprocess boundary)")
    print('Request: {"tool": "read_data", "source": "user", "taint": false}')
    print("→ worker subprocess will announce execution on stderr")
    print()

    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })

    show_response(response)
    print()
    print("→ proxy → runtime → worker subprocess → result returned")
    print()
    print("  [worker] line above (stderr) proves execution crossed the process boundary")


if __name__ == "__main__":
    main()
