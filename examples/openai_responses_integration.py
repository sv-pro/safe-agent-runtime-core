#!/usr/bin/env python3
"""
OpenAI Responses API Integration
=================================

Demonstrates wiring SafeMCPProxy as the enforcement layer beneath
the OpenAI Responses API (not Assistants). Tool calls from the model
are routed through the proxy before reaching the runtime.

Run:
    export OPENAI_API_KEY=...
    python examples/openai_responses_integration.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy

rt = build_runtime()
proxy = SafeMCPProxy(rt)
client = openai.OpenAI()

TOOLS = [
    {
        "type": "function",
        "name": "read_data",
        "description": "Read internal data from the data store.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "summarize",
        "description": "Summarize the given content string.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to summarize."},
            },
            "required": ["content"],
        },
    },
    {
        "type": "function",
        "name": "send_email",
        "description": "Send an email to the given address with the given body.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "body": {"type": "string", "description": "Email body text."},
            },
            "required": ["to", "body"],
        },
    },
]


def execute_tool_call(tool_name: str, arguments: dict, taint: bool = False) -> dict:
    response = proxy.handle({
        "tool": tool_name,
        "params": arguments,
        "source": "user",
        "taint": taint,
    })
    if response.status != "ok":
        return {"error": response.reason}
    return response.result


def main() -> None:
    response = client.responses.create(
        model="gpt-5",
        input="Read the internal data and summarize it.",
        tools=TOOLS,
    )

    tool_outputs = []
    for item in response.output:
        if item.type == "function_call":
            arguments = json.loads(item.arguments)
            result = execute_tool_call(item.name, arguments)
            tool_outputs.append({
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(result),
            })

    if tool_outputs:
        follow_up = client.responses.create(
            model="gpt-5",
            input=tool_outputs,
            tools=TOOLS,
        )
        print(follow_up.output_text)
    else:
        print(response.output_text)


if __name__ == "__main__":
    main()
