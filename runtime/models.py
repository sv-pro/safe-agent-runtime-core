"""
Base types for the ontological runtime.

This module contains only primitive enumerations and the construction error.
It has no imports from other runtime modules — it is the foundation layer.

Design notes:
  - TrustLevel replaces the old string-based trust map lookups.
  - TaintState.join() makes taint monotonic and composable.
  - ConstructionError replaces ImpossibleActionError: the name change is
    intentional. The old name implied a runtime denial ("the action is
    impossible"). The new name describes what actually happens: the IR
    cannot be constructed. The failure is at build time, not execution time.
"""

from enum import Enum


class TaintState(Enum):
    CLEAN = "clean"
    TAINTED = "tainted"

    def join(self, other: "TaintState") -> "TaintState":
        """
        Taint lattice join (least upper bound).

        CLEAN  ∨ CLEAN   = CLEAN
        CLEAN  ∨ TAINTED = TAINTED
        TAINTED ∨ CLEAN  = TAINTED
        TAINTED ∨ TAINTED = TAINTED

        Taint is monotonic: it can only increase, never decrease.
        """
        if self is TaintState.TAINTED or other is TaintState.TAINTED:
            return TaintState.TAINTED
        return TaintState.CLEAN


class ActionType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class TrustLevel(Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ConstructionError(Exception):
    """
    Raised when an IntentIR cannot be constructed.

    This is NOT a runtime denial. The IR cannot be formed because the
    requested combination of (action, trust, taint) is not representable
    in the compiled policy.

    The action is impossible in this context — not forbidden at execution
    time. There is no execution-time check to bypass because execution
    is never reached.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"ConstructionError: {reason}")
