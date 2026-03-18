# Architectural Audit Report — safe-agent-runtime-core

> **Audit date:** 2026-03-18
> **Auditor:** Claude (claude-sonnet-4-6)
> **Scope:** Deterministic ontological execution model — "impossible vs. deny" principle
> **Note:** This supersedes the prior audit. The prior audit analyzed an earlier revision of the
> code and several of its findings are now factually incorrect against the current implementation.

---

## Structured Report

```yaml
verdict: "partial implementation — closer to guardrail than ontological runtime"

score:
  overall: 5
  ontology: 4
  determinism: 7
  capability_model: 3
  taint_model: 4
  execution_control: 6

critical_issues:

  - |
    TRUST IS SELF-ASSERTED — NOT CHANNEL-DERIVED (Principle 4 VIOLATED).
    Source("user") is a plain string dataclass field. Any caller can write
    Source("system") or Source("user") and claim any trust level. There is no
    channel binding, no authentication, no signed token, no kernel-level origin
    enforcement. The trust model is opt-in. If the caller lies, the runtime is
    blind. This is the most severe structural violation: the entire capability
    and taint model is predicated on a trust level that callers supply
    themselves.

  - |
    TAINT IS SELF-REPORTED (Principle 5 VIOLATED).
    ActionRequest(taint=TaintState.TAINTED) is set by the caller at construction
    time. If the caller forgets to mark tainted data — or deliberately marks
    tainted data as CLEAN — the evaluator has no mechanism to detect it. There is
    no taint-tracking engine, no type-level propagation, no runtime lineage
    tracking. Taint is a post-it note the caller writes on the envelope. This
    makes the taint model aspirational, not enforced.

  - |
    ACTION CONSTRUCTION IS BYPASSABLE — REGISTRY IS CONVENTION, NOT ENFORCEMENT.
    Action.__init__ is public. The docstring in registry.py explicitly states:
      "Direct instantiation is possible but bypasses the registry contract"
    This means:
      a = Action("launch_missile", ActionType.INTERNAL, lambda p: {})
      a._execute({})  # executes, no registry, no evaluator, no runtime
    is syntactically and semantically valid Python. The ontological closure is
    a naming convention, not a structural property. Nothing in the type system
    prevents constructing or executing an undefined action.

  - |
    POLICY IS RUNTIME-INTERPRETED, NOT COMPILED (Principle 6 VIOLATED).
    world.yaml is loaded via yaml.safe_load() and stored as plain Python dicts.
    Every call to Evaluator.check() iterates self._taint_rules, does dict
    lookups on self._capabilities, and compares strings. There is no compilation
    phase. Policy changes can be injected by replacing the dicts at runtime.
    The "policy" is a mutable Python dict — not a sealed, compiled artifact.

  - |
    CAPABILITIES ARE STRING-CHECKED AT RUNTIME (Principle 8 VIOLATED).
    evaluator.py:
      allowed_types = self._capabilities.get(trust_level, [])
      if request.action.action_type.value not in allowed_types:
    This is a runtime string membership test against a list loaded from YAML.
    The value being tested is .value (a string) compared against strings from
    a dict. This is a guardrail check — not compiled capability resolution,
    not static dispatch, not a type-level impossibility.

  - |
    APPROVAL GATE IS A STRUCTURAL DEAD END.
    REQUIRE_APPROVAL causes Runtime to raise ImpossibleActionError. There is no
    path in the codebase to submit, validate, or record an approval. Once an
    action requires approval, it can never succeed — ever. The approval gate
    enforces permanent impossibility rather than conditional gating. This is not
    a design choice: there is simply no approval workflow. The feature is
    incomplete and its presence creates false confidence.

architectural_gaps:

  - |
    NO TAINT PROPAGATION ENGINE.
    Taint is a per-request binary flag. If read_data() returns data from an
    untrusted source and that data is passed as params to send_email(), the taint
    is NOT automatically forwarded. The caller must manually remember to set
    taint=TaintState.TAINTED on the second request. In a real pipeline, taint
    must be a type-level property of the data itself — not an annotation on the
    request wrapper. Actions should return TaintedValue(result, taint_state) and
    the runtime should propagate that state into any downstream ActionRequest.

  - |
    NO CHANNEL-LEVEL SOURCE BINDING.
    Source is a dataclass with a single name: str field. The system has no
    concept of authenticated channels, signed origins, or hardware-attested
    sources. To implement Principle 4 (trust from channel, not content), Source
    must be produced by the channel layer — not by the caller — and must be
    unforgeable (e.g., sealed constructor, protocol-level injection, or IPC
    socket identity).

  - |
    NO COMPILE PHASE FOR POLICY.
    world.yaml defines the ontology. It should be compiled once at startup into
    a frozen, validated dispatch structure (e.g., a frozen dict of
    (TrustLevel, ActionType) → Decision, or a compiled match table). Instead,
    the raw YAML structure is carried as mutable Python dicts through the
    lifetime of the Evaluator instance and re-interpreted on every request.

  - |
    NO SEALED ACTION TYPE SYSTEM.
    The ActionType enum (INTERNAL/EXTERNAL) is correct directionally, but actions
    themselves are registered by string name. True ontological closure requires
    actions to be first-class sealed types — not string keys in a dict. In
    Python this means: either a sealed Enum of known actions, a Protocol with
    __init_subclass__ that enforces registry membership, or a frozen dataclass
    hierarchy that makes construction outside the registry a type error.

  - |
    NO IR LAYER.
    ActionRequest is a typed struct, but it is not an IR. A true Intent IR would
    require: (a) a parse/canonicalization phase that transforms raw input into
    the IR, (b) semantic validation at parse time (not evaluation time), and
    (c) the IR being the ONLY form in which intent is expressed inside the system.
    Currently, ActionRequest is constructed directly by callers with no
    intermediate parse stage.

dead_logic:

  - |
    PRIOR AUDIT'S "DEAD CODE" FINDING IS WRONG.
    The prior AUDIT_REPORT.md claimed the taint check at Step 2 of Evaluator is
    unreachable dead code. This was accurate for the OLD implementation where
    taint was derived from source == "external" (a hardcoded string). In the
    CURRENT implementation, taint is an explicit field on ActionRequest
    (TaintState enum), and the taint rules are evaluated from world.yaml's
    taint_rules section. A TRUSTED user carrying TAINTED data CAN reach the
    taint check:
      - Step 1 capability check: trusted user CAN perform external actions → passes
      - Step 2 taint check: trusted user + tainted data + external action → fires
    Demo B and test_tainted_data_blocks_external_action_for_trusted_user both
    exercise this path correctly. The old finding is now factually incorrect and
    should not be used as a basis for further changes.

  - |
    APPROVAL GATE LOGIC IS DEAD IN PRACTICE.
    The REQUIRE_APPROVAL branch in Runtime.execute() raises ImpossibleActionError.
    Since no approval submission mechanism exists anywhere in the codebase, no
    approval-required action can ever execute. The dead_logic is not in the check
    itself but in the semantic: the gate exists to allow execution after approval,
    yet the "after approval" path does not exist. Any test that expects
    approval-required actions to eventually succeed would hang indefinitely.

  - |
    handlers FALLBACK IN build_runtime() IS UNREACHABLE.
    runtime.py:
      handler = handlers.get(name, lambda p: {})
    The fallback lambda p: {} is unreachable because the loop iterates only over
    world["actions"].items() — which are the exact keys in the handlers dict.
    If a new action is added to world.yaml without a corresponding handler entry,
    it silently gets a no-op lambda. This is a latent bug, not dead code — but
    the fallback gives false confidence that unknown actions are handled safely.

repo_structure_assessment:

  - |
    FLAT STRUCTURE WITH NO LAYER SEPARATION.
    Everything is in the repository root (runtime.py, evaluator.py, registry.py,
    models.py, world.yaml). There is no directory hierarchy separating:
      ir/          — Intent IR definitions and parser
      policy/      — World definition and compiler
      runtime/     — Execution engine
      tests/
    The absence of an ir/ or policy/compiled/ directory reflects the absence of
    a compile phase: there is nothing to separate because compilation does not exist.

  - |
    NO COMPILER MODULE.
    A proper ontological runtime requires a compiler that transforms world.yaml
    into a static, validated execution model. This module does not exist. The
    closest thing is build_runtime() in runtime.py — an 18-line bootstrap
    function. It loads YAML, iterates dict items, and returns a Runtime. This is
    not a compiler; it is lazy initialization.

  - |
    models.py MIXES CONCERNS.
    TaintState, ActionType, DecisionOutcome, ImpossibleActionError, Source, and
    Decision are all in models.py. These belong to different architectural layers:
    TaintState and Source are data-layer types; DecisionOutcome and Decision are
    policy-layer types; ImpossibleActionError is a runtime boundary signal.
    Mixing them collapses the layer model into a single flat namespace.

  - |
    TESTS VERIFY BEHAVIOR, NOT STRUCTURAL GUARANTEES.
    test_runtime.py correctly tests that ImpossibleActionError is raised and
    that handlers do not fire on constraint violations. But no test verifies:
      - that Action cannot be constructed outside the registry
      - that Source cannot be fabricated to claim a different trust level
      - that taint cannot be suppressed by a caller who sets it wrong
    These are structural properties. Behavioral tests cannot prove them.

fix_directions:

  - |
    FIX 1 — SEAL ACTION CONSTRUCTION (highest leverage).
    Move Action.__init__ to a module-private constructor pattern. In Python:
      class Action:
          def __init__(self, ...): ...  # make truly private via name mangling
          # OR: use a class-level registry key as constructor guard
    Better: replace string-keyed registry with a frozen Enum of known actions
    where each member IS the action object. Undefined action names cannot be
    passed to Enum() — they raise ValueError at construction, not at registry
    lookup. This moves "impossible" from runtime exception to type-system error.

  - |
    FIX 2 — DERIVE TRUST FROM CHANNEL (eliminates self-assertion).
    Source must be produced by the ingress layer, not by the caller.
    Concretely:
      class AuthenticatedChannel:
          def __init__(self, identity: str, credential: bytes): ...
          def make_source(self) -> Source: ...  # sealed factory
    Source.__init__ becomes private or is replaced with a class method that
    requires a valid AuthenticatedChannel. Callers cannot fabricate Source
    without a real channel object. This requires rethinking the API surface
    but is non-negotiable for Principle 4.

  - |
    FIX 3 — COMPILE POLICY TO STATIC DISPATCH TABLE.
    Replace Evaluator's runtime dict lookups with a pre-computed frozen structure:
      capability_table: frozenset[tuple[TrustLevel, ActionType]]
    Computed once in build_runtime(), never mutated. The check becomes:
      if (trust_level, action_type) not in self._capability_table: raise ...
    This eliminates runtime string comparisons and makes the policy unsealed
    by construction (the frozenset cannot be extended after compilation).

  - |
    FIX 4 — MAKE TAINT A DATA-LEVEL TYPE, NOT A REQUEST ANNOTATION.
    Define:
      @dataclass(frozen=True)
      class TaintedValue(Generic[T]):
          value: T
          taint: TaintState
    Action handlers must return TaintedValue. Runtime.execute() unwraps it and
    propagates taint to any downstream ActionRequest. The caller cannot suppress
    taint by "forgetting" — the type enforces it. This converts taint from an
    honor-system annotation to a structural guarantee.

  - |
    FIX 5 — IMPLEMENT OR REMOVE THE APPROVAL GATE.
    Either: implement an approval workflow (token issuance, verification, re-execution
    path) so REQUIRE_APPROVAL can actually unblock. Or: remove it entirely until
    the workflow exists. A dead gate that permanently blocks is worse than no gate —
    it gives false architectural assurance and will cause silent failures in any
    real deployment.

  - |
    FIX 6 — INTRODUCE AN IR PARSE LAYER.
    The system currently skips from raw input directly to ActionRequest
    construction. Add a parse phase:
      raw_input → parse() → ActionRequest (IR) → Runtime.execute()
    parse() performs: schema validation, action name → Action object resolution
    via registry (raising at parse time, not eval time), taint annotation from
    data lineage (not from caller), and source binding from channel.
    This creates the "bounded parsing stage" required by Principle 7.
```

---

## Summary

The current implementation represents a meaningful improvement over the prior revision. The
key gains are: `ImpossibleActionError` is raised (not returned as a string), `Runtime.execute()`
binds evaluation to execution (no advisory gap), `ActionRegistry` raises at construction for
undefined actions, and taint is expressed as a first-class enum field on `ActionRequest` with
independent evaluation from world.yaml rules.

However, the system remains architecturally a guardrail system for the following reasons:

1. **Trust is asserted by callers** — not derived from authenticated channels.
2. **Taint is annotated by callers** — not tracked by the runtime from data lineage.
3. **Capabilities are checked via string comparisons** — not compiled to static dispatch.
4. **Actions are registry-by-convention** — `Action.__init__` is publicly constructable.
5. **Policy is runtime-interpreted** — no compile phase, mutable YAML-derived dicts.

Until (1) and (2) are fixed, no amount of evaluation logic produces real safety guarantees —
because the inputs to evaluation are controlled by the party being constrained.

The vocabulary and intent are correct. The structural enforcement is not.

---

*End of audit.*
