"""
Runtime — the single execution boundary.

This prototype demonstrates a constrained action world where undefined actions
cannot be constructed and tainted data cannot trigger external side effects.

execute() is the ONLY place where action handlers are invoked.
No handler is reachable by any path that bypasses this method.

Flow:
  1. validate required params
  2. check capability  (trust level → allowed action types)
  3. check taint       (tainted data cannot cross external boundary)
  4. if requires_approval → return structured approval result
  5. otherwise → execute handler, return allow result

Outcomes:
  ExecutionResult(decision="allow")             — handler ran
  ExecutionResult(decision="require_approval")  — action exists, needs token
  ImpossibleActionError                         — capability or taint violation
  (UnknownActionError already raised at request construction, never reaches here)
"""

from __future__ import annotations

from typing import Any, Callable

from .errors import ImpossibleActionError
from .types import ActionRequest, ExecutionResult

# Trivial handlers. The point is the runtime boundary, not the implementation.
_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "read_data":  lambda p: {"data": p.get("query", ""), "source": "db"},
    "summarize":  lambda p: f"summary: {str(p.get('content', ''))[:80]}",
    "send_email": lambda p: {"status": "email_sent", "to": p.get("to")},
}


class Runtime:
    def __init__(self, world: dict) -> None:
        self._trust: dict        = world["trust"]
        self._capabilities: dict = world["capabilities"]
        self._taint_cfg: dict    = world["taint"]

    def execute(self, request: ActionRequest) -> ExecutionResult:
        """Single execution boundary — no action handler runs outside this method."""
        self._validate_params(request)
        self._check_capability(request)
        self._check_taint(request)

        if request.action.requires_approval:
            return ExecutionResult(
                decision="require_approval",
                action=request.action.name,
            )

        output = _HANDLERS[request.action.handler](request.params)
        return ExecutionResult(
            decision="allow",
            action=request.action.name,
            output=output,
        )

    # ── Internal checks ───────────────────────────────────────────────────────

    def _validate_params(self, request: ActionRequest) -> None:
        for p in request.action.params:
            if p not in request.params:
                raise ValueError(
                    f"Missing required param '{p}' for '{request.action.name}'"
                )

    def _check_capability(self, request: ActionRequest) -> None:
        trust_level = self._trust.get(request.source, "untrusted")
        allowed_types = self._capabilities.get(trust_level, [])
        if request.action.action_type not in allowed_types:
            raise ImpossibleActionError(
                f"Action type '{request.action.action_type}' is not available "
                f"in this world for source '{request.source}' (trust={trust_level})"
            )

    def _check_taint(self, request: ActionRequest) -> None:
        # Taint originates from two independent sources:
        #   1. explicit flag on the request (trusted source, tainted payload)
        #   2. source identity listed in tainted_sources (auto-derived)
        # This makes taint independent of the capability check:
        #   a trusted source passes capability but can still carry tainted data.
        source_tainted = request.source in self._taint_cfg.get("tainted_sources", [])
        effective_taint = request.taint or source_tainted

        rule = self._taint_cfg.get("external_side_effect_rule", "impossible")
        if effective_taint and request.action.action_type == "external":
            if rule == "impossible":
                raise ImpossibleActionError(
                    f"Tainted request cannot cross external boundary "
                    f"via '{request.action.name}'"
                )
