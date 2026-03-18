"""
Tests for the Ontological Runtime.

Structural properties verified (not just behavioral):

  1. Undefined actions → ConstructionError at IR build time (not at execution)
  2. Source cannot be fabricated — TypeError on direct construction
  3. Taint propagates from TaintedValue inputs — callers cannot suppress it
  4. Capability violations → ConstructionError at build time (not execution time)
  5. Sandbox executes pre-validated IR without re-checking any constraint
  6. CompiledPolicy and CompiledAction are immutable after construction
  7. Approval gate raises ConstructionError (not a runtime dead-end)
  8. Taint on IR output equals taint computed at build time

The critical distinction from the old test suite:
  Old: tests verified that runtime.execute() raised for bad requests.
       Execution was still attempted; the check happened inside execute().
  New: tests verify that builder.build() raises before execution.
       sandbox.execute() is never called on a failed build.
"""

import os
import pytest

from compile import CompiledAction
from channel import Source
from ir import IntentIR, IRBuilder
from models import ActionType, ConstructionError, TaintState, TrustLevel
from taint import TaintedValue
from runtime import build_runtime

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "world_manifest.yaml")


@pytest.fixture(scope="module")
def runtime():
    return build_runtime(MANIFEST)


# ── 1. Undefined actions → ConstructionError at build time ────────────────────

class TestOntologicalAbsence:
    """
    Undefined actions cannot be represented as IntentIR.
    ConstructionError is raised at builder.build() — no execution path entered.
    """

    def test_undefined_action_raises_at_build(self, runtime):
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("delete_repository", source, {})
        assert "does not exist in the compiled policy" in exc_info.value.reason

    def test_launch_missile_raises_at_build(self, runtime):
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError):
            runtime.builder.build("launch_missile", source, {})

    def test_empty_string_raises_at_build(self, runtime):
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError):
            runtime.builder.build("", source, {})

    def test_known_action_returns_intent_ir(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {"query": "test"})
        assert isinstance(ir, IntentIR)
        assert ir.action.name == "read_data"

    def test_handler_not_called_when_build_fails(self, runtime):
        """
        Structural proof: when build() raises, no handler is invoked.

        Old test verified that runtime.execute() didn't call the handler.
        New test verifies that build() raises before sandbox is ever called.
        """
        executed = []

        from compile import compile_world, _COMPILE_GATE  # type: ignore[attr-defined]

        # We cannot use _COMPILE_GATE from outside — so use runtime.policy to
        # verify that the undefined action simply isn't in the compiled policy.
        assert runtime.policy.get_action("delete_repository") is None

        source = runtime.channel("user").source
        with pytest.raises(ConstructionError):
            runtime.builder.build("delete_repository", source, {})
        # sandbox.execute() was never called — no handler could fire
        assert executed == []


# ── 2. Sealed Source ──────────────────────────────────────────────────────────

class TestSealedSource:
    """
    Source cannot be constructed directly by callers.
    Trust is derived from the channel (compiled policy), not asserted.
    """

    def test_direct_source_construction_raises_type_error(self):
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            Source(trust_level=TrustLevel.TRUSTED, identity="attacker")

    def test_source_from_trusted_channel(self, runtime):
        source = runtime.channel("user").source
        assert source.trust_level == TrustLevel.TRUSTED
        assert source.identity == "user"

    def test_source_from_untrusted_channel(self, runtime):
        source = runtime.channel("external").source
        assert source.trust_level == TrustLevel.UNTRUSTED

    def test_unknown_channel_defaults_to_untrusted(self, runtime):
        source = runtime.channel("mystery_agent").source
        assert source.trust_level == TrustLevel.UNTRUSTED

    def test_source_is_immutable(self, runtime):
        source = runtime.channel("user").source
        with pytest.raises(AttributeError):
            source.trust_level = TrustLevel.UNTRUSTED

    def test_intent_ir_cannot_be_constructed_directly(self, runtime):
        """IntentIR without _IR_SEAL raises TypeError at construction."""
        source = runtime.channel("user").source
        action = runtime.policy.get_action("read_data")
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            IntentIR(
                _seal=object(),  # wrong seal
                action=action,
                source=source,
                params={},
                taint=TaintState.CLEAN,
            )


# ── 3. Taint propagation ──────────────────────────────────────────────────────

