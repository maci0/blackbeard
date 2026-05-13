# Blackbeard — Third-Party Integration Map

## Philosophy

Build the **orchestration and UX layer**. Delegate infrastructure to battle-tested OSS projects. Every component below has been chosen because it is:

1. Open-source with a permissive or copyleft license.
2. Self-hostable (no vendor lock-in).
3. Already adopted at scale (thousands of production deployments).
4. Maintained by an active community or commercial backer.

---

## Integration Matrix

### What we inherit from CrewAI (unchanged)

| Capability | CrewAI Module | Blackbeard Changes |
|------------|---------------|--------------------|
| Agent/Task/Crew/Flow primitives | `crewai.*` | None — import and use |
| YAML config (agents.yaml, tasks.yaml) | `crewai.project` | Extended with `apiVersion/kind/metadata/spec` envelope |
| Memory (unified, scoped, composite scoring) | `crewai.Memory` | None |
| Event bus & listeners | `crewai.events` | Register Blackbeard's own listeners |
| Guardrails (function/LLM/composite) | `crewai.Task.guardrail` | None — add reusable `Guardrail` resource kind |
| Checkpointing (JSON/SQLite) | `crewai.state` | None |
| Tools (`BaseTool`, `@tool` decorator, crewai_tools) | `crewai.tools`, `crewai_tools` | None — add WASM tools and registry |
| Knowledge, Skills | `crewai.knowledge`, `crewai.skills` | None |
| MCP integration | `crewai.mcp` | None |
| A2A protocol | `crewai.a2a` | Extended with Blackbeard auth |
| Process modes (sequential/hierarchical) | `crewai.Process` | None |
| Structured output (Pydantic/JSON) | `Task.output_pydantic` | None |

### What we delegate to third-party OSS

| Concern | Library / Service | What it provides | What Blackbeard builds on top |
|---------|-------------------|------------------|-------------------------------|
| **LLM routing** | **LiteLLM Proxy** | 100+ providers, load balancing, fallbacks, spend tracking per key/team, rate limiting, health checks, virtual keys with budgets | PRD 06: Map AgentPolicy → LiteLLM virtual keys. Generate LiteLLM config from `LLMConnection` resources. Consume spend data for dashboards. |
| **Policy engine** | **Open Policy Agent (OPA)** | General-purpose policy evaluation via Rego language. Sub-millisecond decisions. Used by K8s, Envoy, Terraform. | PRD 03: AgentPolicy YAML compiles to Rego policies. Every tool call, LLM call, delegation, file access is an OPA query. OPA runs as a sidecar. Rego is the internal policy language — users never write it, they use the GUI/YAML. |
| **Identity & auth** | **Ory Kratos** (identity) + **Ory Hydra** (OAuth2/OIDC) | User registration, login, password/passwordless, MFA, SSO, OIDC provider, session management, account recovery | PRD 03: Blackbeard delegates all human authentication to Ory. No custom auth code. Users/sessions/SSO managed by Kratos. OAuth2 flows by Hydra. |
| **Fine-grained authorization** | **SpiceDB** (Google Zanzibar) | Relationship-based access control. Schema + relationships → permission checks. Handles entity-level visibility, inheritance, and cross-cutting. Horizontally scalable. | PRD 03: Entity-level permissions (PRD 03, section 6) use SpiceDB instead of custom DB queries. "Can user X run crew Y?" and "Can agent A access tool B?" are SpiceDB checks. Namespace/org hierarchy modeled as SpiceDB relationships. |
| **PII detection & redaction** | **Microsoft Presidio** | NLP + regex-based PII detection for 20+ entity types, customizable recognizers, anonymizer/deanonymizer. MIT licensed. 8k GitHub stars. | PRD 08: Presidio is the PII engine. `PIIConfig` YAML maps to Presidio recognizer config. Custom recognizers (regex/deny-list) added via Presidio's extension API. Presidio runs as a library, not a service. |
| **Observability & traces** | **Langfuse** (self-hosted) | LLM-native tracing with spans, token/cost tracking, prompt management, evaluations, OpenTelemetry backend. Fully open-source (MIT). | PRD 07: Langfuse is the trace backend and UI. CrewAI events → Langfuse traces via Langfuse SDK. LiteLLM natively supports Langfuse callbacks. Blackbeard embeds Langfuse UI or links to it. Saves building an entire trace storage + visualization layer. |
| **Secrets management** | **Infisical** | Secret storage, rotation, dynamic secrets, RBAC, audit logs, K8s operator, CLI, SDK. 26k GitHub stars. | All PRDs: `EnvironmentVariable` resources with `value_from: secret` resolve through Infisical's API. API keys, OAuth tokens, LLM keys stored in Infisical, never in Blackbeard's DB. |
| **Workflow orchestration** | **Temporal** | Durable execution — workflows survive crashes, restarts, deployments. Built-in retries, timeouts, cron, visibility. Used by Netflix, Snap, Stripe. | PRD 05: Crew/Flow executions are Temporal workflows. Each `kickoff()` → Temporal workflow start. Task execution → Temporal activities. Checkpointing, HITL pauses, and resume are Temporal primitives. Replaces custom Celery/Hatchet layer. |
| **Object storage** | **MinIO** | S3-compatible object storage. Single binary, self-hosted. | All PRDs: Artifact storage (WASM binaries, ZIP deployments, exported files, trace attachments). `s3://` URIs resolve to MinIO. |
| **Cache & pub/sub** | **Valkey** (Redis fork) | In-memory cache, pub/sub, streams. BSD-licensed Linux Foundation project. Drop-in Redis replacement. | Cross-cutting: Session cache, LiteLLM state backend, event bus transport, rate limiting, sandbox warm pool coordination. |
| **WASM runtime** | **Wasmtime** | Production WASM runtime. Component Model support, WASI Preview 2, fuel metering. Bytecode Alliance. | PRD 05: Embedded in execution workers. All WASM tool execution goes through Wasmtime. |
| **Container runtime** | **Docker** + **gVisor** (`runsc`) | Container sandboxing. gVisor adds user-space kernel for syscall filtering. | PRD 05: Docker tier sandboxes. gVisor optional for hardened mode. |
| **Graph editor** | **React Flow** (xyflow) | Canvas rendering, node/edge management, minimap, controls. MIT licensed. | PRD 02: The visual editor framework. |
| **Graph layout** | **ELK.js** | Automatic graph layout algorithm. Eclipse Foundation. | PRD 02: Auto-layout button. |
| **Code editor** | **Monaco Editor** | VS Code's editor component. Syntax highlighting, autocomplete. | PRD 02: YAML and Python path editing in property panels. |
| **Form generation** | **React Hook Form** + **JSON Schema** | Auto-generated forms from schemas with validation. | PRD 02: Property panel forms generated from resource kind schemas. |
| **API docs** | **Scalar** or **Swagger UI** | OpenAPI documentation rendering. | PRD 11: `/api/v1/docs` endpoint. |

