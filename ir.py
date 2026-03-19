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
         (deferred — no approval token path yet; see APPROVAL_DEFERRED note)
      4. Taint propagation: taint is computed from TaintContext
         (callers must pass a TaintContext — cannot drop taint by omission)
      5. Taint rule: TAINTED + EXTERNAL → ConstructionError

Taint threading (structural, not voluntary):
    IRBuilder.build() requires a taint_context: TaintContext argument.
    This is NOT variadic. Callers cannot omit it (TypeError if missing).

    For the first action in a chain:   TaintContext.clean()
    For chained actions with prior output: TaintContext.from_outputs(result)

    This closes the taint-drop gap: in the old design, *input_taints was
    variadic and callers could silently drop taint by passing zero args.
    Now they must explicitly construct TaintContext — a deliberate act.

Old flow:
    ActionRequest(action, source, params, taint)  # taint asserted by caller
    Runtime.execute(request)                       # runtime checks at execution
    Evaluator.check(request)                       # string comparisons, loops

New flow:
    ctx = TaintContext.from_outputs(prior_result)  # taint derived, not asserted
    ir  = builder.build(name, source, params, ctx) # raises ConstructionError if invalid
    result = sandbox.execute(ir)                   # pure execution, TaintedValue out

APPROVAL_DEFERRED:
    Actions with approval_required=True currently raise ConstructionError at
    build time. There is no ApprovalToken type yet. This is an honest dead end:
    the feature is not faked (no "require_approval" string returned as if
    something happened). Approval support is deferred to a future pass.
"""

from __future__ import annotations

from typing import Any, Dict

from compile import CompiledAction, CompiledPolicy
from channel import Source
from models import ActionType, ConstructionError, TaintState, TrustLevel
from taint import TaintContext, TaintedValue


# ── Module-private IR seal ────────────────────────────────────────────────────
_IR_SEAL: object = object()


# ── IntentIR ──────────────────────────────────────────────────────────────────

class IntentIR:
    """
    A sealed, validated execution intent.

    Cannot be constructed outside IRBuilder.build(). The existence of an
    IntentIR object is proof that all constraints were satisfied at build time.

    Fields:
        action  : CompiledAction  — the action descriptor (metadata only, no handler)
        source  : Source          — the requesting identity (channel-derived, sealed)
        params  : dict            — execution parameters
        taint   : TaintState      — computed from TaintContext, not asserted by caller
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

    Taint propagation (structural):
        Callers must pass a TaintContext derived from their prior outputs.
        TaintContext is a required argument — not variadic, not optional.
        A caller cannot casually drop taint by omitting arguments; they must
        explicitly construct TaintContext.clean() to signal a fresh start.

        For the first action in a chain (no prior output):
            ctx = TaintContext.clean()

        For chained actions (using data from a prior sandbox.execute()):
            ctx = TaintContext.from_outputs(prior_result)
            # or: ctx = TaintContext.from_outputs(result_a, result_b)
    """

    def __init__(self, policy: CompiledPolicy) -> None:
        self._policy = policy

    def build(
        self,
        action_name: str,
        source: Source,
        params: Dict[str, Any],
        taint_context: TaintContext,
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
        taint_context : TaintContext
            Required. Carries taint lineage from prior pipeline stages.
            Use TaintContext.clean() for the first action in a chain.
            Use TaintContext.from_outputs(*prior_results) for chained actions.
            This argument is NOT optional — callers cannot drop taint by omission.
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
        if not policy.can_perform(source.trust_level, action.action_type):
            raise ConstructionError(
                f"Trust level {source.trust_level.value!r} does not have capability "
                f"for {action.action_type.value!r} actions — IR cannot be formed"
            )

        # ── 3. Approval gate (deferred) ────────────────────────────────────────
        # Approval-required actions cannot be constructed without an approval token.
        # ApprovalToken is not yet implemented. This raises ConstructionError
        # honestly — there is no success path through approval yet.
        # See APPROVAL_DEFERRED in module docstring.
        if action.approval_required:
            raise ConstructionError(
                f"Action {action_name!r} requires approval — "
                f"approval token support is deferred; IR construction blocked"
            )

        # ── 4. Taint from TaintContext (structural, not voluntary) ─────────────
        # Taint is read from the required TaintContext. The caller cannot omit
        # it (Python raises TypeError). To suppress taint they must explicitly
        # write TaintContext.clean() — a deliberate, visible, auditable act.
        computed_taint = taint_context.taint

        # ── 5. Taint rule check ────────────────────────────────────────────────
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
