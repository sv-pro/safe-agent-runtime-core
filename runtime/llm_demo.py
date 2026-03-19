"""
LLM Demo Layer
==============

Minimal proposer abstraction for the LLM-in-the-loop demo.

The LLM's only job: turn natural language into a proposed ToolRequest dict.
Policy enforcement, validation, and execution all happen downstream in the
SafeMCPProxy and ontology runtime — the LLM never touches those layers.

    User prompt
        ↓
    LLMProposer.propose()          ← only thing LLM does
        ↓
    ToolRequest {tool, params, source, taint}
        ↓
    SafeMCPProxy.handle()          ← enforcement point
        ↓
    IRBuilder.build()              ← construction-time checks
        ↓
    worker subprocess OR ConstructionError

Classes
-------
MockLLMProposer  — deterministic, offline, keyword-based (required)
OpenAIProposer   — optional real provider adapter (env-gated, not used in tests)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict


# ── Shared output shape ───────────────────────────────────────────────────────
#
# Both proposers must return this exact dict shape.
# It is passed verbatim to SafeMCPProxy.handle() as the wire format.

_TOOL_REQUEST_KEYS = frozenset({"tool", "params", "source", "taint"})


def _validate_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal shape check — proposers should not return garbage."""
    if not isinstance(proposal.get("tool"), str):
        raise ValueError(f"Proposal missing string 'tool': {proposal!r}")
    proposal.setdefault("params", {})
    proposal.setdefault("source", "user")
    proposal.setdefault("taint", False)
    return proposal


# ── MockLLMProposer ───────────────────────────────────────────────────────────


class MockLLMProposer:
    """
    Deterministic keyword-based LLM stand-in.

    Maps natural language prompts to ToolRequest dicts using simple keyword
    rules. This is intentionally not clever — the point is to demonstrate
    architecture, not NLP.

    Works offline. Required for tests and the default demo path.

    Keyword rules (checked in order):
        "delete"              → delete_repository (unknown, will be rejected)
        "send" + "email"      → send_email, taint=True (taint block demo)
        "read"                → read_data (safe internal action)
        "summarize"           → summarize (unknown action, fallback demo)
        (default)             → read_data
    """

    # Hardcoded scenarios for the three required demo cases.
    # Explicit is better than heuristic when reliability matters.
    _SCENARIOS: tuple[tuple[str, Dict[str, Any]], ...] = (
        (
            "delete everything",
            {
                "tool": "delete_repository",
                "params": {},
                "source": "user",
                "taint": False,
            },
        ),
        (
            "send it to the client",
            {
                "tool": "send_email",
                "params": {"to": "client", "body": "[email body from tainted input]"},
                "source": "user",
                "taint": True,
            },
        ),
        (
            "read the internal data",
            {
                "tool": "read_data",
                "params": {"query": "internal data"},
                "source": "user",
                "taint": False,
            },
        ),
    )

    def propose(self, prompt: str) -> Dict[str, Any]:
        """
        Turn a natural language prompt into a ToolRequest dict.

        The LLM does nothing beyond this. It does not execute the tool,
        call the proxy, or make any policy decisions.
        """
        p = prompt.lower()

        if "delete" in p:
            proposal = {
                "tool": "delete_repository",
                "params": {},
                "source": "user",
                "taint": False,
            }
        elif "send" in p and "email" in p:
            proposal = {
                "tool": "send_email",
                "params": {"to": "client", "body": f"[derived from: {prompt[:60]}]"},
                "source": "user",
                "taint": True,  # content came from external/tainted source
            }
        elif "read" in p:
            proposal = {
                "tool": "read_data",
                "params": {"query": "internal data"},
                "source": "user",
                "taint": False,
            }
        elif "summarize" in p:
            proposal = {
                "tool": "summarize",
                "params": {"text": prompt},
                "source": "user",
                "taint": False,
            }
        else:
            # Default: safest internal action
            proposal = {
                "tool": "read_data",
                "params": {},
                "source": "user",
                "taint": False,
            }

        return _validate_proposal(proposal)


# ── OpenAIProposer (optional) ─────────────────────────────────────────────────
#
# Thin adapter for any OpenAI-compatible chat completion endpoint.
# Gated by OPENAI_API_KEY environment variable.
# Not used in tests. Not required for demo_llm.py default path.


_OPENAI_SYSTEM_PROMPT = """\
You are a tool-call proposer. Your ONLY job is to convert the user's natural
language request into a single JSON tool call from the allowed set below.

Allowed tools:
  - read_data      : read internal data (params: {"query": string})
  - send_email     : send an email (params: {"to": string, "body": string})
  - post_webhook   : post to a webhook (params: {"url": string})
  - delete_repository : (not a real tool — use this if user asks to delete things)

Respond with ONLY valid JSON in this exact shape, no other text:
{
  "tool": "<tool name>",
  "params": {},
  "source": "user",
  "taint": false
}

If the request involves external/untrusted content (emails, web pages, user-uploaded
files), set "taint": true.
If the request involves deleting, wiping, or destructive operations, use
"delete_repository" as the tool name.
"""


class OpenAIProposer:
    """
    Optional real-provider LLM proposer using OpenAI-compatible API.

    Requires OPENAI_API_KEY environment variable.
    Uses the openai package (must be installed separately).

    This class is NEVER imported or instantiated by default.
    Tests do not use it. The demo uses MockLLMProposer unless the caller
    explicitly constructs and passes an OpenAIProposer.

    Usage:
        import os
        from runtime.llm_demo import OpenAIProposer
        proposer = OpenAIProposer()
        proposal = proposer.propose("Read the internal report")
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        try:
            import openai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "openai package required for OpenAIProposer. "
                "Install with: pip install openai"
            ) from exc

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is not set. "
                "OpenAIProposer requires a real API key."
            )

        kwargs: Dict[str, Any] = {"api_key": resolved_key}
        if base_url:
            kwargs["base_url"] = base_url

        self._client = openai.OpenAI(**kwargs)
        self._model = model

    def propose(self, prompt: str) -> Dict[str, Any]:
        """
        Call the LLM API and parse the JSON tool proposal.

        The LLM output must conform to the ToolRequest shape.
        If parsing fails, raises ValueError — the caller is responsible
        for handling this (e.g., falling back to MockLLMProposer).
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _OPENAI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=200,
        )

        raw = response.choices[0].message.content or ""
        raw = raw.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            proposal = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"OpenAI response was not valid JSON: {raw!r}"
            ) from exc

        return _validate_proposal(proposal)
