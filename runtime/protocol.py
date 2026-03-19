"""
Proxy Protocol Types
====================

Defines the thin surface between external tool requests and the ontology runtime.

ToolRequest   — incoming dict from an agent/LLM client (proxy input format)
ProxyResponse — structured result returned to the caller

These types translate the external "tool" vocabulary into the runtime's
typed model. The proxy layer uses them; the runtime core never sees them.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ToolRequest:
    """
    Incoming tool request from an agent or LLM client.

    This is the external format. It uses 'tool' (not 'action'), carries a
    simple boolean taint flag, and uses a string identity for the source.
    The proxy translates this into the runtime's typed model.
    """

    __slots__ = ("tool", "params", "source", "taint")

    def __init__(
        self,
        tool: str,
        params: Dict[str, Any],
        source: str,
        taint: bool = False,
    ) -> None:
        self.tool = tool
        self.params = params
        self.source = source
        self.taint = taint

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ToolRequest":
        """Construct a ToolRequest from a raw dict (the external wire format)."""
        return ToolRequest(
            tool=d["tool"],
            params=d.get("params", {}),
            source=d.get("source", "external"),
            taint=bool(d.get("taint", False)),
        )

    def __repr__(self) -> str:
        return (
            f"ToolRequest(tool={self.tool!r}, source={self.source!r}, "
            f"taint={self.taint!r}, params={self.params!r})"
        )


class ProxyResponse:
    """
    Structured result from the proxy.

    status values:
        "ok"               — action executed successfully; result is available
        "impossible"       — action cannot be constructed (ontological absence,
                             taint violation, or capability mismatch)
        "require_approval" — action requires approval (deferred in this runtime)
    """

    __slots__ = ("status", "action", "result", "reason")

    def __init__(
        self,
        status: str,
        action: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.status = status
        self.action = action
        self.result = result
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"status": self.status}
        if self.action is not None:
            d["action"] = self.action
        if self.result is not None:
            d["result"] = self.result
        if self.reason is not None:
            d["reason"] = self.reason
        return d

    def __repr__(self) -> str:
        return f"ProxyResponse({self.to_dict()!r})"
