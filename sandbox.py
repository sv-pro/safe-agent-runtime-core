"""
Sandbox
=======

Pre-built execution environment. Executes IntentIR. No policy checks.

Old model:
    Runtime.execute(request)
      → Evaluator.check(request)   # runtime policy evaluation
      → action._execute(params)    # execution

New model:
    ir = builder.build(...)        # construction = validation
    sandbox.execute(ir)            # pure execution, zero checks

The Sandbox receives a pre-validated IntentIR. It executes the action
handler and wraps the result in TaintedValue for downstream propagation.

If IntentIR was successfully constructed, execution is unconditional.
There are no secondary checks inside the sandbox. The architectural
guarantee is: construction = validation, execution = consequence.

Tool isolation:
    Action handlers are registered at compile time inside the handler
    dict passed to compile_world(). They are stored in CompiledAction._handler
    and are only invocable through Sandbox.execute(). They are not exposed
    as module-level callables, not stored in a global registry, and not
    accessible to callers who hold only a CompiledPolicy reference.

    Python-level limitation: CompiledAction._invoke() is reachable by
    any code that holds a CompiledAction reference. True tool isolation
    requires a process or capability boundary (e.g., subprocess, seccomp,
    separate Python interpreter). This architecture makes bypass visible
    and auditable — not invisible.
"""

from __future__ import annotations

from compile import CompiledPolicy
from ir import IntentIR
from taint import TaintedValue


class Sandbox:
    """
    Sealed execution environment.

    execute() is the only path to action handler invocation.
    It accepts only IntentIR — not action names, not raw dicts, not strings.
    The IntentIR's existence proves construction-time validation passed.
    """

    def __init__(self, policy: CompiledPolicy) -> None:
        self._policy = policy

    def execute(self, ir: IntentIR) -> TaintedValue:
        """
        Execute a pre-validated IntentIR.

        No constraint checking. No policy evaluation. No trust lookup.
        The IR was validated at construction — execution is the consequence.

        Returns TaintedValue wrapping the action result. The taint carried
        by the IR propagates to the output, enabling downstream IR builders
        to compute taint joins automatically.
        """
        raw_result = ir.action._invoke(ir.params)
        return TaintedValue(value=raw_result, taint=ir.taint)