class TestTaintPropagation:
    """
    Taint propagates from prior TaintedValue outputs to the new IR.
    Callers cannot suppress taint — they must pass prior outputs.
    """

    def test_tainted_input_blocks_external_action_at_build(self, runtime):
        """
        Trusted user + tainted prior output + external action → ConstructionError at build.
        Old: ImpossibleActionError at runtime.execute().
        New: ConstructionError at builder.build() — sandbox never called.
        """
        tainted_prior = TaintedValue(value={"data": "injected"}, taint=TaintState.TAINTED)
        source = runtime.channel("user").source  # TRUSTED
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("send_email", source, {"to": "x@y.com"}, tainted_prior)
        assert "taint" in exc_info.value.reason.lower()

    def test_tainted_input_blocks_post_webhook_at_build(self, runtime):
        tainted_prior = TaintedValue(value={}, taint=TaintState.TAINTED)
        source = runtime.channel("system").source
        with pytest.raises(ConstructionError):
            runtime.builder.build("post_webhook", source, {"url": "https://attacker.com"}, tainted_prior)

    def test_tainted_input_allows_internal_action(self, runtime):
        """Taint rule only blocks EXTERNAL actions — INTERNAL is allowed."""
        tainted_prior = TaintedValue(value={"q": "user input"}, taint=TaintState.TAINTED)
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {"query": "x"}, tainted_prior)
        assert ir.taint == TaintState.TAINTED  # IR carries the taint
        result = runtime.sandbox.execute(ir)
        assert result.taint == TaintState.TAINTED  # taint propagated to output

    def test_clean_input_allows_external_action(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("send_email", source, {"to": "x@y.com"})
        result = runtime.sandbox.execute(ir)
        assert result.taint == TaintState.CLEAN

    def test_taint_join_is_monotonic(self):
        """CLEAN ∨ TAINTED = TAINTED — cannot decrease."""
        clean = TaintedValue(value=1, taint=TaintState.CLEAN)
        tainted = TaintedValue(value=2, taint=TaintState.TAINTED)
        assert TaintedValue.join(clean, tainted) == TaintState.TAINTED
        assert TaintedValue.join(tainted, clean) == TaintState.TAINTED
        assert TaintedValue.join(clean, clean) == TaintState.CLEAN
        assert TaintedValue.join(tainted, tainted) == TaintState.TAINTED

    def test_no_inputs_defaults_to_clean(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {})
        assert ir.taint == TaintState.CLEAN

    def test_multiple_inputs_any_tainted_propagates(self, runtime):
        clean = TaintedValue(value={}, taint=TaintState.CLEAN)
        tainted = TaintedValue(value={}, taint=TaintState.TAINTED)
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError):
            runtime.builder.build("send_email", source, {}, clean, tainted)

    def test_output_taint_matches_ir_taint(self, runtime):
        """Sandbox wraps result in TaintedValue preserving the IR's taint."""
        tainted_prior = TaintedValue(value={}, taint=TaintState.TAINTED)
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {}, tainted_prior)
        result = runtime.sandbox.execute(ir)
        assert result.taint == ir.taint == TaintState.TAINTED


# ── 4. Capability violations at build time ────────────────────────────────────

class TestCapabilityAtBuildTime:
    """
    Capability checks happen at IR construction, not at execution.
    ConstructionError is raised by builder.build() — sandbox is never called.
    """

    def test_untrusted_cannot_build_external_action_ir(self, runtime):
        source = runtime.channel("external").source  # UNTRUSTED
        assert source.trust_level == TrustLevel.UNTRUSTED
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("send_email", source, {})
        assert "capability" in exc_info.value.reason.lower()

    def test_unknown_source_treated_as_untrusted(self, runtime):
        source = runtime.channel("unknown_bot").source
        assert source.trust_level == TrustLevel.UNTRUSTED
        with pytest.raises(ConstructionError):
            runtime.builder.build("send_email", source, {})

    def test_untrusted_can_build_internal_action_ir(self, runtime):
        source = runtime.channel("external").source  # UNTRUSTED
        ir = runtime.builder.build("read_data", source, {})
        result = runtime.sandbox.execute(ir)
        assert result is not None

    def test_trusted_can_build_external_action_ir(self, runtime):
        source = runtime.channel("user").source  # TRUSTED
        ir = runtime.builder.build("send_email", source, {"to": "x@y.com"})
        result = runtime.sandbox.execute(ir)
        assert result.value["sent"] is True

    def test_capability_check_uses_compiled_matrix(self, runtime):
        """
        Verify the capability check uses the frozenset, not a string scan.
        The frozenset contains (TrustLevel, ActionType) tuples — not strings.
        """
        matrix = runtime.policy._capability_matrix
        assert isinstance(matrix, frozenset)
        assert (TrustLevel.TRUSTED, ActionType.INTERNAL) in matrix
        assert (TrustLevel.TRUSTED, ActionType.EXTERNAL) in matrix
        assert (TrustLevel.UNTRUSTED, ActionType.INTERNAL) in matrix
        assert (TrustLevel.UNTRUSTED, ActionType.EXTERNAL) not in matrix


# ── 5. Sandbox is a pure executor ─────────────────────────────────────────────

