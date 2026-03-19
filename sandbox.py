"""
Sandbox
=======

The ONLY execution layer. Executes IntentIR. No policy checks.

Execution boundary:
    Sandbox is the sole owner of callable action handlers. Handlers are
    passed in at construction and stored in a private dict. No other layer
    (CompiledPolicy, CompiledAction, IRBuilder, Channel) holds any reference
    to a callable handler.

    This means:
      - policy.actions["read_data"]          → CompiledAction (metadata only)
      - policy.actions["read_data"]._invoke  → AttributeError (does not exist)
      - sandbox.execute(ir)                  → the ONLY path to handler invocation

    Callers cannot bypass the Sandbox to invoke handlers because:
      1. CompiledAction carries no handler or _invoke() method.
      2. Handlers are stored in Sandbox._handlers (name-mangled, private).
      3. An IntentIR can only be produced by IRBuilder.build() after all
         construction-time constraints pass.

Old model:
    Runtime.execute(request)
      → Evaluator.check(request)   # runtime policy evaluation
      → action._execute(params)    # execution via CompiledAction

New model:
    ir = builder.build(...)        # construction = validation
    sandbox.execute(ir)            # pure execution, zero checks, Sandbox owns handlers

The Sandbox receives a pre-validated IntentIR. It looks up the handler by
action name in its private dict, invokes it, and wraps the result in
TaintedValue for downstream propagation.

If IntentIR was successfully constructed, execution is unconditional.
The architectural guarantee is: construction = validation, execution = consequence.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ir import IntentIR
from taint import TaintedValue


class Sandbox:
    """
    Sealed execution environment. The sole owner of action handlers.

    execute() is the only path to handler invocation.
    It accepts only IntentIR — not action names, not raw dicts, not strings.
    The IntentIR's existence proves construction-time validation passed.

    Handlers are private to this instance. No external code can reach them
    except through execute(ir) with a validly constructed IntentIR.
    """

    def __init__(self, handlers: Dict[str, Callable[[Dict[str, Any]], Any]]) -> None:
        # Private handler registry. Name-mangled to discourage external access.
        # This is the ONLY location where callable handlers exist at runtime.
        self.__handlers = dict(handlers)  # defensive copy

    def execute(self, ir: IntentIR) -> TaintedValue:
        """
        Execute a pre-validated IntentIR.

        No constraint checking. No policy evaluation. No trust lookup.
        The IR was validated at construction — execution is the consequence.

        Looks up the action handler from the private handler registry by
        ir.action.name. If the action has no registered handler, raises
        KeyError (safe default: no handler = no execution).

        Returns TaintedValue wrapping the action result. The taint carried
        by the IR propagates to the output, enabling downstream IRBuilders
        to compute taint joins automatically via TaintContext.from_outputs().
        """
        handler = self.__handlers.get(ir.action.name)
        if handler is None:
            raise KeyError(
                f"No handler registered for action {ir.action.name!r}. "
                "Register a handler in build_runtime() to make this action executable."
            )
        raw_result = handler(ir.params)
        return TaintedValue(value=raw_result, taint=ir.taint)
