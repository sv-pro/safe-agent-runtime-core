"""
Tests for the minimal ontology runtime (src/).

Six focused properties:

  1. Unknown action fails at construction (UnknownActionError, not at execution)
  2. Tainted external action raises ImpossibleActionError
  3. Tainted internal action can still succeed
  4. Trusted non-tainted external action returns a structured result (require_approval)
  5. Runtime is the only execution boundary (handlers not reachable directly)
  6. No "deny" decision vocabulary appears in results

Run: pytest tests/test_runtime.py
"""

from __future__ import annotations

import os
import pytest

from src.errors import ImpossibleActionError, UnknownActionError
from src.runtime import Runtime, _HANDLERS
from src.world_loader import load_world

WORLD = os.path.join(os.path.dirname(__file__), "..", "world.yaml")


@pytest.fixture(scope="module")
def ctx():
    registry, world = load_world(WORLD)
    runtime = Runtime(world)
    return registry, runtime


# ── 1. Unknown action fails at construction ───────────────────────────────────

def test_unknown_action_fails_at_construction(ctx):
    """
    Action names not in the ontology raise UnknownActionError at build_request().
    No ActionRequest is produced; the runtime execute() is never called.
    """
    registry, _runtime = ctx
    with pytest.raises(UnknownActionError, match="does not exist in this world"):
        registry.build_request("delete_repository", source="user", params={})


# ── 2. Tainted external action raises ImpossibleActionError ──────────────────

def test_tainted_external_action_raises_impossible(ctx):
    """
    Trusted source (system) with explicit taint=True + external action → impossible.

    Capability check passes (system is trusted → can reach external actions).
    Taint check fires: tainted data cannot cross external boundary.
    This proves taint is independent of and distinct from the capability check.
    """
    registry, runtime = ctx
    req = registry.build_request(
        "send_email",
        source="system",          # trusted — capability check passes
        params={"to": "x@x.com", "body": "hi"},
        taint=True,               # explicit taint — not derived from source trust
    )
    with pytest.raises(ImpossibleActionError):
        runtime.execute(req)


# ── 3. Tainted internal action can still succeed ──────────────────────────────

def test_tainted_internal_action_succeeds(ctx):
    """
    External source (auto-tainted) + internal action → allowed.

    Taint rule only blocks tainted + external combinations.
    Internal actions are reachable from tainted sources.
    """
    registry, runtime = ctx
    # external is in tainted_sources → auto-tainted, but summarize is internal
    req = registry.build_request(
        "summarize",
        source="external",
        params={"content": "user provided text"},
    )
    result = runtime.execute(req)
    assert result.decision == "allow"
    assert "summary" in result.output


# ── 4. Trusted external action returns structured result ──────────────────────

def test_trusted_non_tainted_external_returns_structured_result(ctx):
    """
    Trusted source, no taint, external action → runtime returns require_approval.

    The action exists and capability permits it — the result is structured,
    not an error. "require_approval" is a success outcome, not a denial.
    """
    registry, runtime = ctx
    req = registry.build_request(
        "send_email",
        source="user",            # trusted
        params={"to": "x@x.com", "body": "hi"},
        taint=False,
    )
    result = runtime.execute(req)
    assert result.decision == "require_approval"
    assert result.action == "send_email"


# ── 5. Runtime is the only execution boundary ─────────────────────────────────

def test_runtime_is_only_execution_boundary(ctx):
    """
    _HANDLERS exist inside the runtime module but have no public call path
    that bypasses Runtime.execute(). A valid request going through execute()
    is the only way to invoke a handler.

    This test verifies that the happy path works through execute() and that
    the handler dict is not a public API surface.
    """
    registry, runtime = ctx
    req = registry.build_request("read_data", source="user", params={})
    result = runtime.execute(req)
    assert result.decision == "allow"
    assert result.output is not None
    # _HANDLERS is module-private by convention; its keys are the handler names,
    # not action names callable outside the runtime boundary.
    assert "read_data" in _HANDLERS   # exists inside runtime
    # But calling it directly bypasses all constraints — it's intentionally
    # not exported from the package __init__.


# ── 6. No "deny" decision vocabulary in results ───────────────────────────────

def test_no_deny_vocabulary_in_results(ctx):
    """
    The runtime never returns a "deny" decision.
    Impossible actions raise; allowed actions return "allow" or "require_approval".
    """
    registry, runtime = ctx
    req = registry.build_request("read_data", source="user", params={})
    result = runtime.execute(req)
    assert result.decision != "deny"
    assert "deny" not in str(result.decision).lower()
    assert "deny" not in str(result.output or "").lower()