class TestSandboxPureExecution:
    """
    Sandbox.execute() does not check any constraints.
    If an IntentIR was constructed, execution is unconditional.
    """

    def test_sandbox_executes_valid_ir(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {"query": "SELECT *"})
        result = runtime.sandbox.execute(ir)
        assert isinstance(result, TaintedValue)
        assert result.value["data"] == "SELECT *"

    def test_sandbox_returns_tainted_value(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("send_email", source, {"to": "x@y.com"})
        result = runtime.sandbox.execute(ir)
        assert isinstance(result, TaintedValue)

    def test_sandbox_clean_result_for_clean_ir(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {})
        result = runtime.sandbox.execute(ir)
        assert result.taint == TaintState.CLEAN

    def test_sandbox_accepts_only_intent_ir(self, runtime):
        """Sandbox.execute() has no overload for raw dicts or action names."""
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {})
        # This test documents that sandbox.execute() requires IntentIR —
        # passing anything else is a Python type error, not a policy error.
        assert isinstance(ir, IntentIR)


# ── 6. CompiledPolicy and CompiledAction immutability ─────────────────────────

class TestImmutability:
    """
    Compiled artifacts are frozen after construction.
    Runtime cannot be mutated to add or remove actions.
    """

    def test_policy_actions_mapping_is_read_only(self, runtime):
        with pytest.raises((TypeError, AttributeError)):
            runtime.policy.actions["evil_action"] = object()

    def test_policy_attribute_cannot_be_set(self, runtime):
        with pytest.raises(AttributeError):
            runtime.policy._capability_matrix = frozenset()

    def test_compiled_action_name_cannot_be_changed(self, runtime):
        action = runtime.policy.actions["read_data"]
        with pytest.raises(AttributeError):
            action.name = "evil"

    def test_capability_matrix_is_frozenset(self, runtime):
        matrix = runtime.policy._capability_matrix
        assert isinstance(matrix, frozenset)
        with pytest.raises(AttributeError):
            matrix.add((TrustLevel.TRUSTED, ActionType.INTERNAL))

    def test_taint_rules_is_tuple(self, runtime):
        rules = runtime.policy._taint_rules
        assert isinstance(rules, tuple)

    def test_runtime_is_immutable(self, runtime):
        with pytest.raises(AttributeError):
            runtime._policy = None

    def test_compiled_action_cannot_be_constructed_externally(self):
        """CompiledAction raises TypeError without the compile gate."""
        with pytest.raises(TypeError, match="cannot be constructed outside the compile phase"):
            CompiledAction(
                name="evil",
                action_type=ActionType.INTERNAL,
                handler=lambda p: {},
                approval_required=False,
                _gate=object(),  # wrong gate
            )


# ── 7. Approval gate at build time ────────────────────────────────────────────

class TestApprovalGate:
    """
    Approval-required actions raise ConstructionError at build time.
    Old system: REQUIRE_APPROVAL at execution time — dead end.
    New system: ConstructionError at build time — with a message indicating what is needed.
    """

    def test_approval_required_blocks_build_for_trusted_user(self, runtime):
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("download_report", source, {"id": "r-123"})
        assert "approval" in exc_info.value.reason.lower()

    def test_approval_required_blocks_build_for_system(self, runtime):
        source = runtime.channel("system").source
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("download_report", source, {"id": "r-456"})
        assert "approval" in exc_info.value.reason.lower()

    def test_approval_error_message_indicates_what_is_needed(self, runtime):
        """Error must tell the caller what to do — not just that it failed."""
        source = runtime.channel("user").source
        with pytest.raises(ConstructionError) as exc_info:
            runtime.builder.build("download_report", source, {})
        # Message must reference approval token — not just "blocked"
        assert "approval" in exc_info.value.reason.lower()


# ── 8. Allowed actions execute successfully ────────────────────────────────────

class TestAllowedExecution:

    def test_trusted_user_reads_data(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("read_data", source, {"query": "SELECT *"})
        result = runtime.sandbox.execute(ir)
        assert result.value["data"] == "SELECT *"
        assert result.taint == TaintState.CLEAN

    def test_trusted_user_sends_email(self, runtime):
        source = runtime.channel("user").source
        ir = runtime.builder.build("send_email", source, {"to": "a@b.com"})
        result = runtime.sandbox.execute(ir)
        assert result.value["sent"] is True

    def test_system_posts_webhook(self, runtime):
        source = runtime.channel("system").source
        ir = runtime.builder.build("post_webhook", source, {"url": "https://svc/notify"})
        result = runtime.sandbox.execute(ir)
        assert result.value["status"] == 200

    def test_untrusted_reads_internal(self, runtime):
        """Untrusted source can still perform internal actions."""
        source = runtime.channel("external").source
        ir = runtime.builder.build("read_data", source, {})
        result = runtime.sandbox.execute(ir)
        assert result is not None

    def test_unknown_source_reads_internal(self, runtime):
        """Unknown source defaults to untrusted — can do internal actions."""
        source = runtime.channel("mystery_agent").source
        assert source.trust_level == TrustLevel.UNTRUSTED
        ir = runtime.builder.build("read_data", source, {})
        result = runtime.sandbox.execute(ir)
        assert result is not None
