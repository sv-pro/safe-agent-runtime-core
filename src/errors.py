"""
Typed exceptions for the ontology runtime.

UnknownActionError  — raised when an action name is not in the ontology.
                      This happens at request construction, not at execution.
                      The action does not exist; it is not denied.

ImpossibleActionError — raised when a valid action cannot be executed given
                        current world constraints (capability or taint).
                        The action cannot happen; it is not blocked.
"""


class UnknownActionError(Exception):
    """Action name is absent from the compiled ontology."""


class ImpossibleActionError(Exception):
    """Action exists but cannot be constructed in this world context."""
