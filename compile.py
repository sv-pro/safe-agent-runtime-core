"""
Compile Phase
=============

Transforms world_manifest.yaml into an immutable CompiledPolicy.

This runs ONCE at startup via build_runtime(). After compilation:
  - world_manifest.yaml is not accessed by any runtime component
  - All policy decisions live in frozen Python data structures
  - No string comparisons, no YAML parsing, no dict iteration at request time

Compile outputs:
  actions:           MappingProxyType[str, CompiledAction]
                     Sealed — CallerCode cannot add or modify entries.
  capability_matrix: frozenset[tuple[TrustLevel, ActionType]]
                     O(1) membership test — no loops, no strings.
  taint_rules:       tuple[TaintRule, ...]
                     Immutable ordered sequence.
  trust_map:         MappingProxyType[str, TrustLevel]
                     Channel identity → TrustLevel, resolved at IR build time.

Sealing mechanism for CompiledAction:
  _COMPILE_GATE is a module-private object() sentinel. CompiledAction.__init__
  checks that the caller passed _COMPILE_GATE as the _gate argument. External
  code cannot import _COMPILE_GATE (it is module-private by naming convention
  and is not exported). This makes CompiledAction construction outside the
  compile phase a TypeError at runtime, catching accidental bypass immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, FrozenSet, Optional, Tuple

import yaml

from models import ActionType, TaintState, TrustLevel


# ── Module-private compile gate ───────────────────────────────────────────────
# This object is never exported. CompiledAction refuses construction without it.
# The only code that holds a reference to _COMPILE_GATE is compile_world().
_COMPILE_GATE: object = object()


# ── TaintRule ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaintRule:
    """An immutable compiled taint rule."""
    taint: TaintState
    action_type: ActionType
    reason: str


# ── CompiledAction ────────────────────────────────────────────────────────────

class CompiledAction:
    """
    A sealed, immutable action produced by the compile phase.

    The only way to obtain a CompiledAction is from the CompiledPolicy
    returned by compile_world(). Attempting to construct one externally
    raises TypeError immediately — at object creation, not at execution.

    The existence of a CompiledAction object is proof that the action
    was present in world_manifest.yaml at compile time.
    """

    __slots__ = ("name", "action_type", "approval_required", "_handler")

    def __init__(
        self,
        name: str,
        action_type: ActionType,
        handler: Callable[[Dict[str, Any]], Any],
        approval_required: bool,
        _gate: object,
    ) -> None:
        if _gate is not _COMPILE_GATE:
            raise TypeError(
                "CompiledAction cannot be constructed outside the compile phase. "
                "Obtain actions from CompiledPolicy.actions."
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(self, "approval_required", approval_required)
        object.__setattr__(self, "_handler", handler)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CompiledAction is immutable after construction")

    def _invoke(self, params: Dict[str, Any]) -> Any:
        """
        Invoke the action handler.

        Only Sandbox.execute() should call this. The underscore prefix is a
        module-boundary signal. In Python, structural enforcement requires
        keeping handlers inside the sandbox layer — enforced by architecture,
        not by access control (Python has no true private methods).
        """
        return self._handler(params)

    def __repr__(self) -> str:
        return f"CompiledAction({self.name!r}, type={self.action_type.value!r})"

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompiledAction):
            return NotImplemented
        return self.name == other.name


# ── CompiledPolicy ────────────────────────────────────────────────────────────

class CompiledPolicy:
    """
    Immutable compiled policy produced by compile_world().

    All fields are frozen after construction:
      - MappingProxyType: read-only dict view
      - frozenset: immutable by construction
      - tuple: immutable by construction

    All capability lookups are O(1) frozenset membership tests.
    No YAML parsing, no string iteration, no dynamic rule evaluation
    occurs after compile_world() returns.
    """

    __slots__ = ("_actions", "_capability_matrix", "_taint_rules", "_trust_map")

    def __init__(
        self,
        actions: Dict[str, CompiledAction],
        capability_matrix: FrozenSet[Tuple[TrustLevel, ActionType]],
        taint_rules: Tuple[TaintRule, ...],
        trust_map: Dict[str, TrustLevel],
    ) -> None:
        object.__setattr__(self, "_actions", MappingProxyType(actions))
        object.__setattr__(self, "_capability_matrix", capability_matrix)
        object.__setattr__(self, "_taint_rules", taint_rules)
        object.__setattr__(self, "_trust_map", MappingProxyType(trust_map))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CompiledPolicy is immutable after construction")

    # ── Action access (read-only proxy) ───────────────────────────────────────

    @property
    def actions(self) -> MappingProxyType:
        """Read-only view of compiled actions. Cannot be mutated."""
        return self._actions

    def get_action(self, name: str) -> Optional[CompiledAction]:
        """Return the CompiledAction for name, or None if not in the ontology."""
        return self._actions.get(name)

    # ── Capability check (O(1) frozenset lookup) ──────────────────────────────

    def can_perform(self, trust_level: TrustLevel, action_type: ActionType) -> bool:
        """
        True iff (trust_level, action_type) is in the compiled capability matrix.

        This is an O(1) frozenset membership test. No string comparison.
        No loop. No YAML dict lookup. The matrix was compiled once and frozen.
        """
        return (trust_level, action_type) in self._capability_matrix

    # ── Taint rule lookup ─────────────────────────────────────────────────────

    def taint_rule_for(
        self, taint: TaintState, action_type: ActionType
    ) -> Optional[TaintRule]:
        """Return the first matching taint rule, or None."""
        for rule in self._taint_rules:
            if rule.taint is taint and rule.action_type is action_type:
                return rule
        return None

    # ── Trust resolution ──────────────────────────────────────────────────────

    def resolve_trust(self, channel_identity: str) -> TrustLevel:
        """
        Resolve a channel identity to its compiled TrustLevel.

        Fail-secure default: unknown identities resolve to UNTRUSTED.
        This is a compiled dict lookup — not a YAML string scan.
        """
        return self._trust_map.get(channel_identity, TrustLevel.UNTRUSTED)

    def __repr__(self) -> str:
        return (
            f"CompiledPolicy("
            f"actions={list(self._actions)}, "
            f"matrix={self._capability_matrix})"
        )


# ── compile_world ─────────────────────────────────────────────────────────────

def compile_world(
    manifest_path: str,
    handlers: Dict[str, Callable[[Dict[str, Any]], Any]],
) -> CompiledPolicy:
    """
    Compile phase entry point.

    Reads world_manifest.yaml exactly once. Produces an immutable
    CompiledPolicy. After this function returns, the YAML file is not
    accessed again by any runtime component.

    Parameters
    ----------
    manifest_path : str
        Path to world_manifest.yaml.
    handlers : dict
        Action name → callable. Defines the tools that exist inside the
        sandbox. Actions in the manifest without a handler get a no-op.
        These handlers are the ONLY tools that can ever be executed —
        they are not globally callable, only reachable through Sandbox.execute().
    """
    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    # ── Compile actions ───────────────────────────────────────────────────────
    actions: Dict[str, CompiledAction] = {}
    for name, cfg in raw["actions"].items():
        action_type = ActionType(cfg["type"])
        approval_required = bool(cfg.get("approval_required", False))
        handler = handlers.get(name, lambda p: {})
        actions[name] = CompiledAction(
            name=name,
            action_type=action_type,
            handler=handler,
            approval_required=approval_required,
            _gate=_COMPILE_GATE,
        )

    # ── Compile capability matrix → frozenset[(TrustLevel, ActionType)] ───────
    # The old system did: `if action_type.value not in capabilities[trust_level]`
    # which is a runtime string list scan. This compiles it to a frozenset so
    # the check becomes a single O(1) membership test with no strings.
    raw_capabilities: Dict[str, list] = raw.get("capabilities", {})
    capability_matrix: FrozenSet[Tuple[TrustLevel, ActionType]] = frozenset(
        (TrustLevel(trust_str), ActionType(action_type_str))
        for trust_str, action_type_strs in raw_capabilities.items()
        for action_type_str in action_type_strs
    )

    # ── Compile taint rules → tuple[TaintRule, ...] ───────────────────────────
    raw_taint_rules: list = raw.get("taint_rules", [])
    taint_rules: Tuple[TaintRule, ...] = tuple(
        TaintRule(
            taint=TaintState(rule["taint"]),
            action_type=ActionType(rule["action_type"]),
            reason=rule["reason"],
        )
        for rule in raw_taint_rules
    )

    # ── Compile trust map → MappingProxyType[str, TrustLevel] ────────────────
    # The old system did: `self._trust.get(source.name, "untrusted")` — a string
    # lookup that returned a string. Now it returns a TrustLevel enum value,
    # used in the frozenset capability check without any string conversion.
    raw_trust: Dict[str, str] = raw.get("trust", {})
    trust_map: Dict[str, TrustLevel] = {
        identity: TrustLevel(trust_str)
        for identity, trust_str in raw_trust.items()
    }

    return CompiledPolicy(
        actions=actions,
        capability_matrix=capability_matrix,
        taint_rules=taint_rules,
        trust_map=trust_map,
    )
