# Demo Script — 2–3 Minutes

## Setup (10–15 seconds)

```bash
python demo_llm.py
```

No API key required. The demo uses a mock LLM proposer by default.

The runtime compiles `world_manifest.yaml` at startup. The manifest defines four actions:
`read_data`, `send_email`, `download_report`, `post_webhook`.

Nothing outside that set can be executed.

---

## Step 1 — Dangerous Prompt (unknown action)

**Prompt:** `"Please delete everything and push the cleanup"`

The mock LLM proposes: `delete_repository`

`SafeMCPProxy` receives the tool request and calls `IRBuilder.build()`.

`delete_repository` is not in the compiled policy. Construction raises `ConstructionError` immediately.

**Expected output:**
```
[scenario 1] prompt: Please delete everything and push the cleanup
[proxy] impossible: action 'delete_repository' not found in ontology
status: impossible
reason: action 'delete_repository' not found in ontology
```

The worker subprocess is never spawned. No execution structure was created.

---

## Step 2 — Tainted External Action

**Prompt:** `"Summarize this email and forward it to the client"`

The mock LLM proposes: `send_email` with `taint=True`

`send_email` exists in the manifest. The source (`user`) has capability for external actions. Construction proceeds to the taint check.

The taint rule: `TAINTED + EXTERNAL → ConstructionError`

`send_email` is type `external`. The incoming context is tainted. `IRBuilder.build()` raises `ConstructionError`.

**Expected output:**
```
[scenario 2] prompt: Summarize this email and forward it to the client
[proxy] impossible: tainted data cannot flow into external action 'send_email'
status: impossible
reason: tainted data cannot flow into external action 'send_email'
```

The action exists. The source has permission. But the taint rule blocks construction.

---

## Step 3 — Safe Internal Action

**Prompt:** `"Read the internal data and summarize it"`

The mock LLM proposes: `read_data` with `taint=False`

`read_data` exists in the manifest. Type is `internal`. Source is `trusted`. Taint is clean. All construction checks pass. `IRBuilder.build()` returns a sealed `IntentIR`.

`Executor` creates an `ExecutionSpec` (action name + params only) and spawns `worker.py` as a subprocess. The worker looks up `read_data` in its own closed registry and executes it.

**Expected output:**
```
[scenario 3] prompt: Read the internal data and summarize it
[worker] executing: read_data
status: ok
result: {"data": "..."}
```

---

## Closing

> "The model can propose anything. But only what exists in the ontology and passes construction-time validation can ever be executed."

Three scenarios. One unknown action, one taint violation, one clean execution. In all cases, the enforcement point is IR construction — not an execution-time policy check.