---

## Architecture with Integrations

```
┌───────────────────────────────────────────────────────────────────────┐
│                        Blackbeard Platform                            │
│                                                                       │
│   React SPA ──────── React Flow ─── Monaco ─── React Hook Form       │
│       │                                                               │
│       ▼                                                               │
│   ┌────────────────────────────────────────────────┐                  │
│   │              Blackbeard API Server              │                  │
│   │                                                │                  │
│   │  Resource CRUD │ Execution Mgmt │ Studio API   │                  │
│   │       │              │               │         │                  │
│   │   ┌───▼──┐    ┌──────▼──────┐   ┌────▼────┐   │                  │
│   │   │ SpiceDB│    │  Temporal   │   │  OPA    │   │                  │
│   │   │(authz) │    │ (workflows)│   │(policy) │   │                  │
│   │   └───────┘    └─────┬──────┘   └─────────┘   │                  │
│   └───────────────────────┼────────────────────────┘                  │
│                           │                                           │
│   ┌───────────────────────▼────────────────────────┐                  │
│   │           Blackbeard Execution Worker           │                  │
│   │                                                │                  │
│   │   ┌──────────┐  ┌───────────┐  ┌────────────┐ │                  │
│   │   │ CrewAI   │  │ LiteLLM   │  │ Sandbox    │ │                  │
│   │   │ (agents, │  │ Proxy     │  │ Manager    │ │                  │
│   │   │  tasks,  │  │ (routing, │  │            │ │                  │
│   │   │  crews,  │  │  spend,   │  │ ┌────────┐ │ │                  │
│   │   │  flows,  │  │  fallback)│  │ │Wasmtime│ │ │                  │
│   │   │  memory, │  │           │  │ │Docker  │ │ │                  │
│   │   │  events) │  │           │  │ │gVisor  │ │ │                  │
│   │   └──────────┘  └───────────┘  │ └────────┘ │ │                  │
│   │                                └────────────┘ │                  │
│   └────────────────────────────────────────────────┘                  │
│                                                                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│   │ Ory      │  │ Langfuse │  │ Presidio │  │ Infisical│            │
│   │ (identity│  │ (traces, │  │ (PII     │  │ (secrets)│            │
│   │  SSO,    │  │  observ.)│  │  redact) │  │          │            │
│   │  OAuth2) │  │          │  │          │  │          │            │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│                                                                       │
│   ┌──────────┐  ┌──────────┐                                         │
│   │PostgreSQL│  │ Valkey   │  ┌──────────┐                           │
│   │(primary  │  │(cache,   │  │  MinIO   │                           │
│   │ store)   │  │ pub/sub) │  │(objects) │                           │
│   └──────────┘  └──────────┘  └──────────┘                           │
└───────────────────────────────────────────────────────────────────────┘
```

---

## What Blackbeard Actually Builds (the unique value)

After delegating to the above, Blackbeard's custom code is focused on:

