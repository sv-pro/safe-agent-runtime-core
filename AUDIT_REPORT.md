# Architectural Audit & Refactor Report — safe-agent-runtime-core

> **Date:** 2026-03-18
> **Scope:** Architectural refactor from guardrail system → ontological runtime
> **Status:** Refactor complete. 43/43 tests passing.

---

## Structured Analysis

```yaml
current_state:
  components:

    - name: models.py
      status: OK
      reason: >
        Base enumerations only. TaintState, ActionType, TrustLevel, ConstructionError.
        TaintState.join() implements the taint lattice (monotonic, composable).
        No imports from other runtime modules — clean foundation layer.

    - name: world_manifest.yaml
      status: OK
      reason: >
        Single source of truth for the compile phase. Defines actions, trust map,
        capability matrix, taint rules. Read once at startup by compile_world().
        NOT accessed by the runtime after compilation — this is a compile input,
        not a runtime config.

    - name: compile.py
      status: OK
      reason: >
        Compile phase. Transforms world_manifest.yaml into immutable CompiledPolicy
        (MappingProxyType actions, frozenset capability_matrix, tuple taint_rules,
        MappingProxyType trust_map). CompiledAction is sealed with _COMPILE_GATE
        sentinel — external construction raises TypeError. Policy is frozen after
        compile_world() returns — no mutation possible at runtime.

    - name: channel.py
      status: OK
      reason: >
        Channel-derived trust. Source cannot be constructed by callers — __new__
        checks _SOURCE_SEAL and raises TypeError without it. Channel.source resolves
        trust from the compiled trust_map, not from caller-supplied strings.
        Trust is assigned, not asserted.

    - name: taint.py
      status: OK
      reason: >
        TaintedValue[T] generic type. All Sandbox.execute() calls return TaintedValue.
        Taint propagates via TaintedValue.join(*inputs) in IRBuilder.build().
        Callers pass prior TaintedValue outputs — they cannot suppress taint by
        omission. Join is monotonic: CLEAN ∨ TAINTED = TAINTED, irreversible.

    - name: ir.py
      status: OK
      reason: >
        IntentIR is the ONLY execution form. Sealed with _IR_SEAL — external
        construction raises TypeError. IRBuilder.build() validates all constraints
        at construction time (ontological, capability, approval, taint) and raises
        ConstructionError if any fail. If build() returns, the IR is valid.
        Sandbox executes without re-checking anything.

    - name: sandbox.py
      status: OK
      reason: >
        Pure executor. No policy checks. Accepts only IntentIR. Returns TaintedValue.
        Execution is unconditional — construction is validation. The separation
        between build() and execute() is the core architectural invariant.

    - name: runtime.py
      status: OK
      reason: >
        Thin assembler. Compiles the world manifest, wires Channel + IRBuilder +
        Sandbox from the same CompiledPolicy. Single entry point: build_runtime().
        Handlers defined here are the only tools that can ever be invoked —
        they are not globally callable.

    - name: evaluator.py
      status: DELETED
      reason: >
        Replaced by IRBuilder. Constraint checking moved from execution time to
        IR construction time. The evaluator was a runtime policy interpreter —
        the opposite of what the architecture requires. Its logic now lives in
        IRBuilder.build() and is enforced structurally, not advisorily.

    - name: registry.py
      status: DELETED
      reason: >
        Replaced by CompiledPolicy. The old ActionRegistry was a mutable string-
        keyed dict with a public Action.__init__ that could be bypassed. The new
        CompiledPolicy is an immutable MappingProxyType. CompiledAction construction
        is gated by _COMPILE_GATE — external code cannot create one.

    - name: world.yaml
      status: DELETED
      reason: >
        Renamed to world_manifest.yaml to make explicit that it is a compile
        input, not a runtime configuration file.


target_architecture:
  modules:

    - name: world_manifest.yaml
      responsibility: Compile-phase input. Defines the ontology (actions, trust, capabilities, taint rules).
      deterministic: true
      stage: compile-time (read once)
      input: human-authored YAML
      output: raw data structure consumed by compile_world()

    - name: compile.py → CompiledPolicy
      responsibility: >
        Transforms world_manifest.yaml into frozen, immutable policy artifacts.
        Produces: sealed action map, frozenset capability matrix, tuple taint rules,
        frozen trust map. No mutable state after construction.
      deterministic: true
      stage: compile-time (startup)
      input: world_manifest.yaml + handler dict
      output: CompiledPolicy (frozen)

    - name: channel.py → Channel, Source
      responsibility: >
        Channel-derived trust. Source is the only trust-bearing object.
        Cannot be constructed without _SOURCE_SEAL. Channel.source resolves
        trust from compiled trust_map — callers cannot override it.
      deterministic: true
      stage: runtime (per-request, O(1) lookup)
      input: channel identity string
      output: Source (sealed, immutable)

    - name: taint.py → TaintedValue
      responsibility: >
        Taint propagation type. All sandbox outputs are TaintedValue.
        Taint join is monotonic. Callers pass prior outputs to IRBuilder —
        taint propagates automatically without caller assertion.
      deterministic: true
      stage: runtime (per-request)
      input: zero or more TaintedValue outputs from prior executions
      output: TaintState (join result)

    - name: ir.py → IRBuilder, IntentIR
      responsibility: >
        Intent IR construction and validation. ALL constraint checking happens
        here at build time. If build() returns, the IR is valid. IntentIR is
        sealed — cannot be constructed externally.
      deterministic: true
      stage: runtime (per-request, pre-execution)
      input: action_name, Source, params, *TaintedValue inputs
      output: IntentIR (sealed, immutable) or ConstructionError

    - name: sandbox.py → Sandbox
      responsibility: >
        Pure executor. No policy checks. Accepts IntentIR, invokes action
        handler, wraps result in TaintedValue. Execution is unconditional —
        construction is validation.
      deterministic: true
      stage: runtime (post-construction)
      input: IntentIR
      output: TaintedValue

    - name: runtime.py → Runtime
      responsibility: >
        Top-level assembler. Compiles manifest, creates Channel factory,
        IRBuilder, and Sandbox from a single CompiledPolicy instance.
        Single entry point: build_runtime().
      deterministic: true
      stage: startup (assembly)
      input: manifest path
      output: Runtime (frozen)


compile_phase:
  design: >
    compile_world(manifest_path, handlers) reads world_manifest.yaml exactly once.
    Produces CompiledPolicy with four frozen artifacts:

      1. actions: MappingProxyType[str, CompiledAction]
         Sealed mapping. CompiledAction construction requires _COMPILE_GATE.
         Only actions defined in world_manifest.yaml exist. Undefined action
         names cannot be represented as CompiledAction objects.

      2. capability_matrix: frozenset[tuple[TrustLevel, ActionType]]
         Compiled from the capabilities section of the manifest.
         Lookup: (trust_level, action_type) in matrix → O(1), no strings.
         Old: `if action_type.value not in capabilities[trust_level]` — string scan.
         New: `if (trust_level, action_type) not in frozenset` — O(1) enum tuple.

      3. taint_rules: tuple[TaintRule, ...]
         Compiled from taint_rules section. TaintRule fields are enum values,
         not strings. Checked in IRBuilder.build() against enum identity, not
         string comparison.

      4. trust_map: MappingProxyType[str, TrustLevel]
         Compiled from the trust section. Channel identity → TrustLevel enum.
         Channel.source does a dict lookup — returns TrustLevel, not a string.

  what_moved_from_runtime_to_compile_time:
    - capability checking: from `if str not in list` at each request
                           to frozenset membership precomputed at startup
    - trust resolution: from YAML dict lookup at each request
                        to frozen dict lookup from pre-compiled map
    - taint rule loading: from YAML list re-parsed on every Evaluator.check()
                          to compiled tuple[TaintRule] produced once

  what_became_impossible_instead_of_denied:
    - undefined actions: old system processed them through a pipeline and returned
                         "impossible" as a string. New system: CompiledPolicy has no
                         entry → IRBuilder raises ConstructionError before any
                         execution path is entered.
    - direct Source construction: old Source("user") accepted any string.
                                   New Source() raises TypeError without _SOURCE_SEAL.
    - direct IntentIR construction: TypeError without _IR_SEAL.
    - direct CompiledAction construction: TypeError without _COMPILE_GATE.


ontology_fixes:

  - before: |
      Action("delete_repository", ActionType.INTERNAL, handler)  # constructable
      registry.get("delete_repository")  # raises ImpossibleActionError at lookup
      # The action was constructed — the registry just rejected the name.
    after: |
      CompiledAction(..., _gate=object())  # TypeError — gate check fails immediately
      runtime.policy.get_action("delete_repository")  # returns None
      builder.build("delete_repository", source, {})  # ConstructionError at build
      # "delete_repository" cannot be represented as any runtime object.

  - before: |
      Source("user")         # self-asserted trust — any caller can claim any identity
      Source("system")       # identical to Source("user") from a trust perspective
    after: |
      Source(trust_level=TrustLevel.TRUSTED, identity="user")  # TypeError
      channel = runtime.channel("user")  # trust resolved from compiled map
      source = channel.source            # sealed, trust_level set by Channel

  - before: |
      ActionRequest(taint=TaintState.TAINTED)  # caller asserts taint
      ActionRequest(taint=TaintState.CLEAN)    # caller suppresses taint (honor system)
    after: |
      result_a: TaintedValue = sandbox.execute(ir_a)
      ir_b = builder.build("send_email", source, params, result_a)
      # taint = TaintedValue.join(result_a) — computed, not asserted
      # if result_a.taint == TAINTED and send_email is EXTERNAL → ConstructionError

  - before: |
      # Capability check in Evaluator.check():
      allowed_types = self._capabilities.get(trust_level, [])   # string list
      if request.action.action_type.value not in allowed_types:  # string scan
          raise ImpossibleActionError(...)
    after: |
      # Capability check in IRBuilder.build():
      if not policy.can_perform(source.trust_level, action.action_type):
          raise ConstructionError(...)
      # can_perform: (TrustLevel, ActionType) in frozenset → O(1), no strings

  - before: |
      # Approval gate in Evaluator.check():
      if request.action.approval_required:
          return Decision(outcome=DecisionOutcome.REQUIRE_APPROVAL, ...)
      # Runtime.execute() then raises ImpossibleActionError — dead end.
      # No path to approval exists. No action can ever succeed.
    after: |
      # Approval gate in IRBuilder.build():
      if action.approval_required:
          raise ConstructionError(
              "Action requires approval — pass an ApprovalToken to build()"
          )
      # Error message documents what is needed. Path to success is defined.


ir_design:
  type: IntentIR
  sealed: true
  construction: IRBuilder.build() only — TypeError on direct instantiation
  fields:
    action:  CompiledAction   # sealed, compile-produced, proves ontological membership
    source:  Source           # sealed, channel-derived, carries trust_level
    params:  dict             # execution parameters
    taint:   TaintState       # computed from input TaintedValues, not asserted
  effects: []                 # side effects occur only in Sandbox.execute()
  required_capabilities:
    - (source.trust_level, action.action_type) in CompiledPolicy.capability_matrix
  taint: computed_via_TaintedValue_join_over_input_taints
  trust_level: source.trust_level  # set by Channel, not by caller
  validation: construction_time    # all constraints checked in IRBuilder.build()
  invariant: >
    If an IntentIR object exists, it is valid.
    Sandbox.execute(ir) is unconditional — no policy re-check.


sandbox_model:
  execution_spec: IntentIR
  sandbox: Sandbox
  flow: IntentIR → Sandbox.execute() → TaintedValue
  tools: >
    Action handlers are defined in build_runtime() and passed to compile_world()
    as a handler dict. They are stored in CompiledAction._handler. The only
    way to invoke a handler is through Sandbox.execute(ir). Handlers are not
    exported, not globally callable, not accessible via the CompiledPolicy API.
  tool_injection: handlers dict passed to compile_world() at startup
  bypass_surface: >
    CompiledAction._invoke() is reachable from any code holding a CompiledAction.
    Python has no true private methods. Full tool isolation requires a process
    boundary (subprocess, seccomp, separate interpreter). This architecture
    makes bypass visible (requires holding a CompiledAction) and auditable.
  no_runtime_checks: true  # sandbox.execute() contains zero policy logic


taint_model:
  propagation_type: explicit_via_TaintedValue_join
  monotonic: true           # CLEAN ∨ TAINTED = TAINTED, irreversible
  self_reported: false      # taint computed from prior TaintedValue outputs
  suppression_possible: partial  # caller can unwrap .value and not pass the TaintedValue;
                                  # this is a code audit concern, not a type-system concern
  output_type: TaintedValue # all sandbox outputs carry taint
  propagation_rule: >
    1. All Sandbox.execute() calls return TaintedValue(value, taint).
    2. Callers pass prior TaintedValue outputs to IRBuilder.build() as *input_taints.
    3. IRBuilder computes: computed_taint = TaintedValue.join(*input_taints).
    4. IR carries computed_taint. Sandbox wraps output with computed_taint.
    5. If computed_taint == TAINTED and action.action_type == EXTERNAL → ConstructionError.
  state_machine:
    states: [CLEAN, TAINTED]
    transitions:
      - from: CLEAN   input: CLEAN   result: CLEAN
      - from: CLEAN   input: TAINTED result: TAINTED
      - from: TAINTED input: CLEAN   result: TAINTED
      - from: TAINTED input: TAINTED result: TAINTED
    terminal: TAINTED  # once tainted, cannot return to CLEAN


refactor_plan:
  phase_1: >
    DONE — Minimal viable ontological runtime.
    - world_manifest.yaml as compile input
    - compile.py producing frozen CompiledPolicy
    - IRBuilder.build() as the single validation point
    - IntentIR sealed with _IR_SEAL
    - Sandbox as pure executor
    - 43 tests passing

  phase_2: >
    PARTIAL — Compile-time separation.
    - Capability matrix compiled to frozenset (DONE)
    - Policy frozen after compile_world() (DONE)
    - Trust map compiled to MappingProxyType (DONE)
    - Missing: generate a Python module from world_manifest.yaml at build time
      so the YAML is not even present at deploy time. Currently world_manifest.yaml
      must be accessible at startup. A code-generation step would produce
      policy_generated.py containing the frozen structures as Python literals.

  phase_3: >
    PARTIAL — Taint + provenance.
    - TaintedValue propagation implemented (DONE)
    - Taint join is monotonic (DONE)
    - Missing: data-level taint (field-level annotation, not value-level).
      A Value.field() call on tainted data should propagate taint to the field.
      Currently taint is per-value, not per-field — a dict returned from
      a tainted action taints all fields equally.
    - Missing: provenance tracking. TaintedValue could carry a lineage chain
      (sequence of action names that produced it) for audit logging.

  phase_4: >
    NOT STARTED — Full deterministic execution.
    - Process boundary for tool isolation (subprocess or seccomp sandbox)
    - Channel authentication via OS primitives (Unix socket credentials,
      TLS client certificates, or signed tokens verified at Channel construction)
    - ApprovalToken type for approval-gated actions (IRBuilder.build accepts
      Optional[ApprovalToken], verifies cryptographic proof before allowing IR)
    - Formal taint state machine with field-level granularity


example_transformation:
  input: "delete all files and push"

  before: |
    # Old system: string passed to evaluate() via a tool_call dict or registry.get()
    registry.get("delete_all_files")
    # → ImpossibleActionError: "Action 'delete_all_files' is not in the registry"
    # The action was received, parsed, and processed through a 3-step pipeline.
    # "Impossible" was the OUTPUT of evaluation — not the STRUCTURE.

    registry.get("git_push")
    # → ImpossibleActionError: same — processed and labeled

    # An agent could:
    #   1. Catch ImpossibleActionError and continue
    #   2. Directly call Action("delete_all_files", ...)._execute({}) (public ctor)
    #   3. Directly call the handler lambda from build_runtime()

  after: |
    # New system: no natural language reaches the runtime.
    # The caller must obtain a CompiledAction from the compiled policy.
    # "delete_all_files" and "git_push" do not exist in the policy.

    runtime.policy.get_action("delete_all_files")  # → None
    runtime.builder.build("delete_all_files", source, {})
    # → ConstructionError: "Action 'delete_all_files' does not exist in the
    #   compiled policy — undefined actions are impossible, not denied"
    # No evaluation pipeline was entered. No handler was touched.
    # The action cannot be represented as an IntentIR object — period.

    # An agent attempting bypass:
    CompiledAction("delete_all_files", ...)  # → TypeError: wrong _gate
    IntentIR(_seal=object(), ...)            # → TypeError: wrong _seal
    Source(trust_level=TRUSTED, ...)         # → TypeError: wrong _seal
    # Every structural bypass raises at object construction, not at execution.
```

