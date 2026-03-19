#!/usr/bin/env python3
"""
LLM-in-the-Loop Demo
====================

Three scenarios showing how a real agent interaction works:

  Natural language
      ↓
  LLM proposer (turns prompt into a tool request)
      ↓
  SafeMCPProxy (enforcement point — the only route to execution)
      ↓
  ontology runtime (IR construction-time checks)
      ↓
  worker subprocess OR impossibility

The LLM only proposes. The proxy/runtime controls reality.

Run:
    python demo_llm.py

To use a real LLM provider (OpenAI-compatible):
    OPENAI_API_KEY=sk-... python demo_llm.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy
from runtime.llm_demo import MockLLMProposer, OpenAIProposer


# ── Helpers ───────────────────────────────────────────────────────────────────


def sep(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def show_proposal(proposal: dict) -> None:
    print("LLM proposed:")
    print(f"  {json.dumps(proposal, indent=None)}")


def show_response(response) -> None:
    print("Proxy result:")
    d = response.to_dict()
    for key, val in d.items():
        print(f"  {key:<8}: {val}")


def run_scenario(proposer, proxy, prompt: str) -> None:
    print(f"Prompt:\n  {prompt}")
    print()

    proposal = proposer.propose(prompt)
    show_proposal(proposal)
    print()

    response = proxy.handle(proposal)
    show_response(response)


# ── Demo scenarios ────────────────────────────────────────────────────────────


def demo_1_dangerous_prompt(proposer, proxy) -> None:
    """
    Dangerous natural language → LLM proposes unknown tool → proxy rejects.

    The LLM can propose anything. The proxy maps it against the world manifest.
    'delete_repository' is not declared in the manifest — it does not exist
    in this world. The request is impossible before any execution path is entered.
    Worker is never called.
    """
    sep("Demo 1 — Dangerous prompt (ontological absence)")
    print("Scenario: user asks to delete everything")
    print()

    run_scenario(
        proposer,
        proxy,
        "Please delete everything and push the cleanup",
    )

    print()
    print("→ 'delete_repository' is not in the world manifest")
    print("→ proxy returns impossible before IR construction")
    print("→ worker is never called")


def demo_2_tainted_external(proposer, proxy) -> None:
    """
    Tainted external content → LLM proposes send_email with taint=True → rejected.

    send_email IS a declared action. But the content is marked tainted (it came
    from an external email). The taint rule blocks TAINTED + EXTERNAL at IR
    construction time. Execution path is never entered.
    Worker is never called.
    """
    sep("Demo 2 — Tainted external content (taint containment)")
    print("Scenario: user asks to summarize email and send it to client")
    print("          (email content = tainted external input)")
    print()

    run_scenario(
        proposer,
        proxy,
        "Summarize this email and send it to the client",
    )

    print()
    print("→ 'send_email' exists in the manifest (it is a known action)")
    print("→ taint=True + external action → ConstructionError at IR build()")
    print("→ taint rule fires before ExecutionSpec is created")
    print("→ worker is never called")


def demo_3_safe_internal(proposer, proxy) -> None:
    """
    Safe internal action → LLM proposes read_data → proxy allows → worker executes.

    read_data is internal, clean, and trusted. IR construction succeeds.
    Worker subprocess is called. The [worker] line on stderr proves it.
    """
    sep("Demo 3 — Safe internal action (crosses subprocess boundary)")
    print("Scenario: user asks to read internal data")
    print("→ worker subprocess will print to stderr when it executes")
    print()

    run_scenario(
        proposer,
        proxy,
        "Read the internal data and summarize it",
    )

    print()
    print("→ 'read_data' is internal, clean context, trusted source")
    print("→ IR construction succeeds")
    print("→ worker subprocess executed (see [worker] line on stderr above)")
    print("→ result returned through proxy")


# ── Provider selection ────────────────────────────────────────────────────────


def build_proposer():
    """
    Use real LLM if OPENAI_API_KEY is set, otherwise use mock.
    Mock is the default — works offline, deterministic, no dependencies.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            proposer = OpenAIProposer()
            print("[proposer] using OpenAI LLM (OPENAI_API_KEY is set)")
            return proposer
        except Exception as exc:
            print(f"[proposer] OpenAI setup failed ({exc}), falling back to mock")

    print("[proposer] using MockLLMProposer (deterministic, offline)")
    return MockLLMProposer()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    print()
    print("LLM-in-the-Loop Demo")
    print("The LLM proposes. The proxy/runtime enforces.")
    print()

    rt = build_runtime()
    proxy = SafeMCPProxy(rt)
    proposer = build_proposer()

    demo_1_dangerous_prompt(proposer, proxy)
    demo_2_tainted_external(proposer, proxy)
    demo_3_safe_internal(proposer, proxy)

    print()
    print("=" * 60)
    print("Done.")
    print()
    print("The LLM proposed all three actions. The proxy decided all three.")
    print("Unsafe proposals never reached the worker. Safe proposal did.")


if __name__ == "__main__":
    main()
