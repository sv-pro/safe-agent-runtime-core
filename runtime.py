"""
Runtime — top-level assembler
==============================

Compiles the world manifest and wires together Channel, IRBuilder, and Executor.
This is the only module callers need to import for normal use.

Architecture (subprocess boundary edition):

    world_manifest.yaml
          │
          ▼
    compile_world()  ──────────────────────► CompiledPolicy (frozen, metadata only)
          │                                       │
          │              ┌────────────────────────┤
          │              │                        │
          ▼              ▼                        ▼
       Channel       IRBuilder               Executor (no handlers — subprocess only)
    (trust from    (construction-time            │
     compiled map)  constraint checks)           │ stdin/stdout
          │              │                        ▼
          ▼              ▼                   worker.py subprocess
        Source  ──►  IntentIR  ──────────►  (owns handlers, separate process)
                                                  │
                                                  ▼
                                            TaintedValue

Process boundary:
    - The main process (this file) holds NO callable handlers.
    - Executor is a transport facade: it creates an ExecutionSpec and sends it
      to worker.py via subprocess stdin/stdout.
    - worker.py runs in a separate process and owns the real handlers.
    - The main process cannot call handler functions directly.

Execution boundary:
    - CompiledPolicy exposes CompiledAction metadata objects (no handlers, no _invoke).
    - Executor holds only a path to the worker script, not handler callables.
    - The only path to handler invocation: IRBuilder.build() → Executor.execute()
      → worker subprocess.

Taint boundary:
    - Executor.execute() returns TaintedValue (same interface as old Sandbox).
    - Next IRBuilder.build() requires TaintContext (not variadic, not optional).
    - Callers must explicitly construct TaintContext.clean() or
      TaintContext.from_outputs(prior_result) — taint cannot be dropped silently.

Invariant:
    If executor.execute(ir) is called, ir was produced by IRBuilder.build().
    If IRBuilder.build() returned, all constraints were satisfied at construction.
    There are no runtime policy checks in the execution path.
    The worker receives only an already-validated ExecutionSpec.

Caller flow:
    from taint import TaintContext

    runtime = build_runtime()
    channel = runtime.channel("user")       # trust from compiled map
    source  = channel.source               # sealed — cannot be fabricated

    # First action — no prior outputs, explicit clean context
    ctx1 = TaintContext.clean()
    ir1  = runtime.builder.build("read_data", source, {"query": "x"}, ctx1)
    r1   = runtime.sandbox.execute(ir1)    # TaintedValue — dispatches to worker

    # Chained action — taint carried forward structurally
    ctx2 = TaintContext.from_outputs(r1)
    ir2  = runtime.builder.build("send_email", source, {...}, ctx2)
    # ↑ raises ConstructionError if r1 was TAINTED and send_email is EXTERNAL
"""

from __future__ import annotations

import os
from typing import Any

from compile import CompiledPolicy, compile_world
from channel import Channel
from ir import IRBuilder
from executor import Executor


class Runtime:
    """
    Assembled runtime: compiled policy + channel factory + IR builder + executor.

    Immutable after construction. All components are derived from the same
    CompiledPolicy so trust assignments, capability matrix, and taint rules
    are consistent across channel resolution, IR construction, and execution.

    The runtime holds NO callable handlers. Execution is delegated to a
    worker subprocess via Executor.
    """

    __slots__ = ("_policy", "_builder", "_executor")

    def __init__(
        self,
        policy: CompiledPolicy,
        executor: Executor,
    ) -> None:
        object.__setattr__(self, "_policy", policy)
        object.__setattr__(self, "_builder", IRBuilder(policy))
        object.__setattr__(self, "_executor", executor)

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
    def sandbox(self) -> Executor:
        """
        The execution layer. Use sandbox.execute(ir) to run IntentIR.

        Despite the name (kept for API compatibility), this is now an Executor
        that dispatches to a worker subprocess. No handlers live here.
        """
        return self._executor

    @property
    def executor(self) -> Executor:
        """The subprocess executor. Alias for sandbox."""
        return self._executor

    @property
    def policy(self) -> CompiledPolicy:
        """The compiled policy. Read-only metadata — no handlers."""
        return self._policy


def build_runtime(manifest_path: str = "world_manifest.yaml") -> Runtime:
    """
    Entry point: compile world manifest and return an assembled Runtime.

    No handlers are defined or held in the main process.
    Execution is delegated to worker.py via Executor (subprocess boundary).

    To add a tool: add it to world_manifest.yaml AND add a handler in worker.py.
    A handler in worker.py without a manifest entry is unreachable (IRBuilder
    rejects unknown action names at construction). A manifest entry without a
    worker handler causes the worker to return an error (safe default).
    """
    if not os.path.isabs(manifest_path):
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), manifest_path)

    policy = compile_world(manifest_path)
    executor = Executor()

    return Runtime(policy, executor)