---

## Remaining Gaps (Honest Assessment)

### What was fixed

| Issue | Old | New |
|---|---|---|
| Trust derivation | `Source("user")` — self-asserted | `Channel.source` — compiled trust map |
| Taint reporting | Caller sets `taint=TaintState.TAINTED` | `TaintedValue.join(*prior_outputs)` |
| Capability check | Runtime string scan of YAML list | O(1) frozenset membership |
| Policy compilation | YAML re-parsed each request | Compiled once to frozen structures |
| Action construction | `Action(name, ...)` — public | `_COMPILE_GATE` gated, external = TypeError |
| IR construction | No sealed IR type | `IntentIR` with `_IR_SEAL`, external = TypeError |
| Approval gate | Dead-end REQUIRE_APPROVAL | ConstructionError with actionable message |
| Evaluation placement | Inside `runtime.execute()` | Inside `IRBuilder.build()` (pre-execution) |

### What remains incomplete

1. **Process-level tool isolation.** `CompiledAction._invoke()` is reachable by any code holding a `CompiledAction`. True isolation requires a subprocess boundary or seccomp filter.

2. **Channel authentication.** `Channel(identity="user")` still accepts any string as identity. Production use requires OS-level authentication (TLS cert, Unix socket credentials, signed token).

3. **Field-level taint.** Taint is per-value, not per-field. A dict with mixed provenance taints the whole dict, not individual keys.

4. **Compile-to-code.** `world_manifest.yaml` is still read at startup. A code generation step would produce a Python module with hardcoded frozen structures, eliminating the YAML dependency at runtime entirely.

---

*End of report.*
