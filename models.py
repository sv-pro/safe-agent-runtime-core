from dataclasses import dataclass
from enum import Enum


class TaintState(Enum):
    CLEAN = "clean"
    TAINTED = "tainted"


class ActionType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class DecisionOutcome(Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class Source:
    name: str


@dataclass
class Decision:
    outcome: DecisionOutcome
    reason: str


class ImpossibleActionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"ImpossibleActionError: {reason}")
