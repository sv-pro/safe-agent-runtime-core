"""
Safe Agent Runtime Core — decision engine.

Evaluates a tool call request against a world definition and returns one of:
  - "allow"            → action is permitted
  - "impossible"       → action cannot be constructed in this world
  - "require_approval" → action exists and is reachable, but needs human sign-off
"""

import yaml


def load_world(path="world.yaml"):
    """Load and return the world definition from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def evaluate(tool_call, world):
    """
    Evaluate a tool call request against the world definition.

    Args:
        tool_call: dict with keys "action", "params", "source"
        world:     dict loaded from world.yaml

    Returns:
        dict with keys "decision" and "reason"
    """
    action = tool_call["action"]
    source = tool_call["source"]

    # Step 1: Check if action exists in the world.
    if action not in world["actions"]:
        return {
            "decision": "impossible",
            "reason": f"Action '{action}' is not defined in this world",
        }

    action_def = world["actions"][action]
    action_type = action_def["type"]

    # Step 2: Determine trust level for the source.
    trust_map = world["trust"]
    defaulted = source not in trust_map
    trust_level = trust_map.get(source, "untrusted")

    # Step 3: Check capability — does this trust level permit the action type?
    allowed_types = world["capabilities"].get(trust_level, [])
    if action_type not in allowed_types:
        default_note = " (source unknown, defaulted to untrusted)" if defaulted else ""
        return {
            "decision": "impossible",
            "reason": (
                f"Source '{source}' (trust: {trust_level}{default_note}) is not permitted "
                f"to perform actions of type '{action_type}'"
            ),
        }

    # Step 4: Apply taint rule — external sources are always tainted.
    tainted = source == "external"
    if tainted and action_type == "external":
        return {
            "decision": "impossible",
            "reason": "Tainted source cannot trigger external side-effects",
        }

    # Step 5: Some actions require explicit human approval before proceeding.
    if action_def.get("approval_required", False):
        return {
            "decision": "require_approval",
            "reason": f"Action '{action}' requires explicit approval before execution",
        }

    # All checks passed.
    return {
        "decision": "allow",
        "reason": f"Action '{action}' is permitted for source '{source}'",
    }
