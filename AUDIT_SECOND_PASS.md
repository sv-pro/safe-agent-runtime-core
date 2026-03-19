# Second-Pass Architectural Audit
## safe-agent-runtime-core

---

```yaml
verdict: "partial ontology runtime"

score:
  overall: 6
  ontology: 8
  execution_boundary: 5
  impossible_model: 6
  taint_model: 6
  determinism: 9
  repo_architecture: 4

confirmed_fixes:
  - Unknown actions now raise ConstructionError at IRBuilder.build() before any
    execution path is entered — ontological absence is real, not labeled denial
  - IRBuilder enforces a 5-stage constraint check before IntentIR is emitted;
    if build() returns, the IR is structurally valid
  - Capability matrix compiled to frozenset[(TrustLevel, ActionType)] —
    O(1) enum identity check replaces runtime string list scan
  - TaintedValue[T] is a real generic typed container with monotonic join;
    taint is a first-class value, not a boolean flag
  - Taint rule fires independently of capability — TAINTED + external raises
    ConstructionError even when trust level is TRUSTED; this IS real independence
  - CompiledPolicy fields are all frozen (MappingProxyType, frozenset, tuple);
    policy cannot be mutated after compile_world() returns
  - No LLM on execution path; same input produces same output deterministically

remaining_issues:
  - _invoke() bypass is a real architectural hole: CompiledAction._invoke() is
    publicly reachable by any caller who holds a CompiledAction reference.
    policy.actions['read_data']._invoke({}) bypasses Sandbox entirely. The
    docstring calls this "architectural enforcement" — it is not enforcement.
    It is convention. Sandbox is NOT the only execution path.
  - Taint threading is voluntary: *input_taints is variadic, passing zero
    arguments is valid Python, and the system silently loses taint tracking.
    A caller can receive TaintedValue from sandbox.execute(), extract .value,
    and pass it to the next build() call with no input_taints. Taint is gone.
    Nothing in the type system prevents or detects this drop.
  - demo.py uses the OLD src/ runtime (src.runtime.Runtime, src.world_loader),
    not the new architecture. The canonical demonstration of the system is the
    advisory system, not the constrained runtime. This is not cosmetic.
  - Two parallel implementations coexist (root-level modern, src/ original)
    with no deprecation, no migration guide, and no clear canonical path.
    The repo cannot credibly claim a unified architecture.
  - approval_required gate raises ConstructionError with no approval workflow.
    Actions flagged approval_required are permanently impossible — there is no
    ApprovalToken type, no approval path, no way to ever execute them. The gate
    is a dead end masquerading as a feature.
  - CompiledAction sealed constructor uses _COMPILE_GATE sentinel but Python
    allows object.__new__(CompiledAction) + object.__setattr__() to fabricate
    one without the gate. Acknowledged in docs but not mitigated structurally.

false_progress_if_any:
  - "Sandbox execute() is the only path to handler invocation" — false.
    policy.actions exposes MappingProxyType with all CompiledAction objects.
    Any caller can call action._invoke(params) directly.
  - "Callers cannot suppress taint by omitting inputs they received" — false.
    The docstring asserts this but the signature `*input_taints: TaintedValue`
    is variadic with no minimum arity. Callers can pass zero taints freely.
  - The approval gate is presented as a structural feature; it is a dead end
    with no success path, which is closer to permanent denial than approval.

repo_structure_assessment:
  - Two competing implementations with no deprecation: structurally incoherent
  - Modern impl has clean internal separation (models/compile/channel/taint/ir/
    sandbox/runtime) — good layering within that subtree
  - demo.py drives the OLD architecture, making the modern impl an unreachable
    annex rather than the primary runtime
  - World manifest has 4 actions, all with toy lambda handlers — still PoC-shaped
  - No tests for the modern root-level implementation (tests/ covers src/ only)
  - "still PoC-shaped with a clean modern annex that nobody uses yet"

next_required_steps:
  - Move handler invocation into a true process boundary (subprocess, socket,
    seccomp) or remove _invoke() from the public surface of CompiledAction.
    Until then, Sandbox is advisory, not structural.
  - Enforce taint threading: either require at least one TaintedValue input when
    params reference prior outputs (hard in Python without a DSL), or replace
    *input_taints with a mandatory TaintContext object that callers must construct
    by threading prior outputs — making silent drop a type error, not a convention.
  - Deprecate or remove src/ as the authoritative runtime, and port demo.py to
    the modern architecture. The audit target cannot have two runtimes.
  - Implement ApprovalToken or remove approval_required entirely — a gate with
    no success path is not a feature, it is confusion.
  - Write tests that cover the modern root-level implementation (IRBuilder,
    Sandbox, Channel, TaintedValue propagation chains).
  - Add session/task world shaping: CompiledPolicy is global and static;
    nothing shapes the available action space to a specific task context.
  - Replace toy lambda handlers with something that demonstrates real handler
    isolation (even if minimal) — current handlers prove nothing about sandboxing.

summary: |
  The physics changed in the right places: construction-time ConstructionError
  for unknown actions is real, the frozenset capability matrix is real, and
  TaintedValue's monotonic join is correct. These are genuine improvements over
  the first-pass advisory model. However, two critical gaps prevent crossing
  from "partial" to "minimal constrained runtime." First, Sandbox.execute() is
  NOT the only execution path — _invoke() is directly reachable on any
  CompiledAction, and policy.actions exposes all of them. Second, taint
  threading is voluntary — the variadic *input_taints signature allows silent
  taint drop with no type-level enforcement. Additionally, demo.py drives the
  old src/ runtime, meaning the canonical demonstration is the system this
  refactor was meant to replace. The repo has two architectures, one of which
  is not yet canonical. The modern implementation is a credible prototype of
  the right ideas; it is not yet a constrained runtime because its two most
  important invariants (execution boundary, taint propagation) are enforced by
  convention rather than structure.
```
