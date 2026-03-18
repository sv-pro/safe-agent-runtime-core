"""
Unit tests for the Safe Agent Runtime Core decision engine.
"""

import pytest
import yaml
import os

from runtime import evaluate

# ---------------------------------------------------------------------------
# Fixture: minimal world loaded from the project's world.yaml
# ---------------------------------------------------------------------------

WORLD_YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "world.yaml")


@pytest.fixture
def world():
    with open(WORLD_YAML_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_call(action, source, params=None):
    return {"action": action, "source": source, "params": params or {}}


# ---------------------------------------------------------------------------
# Step 1 — Ontological absence: action not defined in world → "impossible"
# ---------------------------------------------------------------------------

def test_unknown_action_is_impossible(world):
    """An action not defined in the world cannot be executed."""
    result = evaluate(_make_tool_call("delete_repository", "external"), world)
    assert result["decision"] == "impossible"
    assert "not defined" in result["reason"]


def test_another_unknown_action_is_impossible(world):
    result = evaluate(_make_tool_call("launch_missile", "user"), world)
    assert result["decision"] == "impossible"


# ---------------------------------------------------------------------------
# Step 3 — Capability check: untrusted source cannot perform external action
# ---------------------------------------------------------------------------

def test_untrusted_cannot_do_external(world):
    """An untrusted (external) source is not permitted to perform external actions."""
    result = evaluate(_make_tool_call("send_email", "external"), world)
    assert result["decision"] == "impossible"


def test_untrusted_can_do_internal(world):
    """An untrusted (external) source is allowed to read internal data."""
    result = evaluate(_make_tool_call("read_data", "external"), world)
    # Taint rule: external + internal → no taint problem, capability check passes
    assert result["decision"] == "allow"


# ---------------------------------------------------------------------------
# Step 4 — Taint rule: tainted source + external action → "impossible"
# ---------------------------------------------------------------------------

def test_taint_containment_send_email(world):
    """Tainted external source cannot send email (external side-effect)."""
    result = evaluate(
        _make_tool_call("send_email", "external", params={"to": "client"}), world
    )
    assert result["decision"] == "impossible"
    assert "not permitted" in result["reason"]


def test_taint_containment_post_webhook(world):
    """Tainted external source cannot trigger a webhook (external side-effect)."""
    result = evaluate(_make_tool_call("post_webhook", "external"), world)
    assert result["decision"] == "impossible"


# ---------------------------------------------------------------------------
# Step 5 — Approval required
# ---------------------------------------------------------------------------

def test_approval_required_for_flagged_action(world):
    """A trusted user requesting an approval-required action gets 'require_approval'."""
    result = evaluate(_make_tool_call("download_report", "user"), world)
    assert result["decision"] == "require_approval"
    assert "approval" in result["reason"].lower()


def test_system_source_also_requires_approval(world):
    result = evaluate(_make_tool_call("download_report", "system"), world)
    assert result["decision"] == "require_approval"


# ---------------------------------------------------------------------------
# Happy path — "allow"
# ---------------------------------------------------------------------------

def test_trusted_user_can_read_data(world):
    result = evaluate(_make_tool_call("read_data", "user"), world)
    assert result["decision"] == "allow"


def test_trusted_user_can_send_email(world):
    result = evaluate(_make_tool_call("send_email", "user"), world)
    assert result["decision"] == "allow"


def test_system_can_send_email(world):
    result = evaluate(_make_tool_call("send_email", "system"), world)
    assert result["decision"] == "allow"


# ---------------------------------------------------------------------------
# Unknown source defaults to untrusted
# ---------------------------------------------------------------------------

def test_unknown_source_treated_as_untrusted(world):
    """A source not listed in the trust map defaults to 'untrusted'."""
    result = evaluate(_make_tool_call("send_email", "mystery_agent"), world)
    assert result["decision"] == "impossible"


def test_unknown_source_can_read_internal(world):
    result = evaluate(_make_tool_call("read_data", "mystery_agent"), world)
    assert result["decision"] == "allow"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

def test_result_always_has_decision_and_reason(world):
    for action, source in [
        ("read_data", "user"),
        ("send_email", "external"),
        ("delete_repository", "user"),
        ("download_report", "user"),
    ]:
        result = evaluate(_make_tool_call(action, source), world)
        assert "decision" in result
        assert "reason" in result
        assert isinstance(result["decision"], str)
        assert isinstance(result["reason"], str)


def test_no_deny_decision(world):
    """The engine never returns 'deny' or 'block' — unsafe actions are impossible."""
    forbidden = {"deny", "block"}
    test_cases = [
        ("delete_repository", "external"),
        ("send_email", "external"),
        ("read_data", "external"),
        ("download_report", "system"),
    ]
    for action, source in test_cases:
        result = evaluate(_make_tool_call(action, source), world)
        assert result["decision"] not in forbidden, (
            f"Got forbidden decision '{result['decision']}' for ({action}, {source})"
        )
