"""
Core types for the ontology runtime.

ActionDefinition — immutable description of an action in the ontology.
ActionRequest    — typed execution request; runtime only accepts this, never raw dicts.
ExecutionResult  — structured outcome of runtime.execute().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionDefinition:
    """
    A single action defined in the world ontology.

    Produced by world_loader at startup. The existence of an ActionDefinition
    object proves the action was present in world.yaml — there is no other
    way to obtain one.
    """

    name: str
    action_type: str       # "internal" | "external"
    params: tuple          # required parameter names
    handler: str           # key into runtime handler table
    requires_approval: bool = False


@dataclass
class ActionRequest:
    """
    A typed execution request.

    The runtime core only operates on ActionRequest — never on raw dicts,
    strings, or natural language. Constructing an ActionRequest requires
    a valid ActionDefinition, so unknown actions cannot reach the runtime.

    taint=True means the request carries data from an untrusted origin.
    Taint can be set explicitly (trusted source, tainted data) or derived
    automatically from the source identity by the registry.
    """

    action: ActionDefinition
    source: str
    params: dict
    taint: bool = False


@dataclass
class ExecutionResult:
    """
    Structured outcome of runtime.execute().

    decision is either "allow" or "require_approval".
    There is no "deny" outcome — impossible actions raise before reaching here.
    """

    decision: str          # "allow" | "require_approval"
    action: str
    output: Any = None
