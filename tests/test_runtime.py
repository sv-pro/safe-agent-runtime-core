"""
Tests for the Constrained Execution Runtime.

Key invariants verified:
  - Unknown actions cannot be constructed (fail at registry.get())
  - Tainted data + external action is impossible (raises, not returns)
  - Bypass is impossible (handler never called on constraint failure)
  - Allowed actions execute successfully
  - No advisory decision strings — only hard enforcement or success
"""

import os
import pytest

from evaluator import Evaluator
from registry import ActionRegistry, ActionRequest
from runtime import Runtime, build_runtime, load_world
from models import ActionType, ImpossibleActionError, Source, TaintState

WORLD_YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "world.yaml")


@pytest.fixture(scope="module")
def runtime_and_registry():
    return build_runtime(WORLD_YAML_PATH)


@pytest.fixture(scope="module")
def runtime(runtime_and_registry):
    return runtime_and_registry[0]


@pytest.fixture(scope="module")
def registry(runtime_and_registry):
    return runtime_and_registry[1]


# ---------------------------------------------------------------------------
# Unknown action fails at construction (not at execution)
# ---------------------------------------------------------------------------

class TestUnknownActionConstruction:
    def test_unknown_action_raises_at_construction(self, registry):
        """Action not in registry cannot be constructed — impossible before execution."""
        with pytest.raises(ImpossibleActionError) as exc_info:
            registry.get("delete_repository")
        assert "delete_repository" in str(exc_info.value)

    def test_launch_missile_raises_at_construction(self, registry):
        with pytest.raises(ImpossibleActionError):
            registry.get("launch_missile")

    def test_arbitrary_string_raises_at_construction(self, registry):
        with pytest.raises(ImpossibleActionError):
            registry.get("__any_string_not_in_world__")

    def test_known_action_is_returned_as_action_object(self, registry):
        action = registry.get("read_data")
        assert action.name == "read_data"
        assert action.action_type == ActionType.INTERNAL


# ---------------------------------------------------------------------------
# Taint blocks external action (taint is separate from trust)
# ---------------------------------------------------------------------------

class TestTaintEnforcement:
    def test_tainted_data_blocks_external_action_for_trusted_user(self, runtime, registry):
        """
        Key taint scenario: a TRUSTED user carries tainted params.
        Trust check passes (trusted can do external), but taint rule fires.
        This proves taint is distinct from trust and is live code.
        """
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("user"),           # trusted source — capability allows external
            params={"to": "victim@example.com", "body": "<injected content>"},
            taint=TaintState.TAINTED,        # data is tainted
        )
        with pytest.raises(ImpossibleActionError) as exc_info:
            runtime.execute(request)
        assert "tainted" in str(exc_info.value).lower() or "external" in str(exc_info.value).lower()

    def test_tainted_data_blocks_post_webhook_for_trusted_user(self, runtime, registry):
        action = registry.get("post_webhook")
        request = ActionRequest(
            action=action,
            source=Source("system"),         # trusted
            params={"url": "https://attacker.com/exfil"},
            taint=TaintState.TAINTED,
        )
        with pytest.raises(ImpossibleActionError):
            runtime.execute(request)

    def test_tainted_data_allows_internal_action(self, runtime, registry):
        """Taint rule only blocks external actions — internal actions are unaffected."""
        action = registry.get("read_data")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"query": "tainted_user_input"},
            taint=TaintState.TAINTED,
        )
        result = runtime.execute(request)
        assert result is not None

    def test_clean_data_allows_external_action_for_trusted_user(self, runtime, registry):
        """Clean data from a trusted source can execute external actions."""
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"to": "colleague@company.com"},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None


# ---------------------------------------------------------------------------
# Bypass is impossible — handler never fires on constraint failure
# ---------------------------------------------------------------------------