| Layer | What we build |
|-------|---------------|
| **Resource model** | `apiVersion/kind/metadata/spec` envelope, `ref:` resolution, resource loader, YAML↔DB sync |
| **Studio UI** | Graph canvas, property panel, node types, edge semantics, AI copilot, YAML↔canvas sync |
| **Execution orchestration** | Resource loader → CrewAI objects, Temporal workflow definitions, sandbox dispatch pipeline, callback resolver |
| **AgentPolicy → enforcement bridge** | Compile YAML policies → OPA Rego + LiteLLM virtual keys + SpiceDB relationships |
| **WASM tool format** | WIT contract, `blackbeard tool compile`, tool registry indexing |
| **Deployment lifecycle** | Build pipeline, Git/ZIP/Studio deploy, versioning, rollback, triggers |
| **Asset repository** | Publish/discover/version/fork agents/tools/crews |
| **Platform API** | REST/gRPC endpoints, webhook streaming, React export, CLI |
| **Observability bridge** | CrewAI events → Langfuse traces, sandbox/policy annotations, Blackbeard-specific dashboards |
| **Glue & UX** | Config generation for all integrated services, unified management UI, setup wizards |

Everything else is delegated to proven infrastructure.

---

## Deployment: One `docker-compose up`

The YAML below is a **reference full-profile** stack (API, worker, LiteLLM, Temporal, OPA, SpiceDB, Ory, etc.). The **repository's** default [`docker-compose.yaml`](../../docker-compose.yaml) follows the MVP: it starts the services needed for local development (for example API, UI, Postgres, Valkey, LiteLLM, Langfuse, Clickhouse/MinIO as required by those images) and **does not** require Temporal, OPA, SpiceDB, or Ory until those milestones ship. See [`MVP-IMPLEMENTATION-PLAN.md`](./MVP-IMPLEMENTATION-PLAN.md).

```yaml
# docker-compose.yaml (simplified, full-profile reference)
services:
  blackbeard-api:
    image: ghcr.io/blackbeard/api:latest
    depends_on: [postgres, valkey, litellm, temporal, opa, spicedb, langfuse]

  blackbeard-worker:
    image: ghcr.io/blackbeard/worker:latest
    depends_on: [postgres, valkey, litellm, temporal, opa, spicedb]
    deploy:
      replicas: 2

  blackbeard-ui:
    image: ghcr.io/blackbeard/ui:latest
    ports: ["3000:80"]

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports: ["4000:4000"]

  temporal:
    image: temporalio/auto-setup:latest
    ports: ["7233:7233"]

  opa:
    image: openpolicyagent/opa:latest
    command: ["run", "--server", "/policies"]
    ports: ["8181:8181"]

  spicedb:
    image: authzed/spicedb:latest
    command: ["serve", "--grpc-preshared-key=${SPICEDB_KEY}"]
    ports: ["50051:50051"]

  ory-kratos:
    image: oryd/kratos:latest
    ports: ["4433:4433", "4434:4434"]

  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3001:3000"]

  # Presidio runs as a Python library inside the worker process
  # (`pip install presidio-analyzer presidio-anonymizer`), not as a separate service.

  infisical:
    image: infisical/infisical:latest
    ports: ["8080:8080"]

  postgres:
    image: postgres:17
    ports: ["5432:5432"]

  valkey:
    image: valkey/valkey:8
    ports: ["6379:6379"]

  minio:
    image: minio/minio:latest
    command: ["server", "/data"]
    ports: ["9000:9000", "9001:9001"]
```

**Total custom images: 3** (API, Worker, UI). Everything else is off-the-shelf.

---

## Optional / Swappable Components

Every integration has a simpler fallback for smaller deployments:

| Full Integration | Simpler Alternative | Trade-off |
|-----------------|---------------------|-----------|
| SpiceDB | PostgreSQL RBAC tables | Loses relationship-based traversal, fine at <100 users |
| Temporal | Celery + Valkey | Loses durable execution guarantees, fine for simple crews |
| Langfuse | Built-in trace tables + basic UI | Loses prompt management, evaluations, advanced analytics |
| Infisical | Environment variables + `.env` files | Loses rotation, audit, RBAC on secrets |
| Ory Kratos/Hydra | Built-in JWT auth + OIDC library | Loses MFA, account recovery, passwordless |
| OPA | In-process Python policy evaluator | Loses Rego ecosystem, harder to audit |
| MinIO | Local filesystem | Loses S3 API, distributed storage |

The MVP implementations (in-process policy check, PostgreSQL-based RBAC) serve as the simple fallbacks listed above. Migration path: MVP ships with in-process checks → post-MVP adds OPA sidecar (same policy logic, different evaluation engine) → SpiceDB replaces PostgreSQL permission queries. Each migration is additive — the simpler implementation remains as a fallback configuration option.

The Helm chart / docker-compose supports profiles: `blackbeard --profile minimal` vs `blackbeard --profile full`.
