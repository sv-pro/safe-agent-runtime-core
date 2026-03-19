# Positioning

## One-Line Descriptions

**Technical:**
> "A deterministic runtime that makes unsafe agent actions unrepresentable at construction time."

**Architectural:**
> "A proxy and typed IR layer that enforces a closed tool world for LLM agents — enforcement at construction, not execution."

**Practical:**
> "Typed action execution for agents: if the action isn't in the ontology, no code path produces it."

---

## When to Use This

**Agent tool execution** — any system where an LLM proposes tool calls that a runtime must execute. The proxy sits between the model and execution.

**MCP-style systems** — tool-calling protocols where the server exposes a fixed set of capabilities. The ontology runtime enforces that set structurally, not just by convention.

**AI security and prompt injection mitigation** — attacker-controlled input may influence what the LLM proposes, but cannot produce an `IntentIR` for an action that doesn't exist. Taint tracking blocks tainted data from reaching external actions.

---

## What This Can Become

**Proxy layer for agent systems** — drop `SafeMCPProxy` in front of any tool-calling runtime. The manifest defines the closed world; the proxy enforces it.

**Integration in tool routers** — systems that dispatch LLM-proposed tool calls to backend handlers can use IR construction as the validation step, replacing ad-hoc string matching.

**Safety layer for LLM systems** — the construction-time enforcement model applies wherever an LLM produces structured output that drives execution. The ontology constrains what that output can produce.

---

## What This Is Not

Not a complete agent framework. Not a sandboxing solution at the OS or network level. Not a replacement for authentication, authorization, or secrets management.

It solves one specific problem: **the window between "LLM proposes an action" and "action is executed"**. In most systems, that window includes construction of a request that may later be denied. This runtime closes the window by making invalid actions unconstructible.
