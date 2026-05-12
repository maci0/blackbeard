# Blackbeard — Product Requirements Documents

**Domain**: blackbeard.sh

## Overview

**Blackbeard** is an open, self-hosted Agent Management Platform (AMP) that wraps and extends the open-source **CrewAI** framework with enterprise-grade RBAC, a visual editor, sandboxed tool execution, and production deployment infrastructure. It does **not** fork or rewrite CrewAI — it imports it as a dependency and adds the layers CrewAI OSS deliberately leaves to platform operators.

### What CrewAI OSS already provides (we inherit, not reimplement)

| Capability | CrewAI OSS Module | Blackbeard's Relationship |
|------------|-------------------|--------------------------|
| Agent / Task / Crew / Flow primitives | `crewai.Agent`, `crewai.Task`, `crewai.Crew`, `crewai.flow.Flow` | **Inherit.** Blackbeard resources compile down to these classes at runtime. |
| YAML config for agents & tasks | `config/agents.yaml`, `config/tasks.yaml` | **Extend.** Blackbeard adds `apiVersion/kind/metadata/spec` envelope, `ref:` cross-references, and callback fields. CrewAI's plain YAML is a valid subset. |
| Tools (`BaseTool`, `@tool` decorator) | `crewai.tools`, `crewai_tools` | **Inherit.** All existing crewai_tools work unchanged. Blackbeard adds WASM tools, sandbox tiers, and a registry UI. |
| Memory (unified, scoped, composite scoring) | `crewai.Memory` | **Inherit fully.** No changes needed — CrewAI's memory system is already excellent. |
| Flows (event-driven, `@start`/`@listen`/`@router`, state, persistence) | `crewai.flow` | **Inherit.** Blackbeard's Flow YAML compiles to a `Flow` subclass. |
| Checkpointing (JSON/SQLite providers, fork/resume) | `crewai.state.checkpoint_config` | **Inherit.** |
| Event bus & listeners | `crewai.events` | **Inherit and extend.** Blackbeard registers its own listeners for tracing, policy enforcement, and webhook streaming. |
| Guardrails (function, LLM, composite) | `Task.guardrail`, `Task.guardrails` | **Inherit.** Blackbeard adds a `Guardrail` resource kind for reusability and a `HallucinationGuardrail` wrapper. |
| Process modes (sequential, hierarchical) | `crewai.Process` | **Inherit.** |
| Knowledge sources | `crewai.knowledge` | **Inherit.** |
| Skills (prompt injection) | `crewai.skills` | **Inherit.** |
| LLM connections (native: OpenAI, Anthropic, Gemini, Azure, Bedrock) | `crewai.LLM` | **Replace with LiteLLM Proxy.** Blackbeard routes ALL LLM calls through a co-deployed LiteLLM Proxy for unified routing, load balancing, fallbacks, spend tracking, and budget enforcement. |
| MCP integration | `crewai.mcp` | **Inherit.** |
| A2A protocol | `crewai.a2a` | **Inherit and extend** with Blackbeard auth and distributed state. |
| Structured output (Pydantic, JSON) | `Task.output_pydantic`, `Task.output_json` | **Inherit.** |
| Async execution | `akickoff`, `kickoff_async` | **Inherit.** |

### What Blackbeard adds (the platform layer)

| Capability | Why CrewAI OSS doesn't do this |
|------------|-------------------------------|
| **K8s-style RBAC for humans AND agents** | OSS has no auth, no access control, no agent runtime constraints |
| **AgentPolicy** (tool allowlists, LLM budgets, delegation limits, network/FS/sandbox constraints) | OSS trusts all code completely |
| **Visual graph editor (Studio)** | OSS is code-only |
| **Sandbox tiers** (none / WASM / Docker / MicroVM) for tool execution | OSS runs everything in-process |
| **WASM tool format** with WIT interface contract | OSS only supports Python tools |
| **LiteLLM Proxy integration** for model routing, load balancing, fallbacks, per-agent spend tracking | OSS calls providers directly |
| **Deployment & automation lifecycle** (build, deploy, version, rollback, triggers) | OSS is a library, not a platform |
| **Traces & observability UI** with cost tracking | OSS emits events but doesn't store/display them |
| **PII redaction** on traces | OSS has no redaction |
| **Asset repository** (publish, discover, version reusable agents/tools/crews) | OSS has no package registry |
| **Public API, webhooks, React export, plugin SDK** | OSS has no platform API |
| **Team management, SSO, audit logging** | OSS has no multi-user support |

