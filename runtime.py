"""
Constrained Execution Runtime

Invariant: unsafe actions are not denied — they are impossible to execute.

All action invocations MUST go through Runtime.execute().
Evaluation and execution are structurally coupled — no bypass path exists.
"""

from typing import Any, Tuple

import yaml

from evaluator import Evaluator
from registry import ActionRegistry, ActionRequest
from models import ActionType, DecisionOutcome, ImpossibleActionError


class Runtime:
    """
    Single execution boundary for all action invocations.

    Flow:
      1. Evaluator.check() validates all constraints (raises ImpossibleActionError on failure).
      2. If decision is not ALLOW, raise ImpossibleActionError — never return a soft string.
      3. Execute the action handler.

    Tools MUST NOT be callable directly. Only Runtime.execute() triggers execution.
    """

    def __init__(self, registry: ActionRegistry, evaluator: Evaluator) -> None:
        self._registry = registry
        self._evaluator = evaluator

    def execute(self, request: ActionRequest) -> Any:
        """
        Execute an ActionRequest through the constrained runtime.

        Raises ImpossibleActionError if the request cannot proceed for any reason.
        Never returns advisory decision strings — enforces or raises.
        """
        decision = self._evaluator.check(request)

        if decision.outcome != DecisionOutcome.ALLOW:
            raise ImpossibleActionError(f"Execution blocked — {decision.reason}")

        return request.action._execute(request.params)


def load_world(path: str = "world.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_runtime(world_path: str = "world.yaml") -> Tuple[Runtime, ActionRegistry]:
    """
    Bootstrap: load world definition, register all actions with handlers,
    and wire together the Runtime.

    Returns (runtime, registry). Callers use registry.get(name) to obtain
    Action objects for building ActionRequests — construction fails immediately
    for any action not defined in world.yaml.
    """
    world = load_world(world_path)
    registry = ActionRegistry()

    handlers = {
        "read_data": lambda params: {"data": params.get("query", ""), "source": "db"},
        "send_email": lambda params: {"sent": True, "to": params.get("to", "")},
        "download_report": lambda params: {"report": params.get("id", ""), "bytes": 0},
        "post_webhook": lambda params: {"status": 200, "url": params.get("url", "")},
    }

    for name, cfg in world["actions"].items():
        action_type = ActionType(cfg["type"])
        approval_required = cfg.get("approval_required", False)
        handler = handlers.get(name, lambda p: {})
        registry.register(name, action_type, handler, approval_required)

    evaluator = Evaluator(world)
    return Runtime(registry, evaluator), registry
