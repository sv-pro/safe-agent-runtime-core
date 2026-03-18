"""
Runtime — top-level assembler
==============================

Compiles the world manifest and wires together Channel, IRBuilder, and Sandbox.
This is the only module callers need to import.

Architecture:

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

Invariant:
    If sandbox.execute(ir) is called, ir was produced by IRBuilder.build().
    If IRBuilder.build() returned, all constraints were satisfied at construction.
    There are no runtime policy checks in the execution path.

Caller flow:
    runtime = build_runtime()
    channel = runtime.channel("user")       # trust from compiled map
    source  = channel.source               # sealed — cannot be fabricated
    ir      = runtime.builder.build(       # raises ConstructionError on failure
        "send_email", source, params,
        *prior_tainted_outputs             # taint propagated automatically
    )
    result  = runtime.sandbox.execute(ir)  # pure execution, TaintedValue out
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from compile import CompiledPolicy, compile_world
from channel import Channel
from ir import IRBuilder
from sandbox import Sandbox


class Runtime:
    """
    Assembled runtime: compiled policy + channel factory + IR builder + sandbox.

    Immutable after construction. All components are derived from the same
    CompiledPolicy so trust assignments, capability matrix, and taint rules
    are consistent across channel resolution, IR construction, and execution.
    """

    __slots__ = ("_policy", "_builder", "_sandbox")

    def __init__(self, policy: CompiledPolicy) -> None:
        object.__setattr__(self, "_policy", policy)
        object.__setattr__(self, "_builder", IRBuilder(policy))
        object.__setattr__(self, "_sandbox", Sandbox(policy))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Runtime is immutable after construction")

    def channel(self, identity: str) -> Channel:
        """
        Create a Channel for the given identity.

        Trust is resolved from the compiled policy — the caller cannot
        override or inject a trust level. Unknown identities resolve to
        UNTRUSTED (fail-secure).
        """
        return Channel(identity=identity, policy=self._policy)

    @property
    def builder(self) -> IRBuilder:
        """The IR builder. Use builder.build() to construct IntentIR."""
        return self._builder

    @property
    def sandbox(self) -> Sandbox:
        """The execution sandbox. Use sandbox.execute(ir) to run IntentIR."""
        return self._sandbox

    @property
    def policy(self) -> CompiledPolicy:
        """The compiled policy. Read-only."""
        return self._policy


def build_runtime(manifest_path: str = "world_manifest.yaml") -> Runtime:
    """
    Entry point: compile world manifest and return an assembled Runtime.

    Handlers defined here are the ONLY tools that can ever be executed.
    They are not globally callable — they exist only inside the sandbox,
    reachable exclusively through Sandbox.execute(ir).

    To add a tool: add it to world_manifest.yaml AND add a handler here.
    A handler without a manifest entry is never registered (unreachable).
    A manifest entry without a handler gets a no-op lambda (safe default).
    """
    handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
        "read_data":       lambda p: {"data": p.get("query", ""), "source": "db"},
        "send_email":      lambda p: {"sent": True, "to": p.get("to", "")},
        "download_report": lambda p: {"report": p.get("id", ""), "bytes": 0},
        "post_webhook":    lambda p: {"status": 200, "url": p.get("url", "")},
    }
    policy = compile_world(manifest_path, handlers)
    return Runtime(policy)