### Architecture: CrewAI + LiteLLM as the engine layer

```
┌─────────────────────────────────────────────────────────────┐
│                     Blackbeard Platform                      │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────────────┐  │
│  │ Studio  │ │  RBAC   │ │ Sandbox  │ │ Deployment /    │  │
│  │ (graph  │ │ & Agent │ │ Manager  │ │ Triggers /      │  │
│  │ editor) │ │ Policy  │ │ (WASM/   │ │ Automations     │  │
│  │         │ │         │ │ Docker/  │ │                 │  │
│  │         │ │         │ │ MicroVM) │ │                 │  │
│  └────┬────┘ └────┬────┘ └────┬─────┘ └────────┬────────┘  │
│       │           │           │                 │           │
│  ┌────▼───────────▼───────────▼─────────────────▼────────┐  │
│  │              Blackbeard Execution Engine               │  │
│  │  Resource Loader → Policy Enforcer → Sandbox Dispatch  │  │
│  │         │                    │                         │  │
│  │  ┌──────▼────────┐  ┌───────▼──────────┐              │  │
│  │  │   CrewAI OSS  │  │  LiteLLM Proxy   │              │  │
│  │  │               │  │                  │              │  │
│  │  │  Agent, Task,  │  │  Model routing,  │              │  │
│  │  │  Crew, Flow,   │  │  load balancing, │              │  │
│  │  │  Memory, Tools,│  │  fallbacks,      │              │  │
│  │  │  Events,       │  │  spend tracking, │              │  │
│  │  │  Checkpoints   │  │  virtual keys,   │              │  │
│  │  │               │  │  100+ providers  │              │  │
│  │  └───────────────┘  └──────────────────┘              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ Traces & │ │ Asset    │ │ API /     │ │ Guardrails   │  │
│  │ Observ.  │ │ Registry │ │ Webhooks  │ │ & PII        │  │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Design principles

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | **CrewAI-native** | Every Blackbeard resource compiles to a real CrewAI object. You can `pip install crewai` and run the same YAML locally without Blackbeard. |
| 2 | **LiteLLM for all LLM traffic** | No custom LLM dispatcher. LiteLLM Proxy handles routing, fallbacks, load balancing, spend tracking. Blackbeard maps AgentPolicies to LiteLLM virtual keys. |
| 3 | **YAML-first, code-minimal** | Resources defined in YAML. Python is used only for callbacks and custom tool implementations, referenced by qualified name — never inlined in YAML. |
| 4 | **K8s-inspired RBAC for humans AND agents** | Objects, verbs, roles, role-bindings, rules, and AgentPolicies. |
| 5 | **Visual graph editor** | Drag-and-drop canvas with arrows. The graph is the source of truth, serialised to YAML. |
| 6 | **Tiered sandboxing** | `none` / `wasm` / `docker` / `microvm` — all production-valid. |
| 7 | **Module isolation** | Each module owns its schema, migrations, API routes, and UI. Modules developed and deployed independently. |
| 8 | **Event-driven core** | Internal event bus (extends CrewAI's `crewai_event_bus`) propagates lifecycle events across modules. |
| 9 | **Self-hosted first** | Docker Compose + Helm chart. No vendor lock-in. |

### Target users

| Persona | Description |
|---------|-------------|
| **Platform engineer** | Sets up Blackbeard, configures integrations, manages infrastructure. Primary user of deployment, RBAC, and observability features. |
| **AI/ML developer** | Builds agents, tasks, and crews. Primary user of Studio, resource model, and tool registry. |
| **Operator** | Monitors running automations, manages LLM budgets, responds to HITL requests. Primary user of dashboards and execution views. |
| **Non-technical stakeholder** | Business users who view dashboards, approve HITL requests, and monitor costs. Does not write YAML or code. Primary consumer of observability UIs, budget reports, and approval workflows. |

Blackbeard targets **teams of 3–20** building production agent workflows. Solo developers can use the `--profile minimal` deployment, but the platform's value increases with team size and governance needs.

### Module map

| PRD # | Module | Key Integration | Description |
|-------|--------|----------------|-------------|
| 00 | **Overview** | — | System-level context, architecture, design principles, module map |
| 00 | **Integration Map** | — | Which OSS libraries we use and why |
| 01 | **Core Object Model** | CrewAI OSS | Blackbeard resource envelope wrapping CrewAI's agents, tasks, crews, flows, tools |
| 02 | **Visual Graph Editor (Studio)** | React Flow, ELK.js, Monaco | Drag-and-drop canvas for composing agents, tasks, and flows |
| 03 | **RBAC & Identity** | Ory Kratos/Hydra, SpiceDB, OPA | K8s-style RBAC for humans; AgentPolicies for agents; SSO; team management |
| 04 | **Tool & Integration Registry** | Wasmtime | Tool catalogue with WASM support, MCP servers, OAuth connectors |
| 05 | **Execution Engine & Sandboxing** | Temporal, Wasmtime, Docker/gVisor | Loads YAML → CrewAI objects, enforces policies via OPA, runs tools in sandboxes |
| 06 | **LiteLLM Integration** | LiteLLM Proxy | Model routing, load balancing, fallbacks, spend tracking, per-agent virtual keys |
| 07 | **Observability & Traces** | Langfuse | Execution traces, token metrics, cost tracking, OpenTelemetry |
| 08 | **Guardrails & Safety** | Microsoft Presidio | Hallucination detection, PII redaction, custom validators |
| 09 | **Deployment & Automation** | — | Build, deploy, version, rollback, triggers, webhooks, A2A |
| 10 | **Agent & Asset Repository** | MinIO | Shared library of reusable agents, tasks, tools, and templates |
| 11 | **API & Extensibility** | — | Public REST/gRPC API, webhook streaming, React component export, plugin SDK |

### Cross-cutting concerns

- **Persistence**: PostgreSQL for relational data, MinIO (S3-compatible) for artifacts, Valkey for caching.
- **Workflow orchestration**: Temporal for durable crew/flow executions.
  - Temporal uses its own persistence backend. Default: shares the Blackbeard PostgreSQL instance with a separate `temporal` database. For production deployments with high workflow volume, a dedicated PostgreSQL instance is recommended.
- **Auth & identity**: Ory Kratos (identity) + Ory Hydra (OAuth2/OIDC).
- **Authorization**: OPA (policy evaluation) + SpiceDB (relationship-based permissions).
- **LLM gateway**: LiteLLM Proxy co-deployed as a sidecar or standalone service.
- **Observability**: Langfuse (self-hosted) for trace storage and visualization.
- **PII**: Microsoft Presidio embedded as a library.
- **Secrets**: Infisical for secret storage and rotation.
- **Config format**: YAML as canonical format; JSON accepted everywhere.
- **Frontend**: React + TypeScript SPA with React Flow, Monaco, ELK.js.

### Event Bus

All modules communicate asynchronously via a shared **event bus**. Every resource mutation, execution lifecycle event, policy decision, and system state change emits a typed event.

**MVP implementation**: In-process Python event emitter (`blackbeard.events.EventBus`), extending CrewAI's `crewai_event_bus` with Blackbeard-specific event types. Single-process, synchronous dispatch — listeners run in the same thread as the emitter.

**Production implementation**: Valkey pub/sub for multi-worker event distribution. Workers subscribe to event channels on startup. Events are fire-and-forget (no persistence or replay). For durable event processing (e.g., webhook delivery with retry), the listener enqueues work into a task queue.

**Event envelope**:
```json
{
  "event": "execution.task_completed",
  "timestamp": "2026-05-10T12:01:23Z",
  "source": "execution-worker-01",
  "data": {
    "execution_id": "exec-abc123",
    "task_name": "research-ai",
    "agent_name": "researcher",
    "duration_ms": 12400
  }
}
```

**Naming convention**: `{module}.{noun}.{verb}` — e.g., `execution.task.completed`, `agent.policy.denied`, `resource.agent.created`, `litellm.key.budget_exceeded`.

Event payload schemas for each module are defined in their respective PRDs (see "Events Emitted" sections).

### Infrastructure components (deployed together)

| Component | Purpose | Default deployment |
|-----------|---------|-------------------|
| **Blackbeard API** | Platform API server | Docker container |
| **Blackbeard Worker** | Execution worker pool | Docker container(s), horizontally scalable |
| **Blackbeard UI** | React SPA | Static files / Nginx |
| **LiteLLM Proxy** | LLM gateway | Docker sidecar or standalone |
| **PostgreSQL** | Relational storage | Docker or managed (RDS, Cloud SQL) |
| **Valkey** | Cache, pub/sub, LiteLLM state backend | Docker or managed |
| **Langfuse** | Trace storage and LLM observability | Docker container |
| **WASM Runtime** | Wasmtime library | Embedded in workers |

---

*Each PRD can be owned by an independent team, but cross-module dependencies exist — particularly around the resource model (PRD 01), execution engine (PRD 05), and RBAC (PRD 03). Dependencies are documented in each PRD.*
