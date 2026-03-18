from typing import Any, Dict, List

from models import Decision, DecisionOutcome, ImpossibleActionError, TaintState
from registry import ActionRequest


class Evaluator:
    """
    Pure constraint checker.

    Invariants:
    - MUST NOT execute anything.
    - MUST NOT be called directly by external callers.
    - Only Runtime may call Evaluator.check().

    Returns a Decision when constraints pass, raises ImpossibleActionError
    when they do not. There is no soft advisory path.
    """

    def __init__(self, world: Dict[str, Any]) -> None:
        self._trust: Dict[str, str] = world["trust"]
        self._capabilities: Dict[str, List[str]] = world["capabilities"]
        self._taint_rules: List[Dict[str, str]] = world.get("taint_rules", [])

    def check(self, request: ActionRequest) -> Decision:
        trust_level = self._trust.get(request.source.name, "untrusted")

        # Step 1: Capability check — source trust level must permit the action type.
        allowed_types = self._capabilities.get(trust_level, [])
        if request.action.action_type.value not in allowed_types:
            raise ImpossibleActionError(
                f"Source '{request.source.name}' (trust={trust_level!r}) cannot perform "
                f"'{request.action.action_type.value}' actions — capability denied"
            )

        # Step 2: Taint rules — tainted data cannot trigger actions of restricted types.
        # Taint is about the DATA, not the source. A trusted source carrying tainted
        # params can still be blocked — this is distinct from the capability check above.
        for rule in self._taint_rules:
            if (
                request.taint.value == rule["taint"]
                and request.action.action_type.value == rule["action_type"]
            ):
                raise ImpossibleActionError(rule["reason"])

        # Step 3: Approval gate.
        if request.action.approval_required:
            return Decision(
                outcome=DecisionOutcome.REQUIRE_APPROVAL,
                reason="Action is flagged approval_required — explicit approval must be obtained before execution",
            )

        return Decision(outcome=DecisionOutcome.ALLOW, reason="All constraints satisfied")
