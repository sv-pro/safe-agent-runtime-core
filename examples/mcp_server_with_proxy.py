#!/usr/bin/env python3
"""
MCP Server with SafeMCPProxy
=============================

Exposes read_data, summarize, and send_email as MCP tools, routing every
call through SafeMCPProxy before it reaches the runtime. Construction-time
constraints are enforced before any action reaches execution.

Run:
    python examples/mcp_server_with_proxy.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy

rt = build_runtime()
proxy = SafeMCPProxy(rt)

mcp = FastMCP("SafeProxyTools", json_response=True)


@mcp.tool()
def read_data() -> dict:
    """Read internal data from the data store."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    if response.status != "ok":
        return {"status": response.status, "reason": response.reason}
    return response.result


@mcp.tool()
def summarize(content: str) -> dict:
    """Summarize the given content string."""
    response = proxy.handle({
        "tool": "summarize",
        "params": {"content": content},
        "source": "user",
        "taint": False,
    })
    if response.status != "ok":
        return {"status": response.status, "reason": response.reason}
    return response.result


@mcp.tool()
def send_email(to: str, body: str, tainted: bool = False) -> dict:
    """Send an email to the given address with the given body."""
    response = proxy.handle({
        "tool": "send_email",
        "params": {"to": to, "body": body},
        "source": "user",
        "taint": tainted,
    })
    if response.status != "ok":
        return {"status": response.status, "reason": response.reason}
    return response.result


if __name__ == "__main__":
    mcp.run()
