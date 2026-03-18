"""
Taint Engine
============

TaintedValue[T] is the mandatory return type of all Sandbox.execute() calls.

Old model:
    ActionRequest(taint=TaintState.TAINTED)  # caller asserts taint (honor system)
    # caller forgets → taint suppressed silently

New model:
    result: TaintedValue = sandbox.execute(ir)
    # result.taint is computed by the runtime — caller cannot suppress it
    ir2 = builder.build("send_email", source, params, result)
    # builder extracts taint from result automatically via TaintedValue.join()

Propagation rules:
    1. Every Sandbox.execute() returns TaintedValue — no exceptions.
    2. IRBuilder.build() accepts *input_taints: TaintedValue as prior outputs.
    3. Taint join is monotonic: CLEAN ∨ TAINTED = TAINTED. Cannot decrease.
    4. If no inputs are passed, taint defaults to CLEAN.
    5. If any input is TAINTED, the IR carries TAINTED taint.
    6. If the IR carries TAINTED taint AND the action is EXTERNAL,
       IRBuilder raises ConstructionError — the IR cannot be formed.

Callers cannot suppress taint by:
    - Omitting prior outputs (they must pass TaintedValue, not unwrap it)
    - Passing clean TaintedValue with .value from a tainted result
      (they can try, but this is a code audit concern, not a type concern)
    - Setting a different taint on the IR directly (IntentIR is immutable)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Iterator, TypeVar

from models import TaintState

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class TaintedValue(Generic[T]):
    """
    A value paired with its taint state.

    This is the return type of all Sandbox.execute() calls.
    Taint cannot be removed from a TaintedValue — only propagated
    or joined with other TaintedValues.

    Use .map() to transform the value while preserving taint.
    Use TaintedValue.join(*values) to compute the join of multiple taints.
    """

    value: T
    taint: TaintState

    def map(self, f: Callable[[T], U]) -> "TaintedValue[U]":
        """Apply f to value, preserving taint state."""
        return TaintedValue(value=f(self.value), taint=self.taint)

    @staticmethod
    def join(*values: "TaintedValue") -> TaintState:
        """
        Compute the taint join across zero or more TaintedValues.

        join() with no arguments returns CLEAN (identity element).
        join() with any TAINTED argument returns TAINTED.
        Taint is monotonic: once introduced, it cannot be removed.
        """
        result = TaintState.CLEAN
        for v in values:
            result = result.join(v.taint)
        return result

    def __repr__(self) -> str:
        return f"TaintedValue(taint={self.taint.value!r}, value={self.value!r})"
