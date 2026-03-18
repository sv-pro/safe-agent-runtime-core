"""
Action registry — the closed ontology lookup.

ActionRegistry holds the set of actions that exist in this world.
build_request() is the only way to produce an ActionRequest — it resolves
the ActionDefinition by name and raises UnknownActionError if absent.

Unknown action names cannot be smuggled into the runtime via strings;
they fail here, at request construction time.
"""

from .errors import UnknownActionError
from .types import ActionDefinition, ActionRequest


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionDefinition] = {}

    def register(self, action: ActionDefinition) -> None:
        self._actions[action.name] = action

    def get(self, name: str) -> ActionDefinition:
        if name not in self._actions:
            raise UnknownActionError(
                f"Action '{name}' does not exist in this world"
            )
        return self._actions[name]

    def build_request(
        self,
        action_name: str,
        source: str,
        params: dict,
        taint: bool = False,
    ) -> ActionRequest:
        """
        Construct a typed ActionRequest.

        Raises UnknownActionError immediately if action_name is absent from
        the ontology — the action cannot be constructed, not merely rejected.
        """
        action = self.get(action_name)
        return ActionRequest(action=action, source=source, params=params, taint=taint)
