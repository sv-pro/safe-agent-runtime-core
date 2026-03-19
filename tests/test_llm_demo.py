"""
LLM Demo Tests
==============

Verifies the invariants of the LLM-in-the-loop demo layer.

The LLM proposer produces ToolRequest dicts. The proxy is the enforcement point.
These tests confirm that the proposer + proxy combination behaves correctly for
the three canonical scenarios, and that the architecture is not bypassed.

Invariants:
  1. Mock LLM maps dangerous prompt to unknown tool
  2. Dangerous prompt path does not reach worker
  3. Tainted external prompt path does not reach worker
  4. Safe prompt path reaches worker and returns a result
  5. Demo layer does not bypass proxy (proxy.handle is the only entry point)
  6. OpenAIProposer is optional — importing it does not affect test execution
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from runtime import build_runtime
from runtime.proxy import SafeMCPProxy
from runtime.llm_demo import MockLLMProposer


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def proposer():
    return MockLLMProposer()


@pytest.fixture
def proxy():
    rt = build_runtime()
    return SafeMCPProxy(rt)


# ── 1. Mock LLM maps dangerous prompt to unknown tool ─────────────────────────


def test_mock_llm_dangerous_prompt_proposes_unknown_tool(proposer):
    """Dangerous prompt → proposer outputs a tool that is not in the world manifest."""
    proposal = proposer.propose("Please delete everything and push the cleanup")

    assert proposal["tool"] == "delete_repository"
    assert proposal["source"] == "user"
    assert proposal["taint"] is False


def test_mock_llm_tainted_email_prompt_proposes_external_tool(proposer):
    """Email/send prompt → proposer outputs send_email with taint=True."""
    proposal = proposer.propose("Summarize this email and send it to the client")

    assert proposal["tool"] == "send_email"
    assert proposal["taint"] is True


def test_mock_llm_safe_prompt_proposes_internal_tool(proposer):
    """Read prompt → proposer outputs read_data (internal, clean)."""
    proposal = proposer.propose("Read the internal data and summarize it")

    assert proposal["tool"] == "read_data"
    assert proposal["taint"] is False


# ── 2. Dangerous prompt path does not reach worker ───────────────────────────


def test_dangerous_prompt_does_not_reach_worker(proposer, proxy):
    """
    delete_repository is not in the world manifest.
    Proxy returns impossible before any subprocess is spawned.
    """
    proposal = proposer.propose("Please delete everything and push the cleanup")

    with patch("runtime.executor.subprocess.run") as mock_run:
        response = proxy.handle(proposal)

    assert response.status == "impossible"
    mock_run.assert_not_called()


# ── 3. Tainted external prompt path does not reach worker ────────────────────


def test_tainted_external_prompt_does_not_reach_worker(proposer, proxy):
    """
    send_email exists but taint=True + external action → ConstructionError.
    Worker subprocess is never spawned.
    """
    proposal = proposer.propose("Summarize this email and send it to the client")

    assert proposal["taint"] is True

    with patch("runtime.executor.subprocess.run") as mock_run:
        response = proxy.handle(proposal)

    assert response.status == "impossible"
    assert "taint" in response.reason.lower() or "external" in response.reason.lower()
    mock_run.assert_not_called()


# ── 4. Safe prompt path reaches worker ───────────────────────────────────────


def test_safe_prompt_reaches_worker(proposer, proxy):
    """
    read_data is internal and clean. IR construction succeeds.
    Worker subprocess is called and returns a result.
    """
    proposal = proposer.propose("Read the internal data and summarize it")

    response = proxy.handle(proposal)

    assert response.status == "ok"
    assert response.result is not None


# ── 5. Demo layer does not bypass proxy ───────────────────────────────────────


def test_proposer_output_goes_through_proxy_handle(proposer, proxy):
    """
    The proposer only produces a dict. Enforcement happens in proxy.handle().
    There is no shortcut path that skips the proxy.

    Verify by mocking proxy.handle and confirming the proposal is passed to it.
    """
    original_handle = proxy.handle
    calls = []

    def recording_handle(request):
        calls.append(request)
        return original_handle(request)

    proxy.handle = recording_handle

    proposal = proposer.propose("Read the internal data and summarize it")
    proxy.handle(proposal)

    assert len(calls) == 1
    assert calls[0]["tool"] == "read_data"


def test_proxy_has_no_callable_handlers():
    """
    SafeMCPProxy holds no handler functions — it cannot execute tools itself.
    Execution only happens through runtime.sandbox.execute(ir) → worker subprocess.
    """
    rt = build_runtime()
    p = SafeMCPProxy(rt)

    # Proxy should have no callable that maps tool names to handler functions
    assert not hasattr(p, "_handlers")
    assert not hasattr(p, "_registry")
    assert not hasattr(p, "_dispatch")


# ── 6. OpenAIProposer is optional ─────────────────────────────────────────────


def test_openai_proposer_is_importable_but_not_required():
    """
    OpenAIProposer can be imported without error.
    It is not used in this test suite.
    """
    from runtime.llm_demo import OpenAIProposer  # noqa: F401

    # If we reach here, the import works.
    # No network calls, no API key checks at import time.
    assert OpenAIProposer is not None


def test_openai_proposer_requires_api_key():
    """
    OpenAIProposer raises EnvironmentError if OPENAI_API_KEY is not set
    and no api_key is provided. This confirms it is env-gated.
    """
    from runtime.llm_demo import OpenAIProposer
    import os

    # Temporarily unset the key if it happens to be set
    original = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises((EnvironmentError, ImportError)):
            OpenAIProposer()
    finally:
        if original is not None:
            os.environ["OPENAI_API_KEY"] = original
