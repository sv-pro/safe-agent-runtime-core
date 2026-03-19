# Ontology Runtime vs Guardrails

## Comparison

| Aspect | Guardrails / Policy Engines | Ontology Runtime |
|---|---|---|
| Action existence | Action is constructed, then checked | Action must exist in manifest to be constructed |
| Enforcement point | After construction (deny at execution) | During construction (impossible to create) |
| Enforcement model | Allow / Deny | Possible / Impossible |
| Tool calls | String names evaluated at runtime | Typed IR, sealed at construction |
| LLM role | Partially trusted (proposals may succeed by default) | Never trusted (proposals must pass construction) |
| Taint handling | Checked at execution boundary | Checked at IR construction; blocks before object exists |
| Trust injection | Often caller-supplied or string-matched | Policy-derived at channel creation; callers cannot inject trust |
| Unknown actions | Constructed, then denied | Cannot be represented; `ConstructionError` at build |
| Policy location | Evaluated at multiple points | Compiled once at startup into a frozen, immutable object |

## What This Means

- **Guardrails filter behavior.** A request is formed, evaluated, and possibly denied. The action exists as an object up to the denial point. A misconfigured filter is a gap.

- **Ontology runtime defines representability.** If an action is not in the manifest, there is no code path that produces an `IntentIR` for it. The question is not "will this be denied?" but "can this exist?"

- **Taint is a construction constraint, not an execution tag.** Tainted data flowing into an external action raises `ConstructionError`. The `ExecutionSpec` is never created. The subprocess is never spawned.

- **Unknown actions are not rejected. They are impossible.** `delete_repository` not in the manifest means `IRBuilder.build("delete_repository", ...)` raises immediately. There is no representation to reject.

- **The enforcement surface is smaller.** Policy is evaluated in one place (`IRBuilder.build()`), not across middleware, filters, or runtime hooks.
