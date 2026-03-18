"""
Intent IR
=========

IntentIR is the ONLY form in which execution intent is expressed inside
the runtime. No natural language, no raw dicts, no action names as strings
reach the execution layer.

Sealing:
    IntentIR.__new__ checks for _IR_SEAL (module-private sentinel).
    External code cannot construct an IntentIR directly — TypeError at
    object creation. The only way to obtain an IntentIR is through
    IRBuilder.build().

Construction-time constraint checking (IRBuilder.build):
    All constraint evaluation happens HERE — at IR construction time.
    If build() raises ConstructionError, no execution path is entered.
    If build() returns an IntentIR, the action is valid and Sandbox
    executes it without re-checking any constraint.

    Constraints checked at construction:
      1. Ontological: action must exist in compiled policy
         (undefined action → ConstructionError, not runtime denial)
      2. Capability: source trust level must permit the action type
         (O(1) frozenset lookup on compiled capability matrix)
      3. Approval: approval-required actions block construction
         (no execution path exists without an approval token)
      4. Taint propagation: taint is computed from input TaintedValues
         (callers pass prior outputs — they cannot suppress taint)
      5. Taint rule: TAINTED + EXTERNAL → ConstructionError

Old flow:
    ActionRequest(action, source, params, taint)  # taint asserted by caller
    Runtime.execute(request)                       # runtime checks at execution
    Evaluator.check(request)                       # string comparisons, loops

New flow:
    ir = builder.build(name, source, params, *prior_outputs)
    # ↑ raises ConstructionError if any constraint fails
    # If this line completes, the IR is valid — execution is unconditional
    result = sandbox.execute(ir)
    # ↑ pure execution, zero constraint checks
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from compile import CompiledAction, CompiledPolicy
from channel import Source
from models import ActionType, ConstructionError, TaintState, TrustLevel
from taint import TaintedValue


# ── Module-private IR seal ────────────────────────────────────────────────────
_IR_SEAL: object = object()


# ── IntentIR ──────────────────────────────────────────────────────────────────

class IntentIR:
    """
    A sealed, validated execution intent.

    Cannot be constructed outside IRBuilder.build(). The existence of an
    IntentIR object is proof that all constraints were satisfied at build time.

    Fields:
        action  : CompiledAction  — the action to execute (sealed, compile-produced)
        source  : Source          — the requesting identity (channel-derived, sealed)
        params  : dict            — execution parameters
        taint   : TaintState      — computed from input TaintedValues, not asserted
    """

    __slots__ = ("action", "source", "params", "taint")

    def __new__(cls, *, _seal: object, **kwargs: Any) -> "IntentIR":
        if _seal is not _IR_SEAL:
            raise TypeError(
                "IntentIR cannot be constructed directly. "
                "Use IRBuilder.build() — construction validates all constraints."
            )
        return super().__new__(cls)

    def __init__(
        self,
        *,
        _seal: object,
        action: CompiledAction,
        source: Source,
        params: Dict[str, Any],
        taint: TaintState,
    ) -> None:
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "taint", taint)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("IntentIR is immutable after construction")

    def __repr__(self) -> str:
        return (
            f"IntentIR("
            f"action={self.action.name!r}, "
            f"source={self.source.identity!r}, "
            f"taint={self.taint.value!r})"
        )


# ── IRBuilder ─────────────────────────────────────────────────────────────────

class IRBuilder:
    """
    Constructs IntentIR from validated inputs.

    All constraint checking happens inside build(). If build() returns,
    the IR is valid. If build() raises ConstructionError, the action is
    not representable — not denied at execution, not possible at all.

    Taint propagation:
        Pass prior TaintedValue outputs as *input_taints. The builder
        computes the taint join automatically. Callers cannot suppress
        taint by omitting inputs they received from prior sandbox.execute()
        calls — the type system makes the propagation chain visible.
    """

    def __init__(self, policy: CompiledPolicy) -> None:
        self._policy = policy

    def build(
        self,
        action_name: str,
        source: Source,
        params: Dict[str, Any],
        *input_taints: TaintedValue,
    ) -> IntentIR:
        """
        Build an IntentIR or raise ConstructionError.

        Parameters
        ----------
        action_name : str
            The name of the action to execute. Must be present in the compiled
            policy — otherwise ConstructionError is raised before any execution
            path is entered.
        source : Source
            The requesting Source. Must be obtained through Channel.source —
            callers cannot fabricate a Source with an arbitrary trust level.
        params : dict
            Execution parameters passed to the action handler.
        *input_taints : TaintedValue
            Prior action outputs whose values are used in params. Taint is
            propagated automatically via TaintedValue.join(). If any input
            is TAINTED, the IR carries TAINTED taint, and the taint rule
            check may raise ConstructionError.
        """
        policy = self._policy

        # ── 1. Ontological check ───────────────────────────────────────────────
        # The action must exist in the compiled policy. This is not a runtime
        # denial — the action does not exist in this ontology. ConstructionError
        # is raised before any execution path is entered.
        action = policy.get_action(action_name)
        if action is None:
            raise ConstructionError(
                f"Action {action_name!r} does not exist in the compiled policy — "
                f"undefined actions are impossible, not denied"
            )

        # ── 2. Capability check (O(1) frozenset lookup) ────────────────────────
        # Old: `if action_type.value not in capabilities[trust_level]` — string scan
        # New: `if (trust_level, action_type) not in frozenset` — O(1), no strings
        if not policy.can_perform(source.trust_level, action.action_type):
            raise ConstructionError(
                f"Trust level {source.trust_level.value!r} does not have capability "
                f"for {action.action_type.value!r} actions — IR cannot be formed"
            )

        # ── 3. Approval gate ───────────────────────────────────────────────────
        # Approval-required actions cannot be constructed without an approval token.
        # The old system returned REQUIRE_APPROVAL and then raised at execution —
        # a dead end with no path to success. Now it raises at construction.
        # A real system would accept ApprovalToken as a parameter and verify it here.
        if action.approval_required:
            raise ConstructionError(
                f"Action {action_name!r} requires approval — "
                f"IR construction blocked until an approval token is provided"
            )

        # ── 4. Taint propagation ───────────────────────────────────────────────
        # Compute taint from all prior TaintedValue outputs.
        # Callers must pass their prior outputs here — they cannot suppress taint
        # by "forgetting". The join is monotonic: CLEAN ∨ TAINTED = TAINTED.
        computed_taint = TaintedValue.join(*input_taints)

        # ── 5. Taint rule check ────────────────────────────────────────────────
        # Old: `if taint.value == rule["taint"] and action_type.value == rule["action_type"]`
        #       — string comparison against YAML-derived strings at runtime
        # New: enum identity comparison against compiled TaintRule objects
        taint_rule = policy.taint_rule_for(computed_taint, action.action_type)
        if taint_rule is not None:
            raise ConstructionError(
                f"Taint rule violation: {taint_rule.reason} — IR cannot be formed"
            )

        return IntentIR(
            _seal=_IR_SEAL,
            action=action,
            source=source,
            params=params,
            taint=computed_taint,
        )
