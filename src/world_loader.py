"""
World loader — compile world.yaml into a live ActionRegistry and policy dict.

Reads world.yaml exactly once. Returns:
  registry : ActionRegistry   — closed ontology, used to construct requests
  world    : dict             — raw policy for trust, capabilities, taint rules

After load_world() returns, world.yaml is not accessed by any runtime component.
"""

from __future__ import annotations

import yaml

from .registry import ActionRegistry
from .types import ActionDefinition


def load_world(path: str = "world.yaml") -> tuple[ActionRegistry, dict]:
    with open(path) as f:
        world: dict = yaml.safe_load(f)

    registry = ActionRegistry()
    for name, defn in world["actions"].items():
        registry.register(
            ActionDefinition(
                name=name,
                action_type=defn["type"],
                params=tuple(defn.get("params") or []),
                handler=name,
                requires_approval=bool(defn.get("requires_approval", False)),
            )
        )

    return registry, world