class TestBypassImpossible:
    def test_impossible_action_raises_not_returns_string(self, runtime, registry):
        """Runtime raises — never returns an advisory string like 'impossible'."""
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("external"),       # untrusted, cannot do external
            params={},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError):
            runtime.execute(request)

    def test_no_soft_decision_string_on_failure(self, runtime, registry):
        """Verify execution never returns a string on failure — only raises."""
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("external"),
            params={},
            taint=TaintState.CLEAN,
        )
        result = None
        try:
            result = runtime.execute(request)
        except ImpossibleActionError:
            pass
        assert result is None, "Runtime must raise, never return an advisory string"

    def test_handler_not_called_when_constraint_fails(self, registry):
        """
        Structural proof: the action handler is never invoked when
        execution is impossible. Uses a tracking handler to verify silence.
        """
        executed = []

        def tracking_handler(params):
            executed.append(True)
            return {"done": True}

        local_registry = ActionRegistry()
        local_registry.register("tracked_external", ActionType.EXTERNAL, tracking_handler)

        world = load_world(WORLD_YAML_PATH)
        local_runtime = Runtime(local_registry, Evaluator(world))

        action = local_registry.get("tracked_external")
        request = ActionRequest(
            action=action,
            source=Source("external"),       # untrusted, cannot do external
            params={},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError):
            local_runtime.execute(request)

        assert executed == [], "Handler MUST NOT be called when execution is impossible"

    def test_taint_handler_not_called(self, registry):
        """Handler is not called when taint rule fires."""
        executed = []

        def tracking_handler(params):
            executed.append(True)
            return {"done": True}

        local_registry = ActionRegistry()
        local_registry.register("tracked_external2", ActionType.EXTERNAL, tracking_handler)

        world = load_world(WORLD_YAML_PATH)
        local_runtime = Runtime(local_registry, Evaluator(world))

        action = local_registry.get("tracked_external2")
        request = ActionRequest(
            action=action,
            source=Source("user"),           # trusted — passes capability check
            params={"data": "injected"},
            taint=TaintState.TAINTED,        # taint rule fires here
        )
        with pytest.raises(ImpossibleActionError):
            local_runtime.execute(request)

        assert executed == [], "Handler MUST NOT be called when taint rule fires"


# ---------------------------------------------------------------------------
# Allowed actions execute successfully
# ---------------------------------------------------------------------------

class TestAllowedActions:
    def test_trusted_user_can_read_data(self, runtime, registry):
        action = registry.get("read_data")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"query": "SELECT *"},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None

    def test_trusted_user_can_send_email(self, runtime, registry):
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"to": "colleague@company.com"},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None

    def test_system_can_post_webhook(self, runtime, registry):
        action = registry.get("post_webhook")
        request = ActionRequest(
            action=action,
            source=Source("system"),
            params={"url": "https://internal.svc/notify"},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None

    def test_untrusted_source_can_read_internal(self, runtime, registry):
        """Untrusted (external) source can still perform internal actions."""
        action = registry.get("read_data")
        request = ActionRequest(
            action=action,
            source=Source("external"),
            params={},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None

    def test_unknown_source_can_read_internal(self, runtime, registry):
        """Unknown source defaults to untrusted — can still do internal actions."""
        action = registry.get("read_data")
        request = ActionRequest(
            action=action,
            source=Source("mystery_agent"),
            params={},
            taint=TaintState.CLEAN,
        )
        result = runtime.execute(request)
        assert result is not None


# ---------------------------------------------------------------------------
# Approval requirement raises ImpossibleActionError
# ---------------------------------------------------------------------------

class TestApprovalRequirement:
    def test_approval_required_raises_for_trusted_user(self, runtime, registry):
        action = registry.get("download_report")
        request = ActionRequest(
            action=action,
            source=Source("user"),
            params={"id": "report-123"},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError) as exc_info:
            runtime.execute(request)
        assert "approval" in str(exc_info.value).lower()

    def test_approval_required_raises_for_system_source(self, runtime, registry):
        action = registry.get("download_report")
        request = ActionRequest(
            action=action,
            source=Source("system"),
            params={"id": "report-456"},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError):
            runtime.execute(request)


# ---------------------------------------------------------------------------
# Capability enforcement
# ---------------------------------------------------------------------------

class TestCapabilityEnforcement:
    def test_untrusted_cannot_do_external(self, runtime, registry):
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("external"),
            params={},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError):
            runtime.execute(request)

    def test_unknown_source_treated_as_untrusted_for_external(self, runtime, registry):
        action = registry.get("send_email")
        request = ActionRequest(
            action=action,
            source=Source("unknown_bot"),
            params={},
            taint=TaintState.CLEAN,
        )
        with pytest.raises(ImpossibleActionError):
            runtime.execute(request)
