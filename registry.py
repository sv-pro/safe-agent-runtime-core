from dataclasses import dataclass
from typing import Any, Callable, Dict

from models import ActionType, ImpossibleActionError, Source, TaintState


class Action:
    """
    A registered, typed action with an execution handler.

    Actions MUST be obtained from ActionRegistry.get().
    Direct instantiation is possible but bypasses the registry contract —
    use the registry to ensure only world-defined actions can be constructed.
    """

    def __init__(
        self,
        name: str,
        action_type: ActionType,
        handler: Callable[[Dict[str, Any]], Any],
        approval_required: bool = False,
    ) -> None:
        self.name = name
        self.action_type = action_type
        self._handler = handler
        self.approval_required = approval_required

    def _execute(self, params: Dict[str, Any]) -> Any:
        """Execute the action handler. Only Runtime may call this."""
        return self._handler(params)

    def __repr__(self) -> str:
        return f"Action(name={self.name!r}, type={self.action_type.value!r})"


@dataclass
class ActionRequest:
    """
    Typed ingress for all runtime execution requests.
    No raw dicts allowed — parsing and validation happen before evaluation.
    """

    action: Action
    source: Source
    params: Dict[str, Any]
    taint: TaintState


class ActionRegistry:
    """
    Closed registry of world-defined actions.

    Attempting to construct an Action not present in the registry
    raises ImpossibleActionError at call time — construction fails,
    not execution.
    """

    def __init__(self) -> None:
        self._actions: Dict[str, Action] = {}

    def register(
        self,
        name: str,
        action_type: ActionType,
        handler: Callable[[Dict[str, Any]], Any],
        approval_required: bool = False,
    ) -> Action:
        action = Action(name, action_type, handler, approval_required)
        self._actions[name] = action
        return action

    def get(self, name: str) -> Action:
        """
        Retrieve a registered action by name.

        Raises ImpossibleActionError if the action is not in the registry.
        The action cannot be constructed — it is impossible, not denied.
        """
        if name not in self._actions:
            raise ImpossibleActionError(
                f"Action '{name}' is not in the registry — construction failed"
            )
        return self._actions[name]

    def __contains__(self, name: str) -> bool:
        return name in self._actions
