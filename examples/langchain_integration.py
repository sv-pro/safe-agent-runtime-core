#!/usr/bin/env python3
"""
LangChain Integration
=====================

Demonstrates wiring SafeMCPProxy as the enforcement layer beneath
LangChain tools. Every tool call from the agent passes through the proxy
before reaching the runtime — no side door to execution.

Run:
    python examples/langchain_integration.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy

rt = build_runtime()
proxy = SafeMCPProxy(rt)


@tool
def read_data() -> dict:
    """Read internal data from the data store."""
    response = proxy.handle({
        "tool": "read_data",
        "params": {},
        "source": "user",
        "taint": False,
    })
    if response.status != "ok":
        raise RuntimeError(response.reason)
    return response.result


@tool
def summarize(content: str) -> dict:
    """Summarize the given content string."""
    response = proxy.handle({
        "tool": "summarize",
        "params": {"content": content},
        "source": "user",
        "taint": False,
    })
    if response.status != "ok":
        raise RuntimeError(response.reason)
    return response.result


@tool
def send_email(to: str, body: str) -> dict:
    """Send an email to the given address with the given body."""
    response = proxy.handle({
        "tool": "send_email",
        "params": {"to": to, "body": body},
        "source": "user",
        "taint": False,
    })
    if response.status != "ok":
        raise RuntimeError(response.reason)
    return response.result


def main() -> None:
    model = init_chat_model("gpt-5", model_provider="openai")
    agent = create_react_agent(
        model=model,
        tools=[read_data, summarize, send_email],
    )

    result = agent.invoke({
        "messages": [{"role": "user", "content": "Read the internal data and summarize it."}]
    })

    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
