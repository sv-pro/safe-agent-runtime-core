"""
Runtime — top-level assembler
==============================

Compiles the world manifest and wires together Channel, IRBuilder, and Sandbox.
This is the only module callers need to import for normal use.

Architecture:

    world_manifest.yaml
          │
          ▼
    compile_world()  ──────────────────────► CompiledPolicy (frozen, metadata only)
          │                                       │
          │              ┌────────────────────────┤
          │              │                        │
          ▼              ▼                        │
       Channel       IRBuilder               handlers dict
    (trust from    (construction-time      (local to build_runtime,
     compiled map)  constraint checks)      passed to Sandbox only)
          │              │                        │
          ▼              ▼                        ▼
        Source  ──►  IntentIR  ──────────►  Sandbox (owns handlers)
                                                  │
                                                  ▼
                                            TaintedValue

Execution boundary:
    - CompiledPolicy exposes CompiledAction metadata objects (no handlers, no _invoke).
    - Sandbox is the sole owner of callable handlers.
    - The only path to handler invocation: IRBuilder.build() → Sandbox.execute().

Taint boundary:
    - Sandbox.execute() returns TaintedValue.
    - Next IRBuilder.build() requires TaintContext (not variadic, not optional).
    - Callers must explicitly construct TaintContext.clean() or
      TaintContext.from_outputs(prior_result) — taint cannot be dropped silently.

Invariant:
    If sandbox.execute(ir) is called, ir was produced by IRBuilder.build().
    If IRBuilder.build() returned, all constraints were satisfied at construction.
    There are no runtime policy checks in the execution path.

Caller flow:
    from taint import TaintContext

    runtime = build_runtime()
    channel = runtime.channel("user")       # trust from compiled map
    source  = channel.source               # sealed — cannot be fabricated

    # First action — no prior outputs, explicit clean context
    ctx1 = TaintContext.clean()
    ir1  = runtime.builder.build("read_data", source, {"query": "x"}, ctx1)
    r1   = runtime.sandbox.execute(ir1)    # TaintedValue

    # Chained action — taint carried forward structurally
    ctx2 = TaintContext.from_outputs(r1)
    ir2  = runtime.builder.build("send_email", source, {...}, ctx2)
    # ↑ raises ConstructionError if r1 was TAINTED and send_email is EXTERNAL
"""

from __future__ import annotations

import os
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

    def __init__(
        self,
        policy: CompiledPolicy,
        handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
    ) -> None:
        object.__setattr__(self, "_policy", policy)
        object.__setattr__(self, "_builder", IRBuilder(policy))
        object.__setattr__(self, "_sandbox", Sandbox(handlers))

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
        """The compiled policy. Read-only metadata — no handlers."""
        return self._policy


def build_runtime(manifest_path: str = "world_manifest.yaml") -> Runtime:
    """
    Entry point: compile world manifest and return an assembled Runtime.

    Handlers defined here are the ONLY tools that can ever be executed.
    They are NOT passed to compile_world() — CompiledPolicy is pure metadata.
    Handlers are passed directly to Sandbox, which is the sole execution layer.

    To add a tool: add it to world_manifest.yaml AND add a handler here.
    A handler without a manifest entry is never reachable (IRBuilder rejects
    unknown action names at construction). A manifest entry without a handler
    causes Sandbox.execute() to raise KeyError (safe default).
    """
    if not os.path.isabs(manifest_path):
        # Resolve relative paths from the directory containing this file,
        # not from the caller's working directory.
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), manifest_path)

    handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
        "read_data":       lambda p: {"data": p.get("query", ""), "source": "db"},
        "send_email":      lambda p: {"sent": True, "to": p.get("to", "")},
        "download_report": lambda p: {"report": p.get("id", ""), "bytes": 0},
        "post_webhook":    lambda p: {"status": 200, "url": p.get("url", "")},
    }

    # compile_world produces pure metadata — no handlers, no callable behavior.
    policy = compile_world(manifest_path)

    # Runtime assembles policy (metadata) + handlers (execution) into one object.
    # The handler dict never escapes Runtime; only Sandbox holds a reference.
    return Runtime(policy, handlers)
