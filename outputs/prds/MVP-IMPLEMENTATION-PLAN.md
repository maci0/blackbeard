# Blackbeard MVP — Implementation Plan

## MVP Definition

The MVP proves one thesis: **you can define agents, tasks, and crews in YAML, wire them together visually, execute them through LiteLLM with sandbox isolation and basic agent policies, and see what happened via live event streaming and LiteLLM's dashboard** -- all from `docker compose up`.

### In scope

| Feature | Scope for MVP |
|---------|---------------|
| Resource model | Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail, Role, RoleBinding, Flow (CRUD only, no execution), KnowledgeSource (CRUD only, not wired to execution). No EnvironmentVariable, Namespace, or standalone ServiceAccount resource yet. |
| Visual editor | Canvas with Agent/Task/Tool nodes, edges for context/tool assignment, property panel, YAML tab |
| Execution | Sequential crews + sequential flow steps (crew/function). Train and test via CrewAI native. No hierarchical process, no flow router/condition steps. |
| LLM routing | LiteLLM Proxy with basic config generation from LLMConnection resources |
| Sandbox | `none` and `wasm` tiers only (no Docker/MicroVM sandbox) |
| Tools | Python tools (`BaseTool`), WASM tools, and MCP tools (stdio + HTTP). No OAuth integrations |
| Agent policy | Tool allowlists/denylists, LLM budget enforcement via per-execution LiteLLM virtual keys, delegation constraints (allowed/targets). Audit logging on all mutations. No network/FS policy enforcement at runtime. |
| Guardrails | Task-level guardrails (function-based and LLM-based) — wired through CrewAI's built-in guardrail system. No namespace or crew-level guardrails |
| Observability | Execution event log + SSE streaming + WebSocket streaming + LiteLLM dashboard + audit log API |
| API | REST CRUD for resources + kickoff/status endpoints. No gRPC, no webhooks |
| Auth & RBAC | Built-in email/password auth with JWT tokens (access + refresh). User and Group models. Role and RoleBinding resource kinds with predefined roles (owner/admin/developer/operator/viewer/policy-admin + agent roles). Authorization middleware accepts both `X-API-Key` and `Authorization: Bearer <jwt>`. Visual RBAC editor (Roles, Users, RoleBindings). No SSO/OIDC, no SpiceDB, no OPA. |
| CLI | Full parity with UI: `apply`, `validate`, `kickoff`, `status`, `get`, `list`, `delete`, `export`, `login`/`logout`/`whoami`/`register`, `user list/invite`, `group list/create/delete`, `role list/describe`, `rolebinding list/create`, `executions`, `events --follow`, `cancel`. JWT credential storage in `~/.config/blackbeard/`. |
| Deployment | `docker compose up` only. No Helm, no Git deploy, no triggers |

### Out of scope (post-MVP)

| Feature | Why deferred |
|---------|-------------|
| Ory Kratos/Hydra (SSO/OIDC) | Built-in auth covers MVP; SSO deferred |
| SpiceDB (relationship-based AC) | Role-based RBAC covers MVP; entity-level permissions deferred |
| OPA (policy-as-code) | MVP policies are simple allowlists — in-process Python check is fine |
| Temporal (workflow orchestration) | Sequential crews don't need durable execution; in-process is fine |
| Presidio (PII redaction) | Not critical for MVP; execution events are stored in own DB |
| Infisical (secrets) | `.env` files are fine for MVP |
| MinIO (object storage) | Git-based asset management via export/apply; no blob store needed |
| Flow router/condition steps | Sequential flow steps work; dynamic routing deferred |
| Hierarchical process | Sequential is enough for MVP |
| Docker/MicroVM sandbox tiers | `none` + `wasm` covers most cases |
| OAuth integrations (Gmail, Slack, etc.) | Complex, not core |
| A2A protocol | Inter-agent comms deferred |
| Asset repository | Git-based via export/apply; custom registry deferred |
| React component export | Post-MVP UX feature |
| Webhook streaming | Post-MVP integration feature |
| Plugin SDK | Post-MVP extensibility |
| Namespace-level guardrails | Task-level guardrails are sufficient for MVP |
| gRPC API | REST only for MVP |
| Python/TypeScript SDKs | CLI and REST API cover MVP use cases |

---

## Tech Stack (MVP)

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13+, FastAPI, SQLAlchemy (async), Pydantic v2 |
| **Database** | PostgreSQL 18 (17+ supported) |
| **Cache** | Valkey 9 (Redis-compatible) |
| **LLM gateway** | LiteLLM Proxy |
| **Observability** | LiteLLM dashboard (`:4000/ui`) + execution_events table + SSE |
| **WASM runtime** | wasmtime-py (Python bindings for Wasmtime) |
| **Frontend** | React 19, TypeScript, Vite |
| **Graph editor** | React Flow (xyflow v12) |
| **Code editor** | Monaco Editor |
| **Forms** | React Hook Form + Zod |
| **State** | Zustand |
| **Styling** | Tailwind CSS + shadcn/ui |
| **CLI** | Click (Python) |
| **CrewAI** | `crewai` with a narrow range in `pyproject.toml` (e.g. `>=1.14,<2`); pin an exact version for release builds per PRD 00 (Compatibility strategy) |

---

## Repository Structure

```
blackbeard/
├── docker-compose.yaml                # One command to start everything
├── .env.example                       # Required env vars
│
├── backend/                           # Python backend (FastAPI)
│   ├── pyproject.toml
│   ├── blackbeard/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app
│   │   ├── config.py                  # Settings / env parsing
│   │   │
│   │   ├── models/                    # SQLAlchemy + Pydantic models
│   │   │   ├── database.py            # Engine and session factory
│   │   │   ├── resource.py            # Generic resource table
│   │   │   ├── resource_schemas.py    # Pydantic schemas for resource API
│   │   │   ├── execution.py           # Execution records
│   │   │   └── execution_schemas.py   # Pydantic schemas for execution API
│   │   │
│   │   ├── resources/                 # Resource system
│   │   │   ├── service.py             # Generic resource CRUD
│   │   │   ├── validator.py           # JSON Schema validation per kind
│   │   │   ├── spec_schemas.py        # Per-kind spec schemas
│   │   │   ├── refs.py                # ref: resolution and dependency graph
│   │   │   └── kinds.py               # Kind registry and URL plural mapping
│   │   │
│   │   ├── engine/                    # Execution engine
│   │   │   ├── loader.py              # YAML → CrewAI objects
│   │   │   ├── executor.py            # Kickoff and manage runs
│   │   │   ├── policy.py              # AgentPolicy enforcement
│   │   │   └── sandbox/               # Sandbox manager (none + wasm)
│   │   │       ├── selector.py        # Tier selection (tool + policy)
│   │   │       └── wasm_runtime.py    # Wasmtime wrapper
│   │   │
│   │   ├── litellm/                   # LiteLLM integration
│   │   │   ├── config_gen.py          # LLMConnection → litellm config.yaml
│   │   │   ├── key_manager.py         # Virtual key lifecycle
│   │   │   └── helpers.py             # LiteLLM utility functions
│   │   │
│   │   ├── langfuse/                  # Execution event system (legacy module name; does NOT depend on Langfuse)
│   │   │   ├── listener.py            # CrewAI events → execution_events table
│   │   │   └── client.py              # Event client
│   │   │
│   │   ├── api/                       # API routes
│   │   │   ├── resources.py           # Generic CRUD endpoints
│   │   │   ├── executions.py          # Kickoff, status, stream
│   │   │   ├── health.py              # Health check endpoint
│   │   │   └── middleware.py          # Auth, request ID, body size limiter
│   │   │
│   │   └── cli/                       # CLI commands
│   │       ├── __main__.py
│   │       ├── apply.py
│   │       ├── validate.py
│   │       ├── kickoff.py
│   │       └── status.py
│   │
│   └── tests/
│       ├── test_loader.py
│       ├── test_executor.py
│       ├── test_policy.py
│       ├── test_sandbox.py
│       └── test_api.py
│
├── frontend/                          # React SPA
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Studio.tsx             # Graph editor page
│   │   │   ├── Resources.tsx          # Resource list/detail
│   │   │   ├── Executions.tsx         # Execution list
│   │   │   ├── ExecutionDetail.tsx    # Single execution view
│   │   │   ├── Models.tsx             # LLM connection management
│   │   │   └── Tools.tsx              # Tool registry
│   │   │
│   │   ├── components/
│   │   │   ├── studio/                # Graph editor components
│   │   │   │   ├── Canvas.tsx         # React Flow wrapper
│   │   │   │   ├── nodes/
│   │   │   │   │   ├── AgentNode.tsx
│   │   │   │   │   ├── TaskNode.tsx
│   │   │   │   │   └── ToolNode.tsx
│   │   │   │   ├── edges/
│   │   │   │   │   ├── DataFlowEdge.tsx
│   │   │   │   │   └── ToolAssignEdge.tsx
│   │   │   │   ├── PropertyPanel.tsx
│   │   │   │   ├── Palette.tsx
│   │   │   │   └── YamlEditor.tsx
│   │   │   │
│   │   │   └── shared/                # Shared UI components
│   │   │
│   │   ├── stores/                    # Zustand stores
│   │   │   ├── resourceStore.ts
│   │   │   ├── studioStore.ts
│   │   │   └── executionStore.ts
│   │   │
│   │   └── api/                       # API client
│   │       └── client.ts
│   │
│   └── tests/
│
├── examples/                          # Example crews for testing
│   ├── research-crew/
│   │   ├── agents/researcher.yaml
│   │   ├── agents/writer.yaml
│   │   ├── tasks/research.yaml
│   │   ├── tasks/write-report.yaml
│   │   ├── tools/serper-search.yaml
│   │   ├── crews/research-crew.yaml
│   │   └── llm-connections/openai.yaml
│   │
│   └── simple-crew/
│       └── ...
│
└── deploy/
    ├── docker/
    │   ├── Dockerfile.api            # API + worker in same process for MVP
    │   └── Dockerfile.ui
    └── litellm/
        └── config.yaml
```

---

## Phases

### Phase 0 — Skeleton (Week 1)

**Goal**: `docker compose up` boots all services; API returns health check; UI loads.

| # | Task | Output | Days |
|---|------|--------|------|
| 0.1 | Scaffold backend (FastAPI + SQLAlchemy + CORS middleware) | `/api/v1/health` returns 200, CORS configured for frontend origin | 0.5 |
| 0.1b | Set up DB schema creation via `Base.metadata.create_all()` in entrypoint | Tables created on first startup against fresh DB | 0.5 |
| 0.1c | Implement API key middleware: validate `X-API-Key` header against `BLACKBEARD_API_KEY` env var, return 401 on mismatch | Unauthenticated requests rejected | 0.5 |
| 0.2 | Scaffold frontend (Vite + React + React Flow + Tailwind + shadcn/ui + React Router + layout shell with sidebar nav placeholder) | Blank canvas loads at `:3000` with navigation shell | 0.5 |
| 0.3 | Write `docker-compose.yaml` with all services | `docker compose up` boots: API, UI, PostgreSQL, Valkey, LiteLLM (5 containers) | 1 |
| 0.4 | Create `.env.example` with all required vars | Documented with comments explaining each var. Must include: `OPENAI_API_KEY`, `BLACKBEARD_API_KEY`, `LITELLM_MASTER_KEY`, `DATABASE_URL`, `VALKEY_URL` | 0.5 |
| 0.5 | Set up CI (GitHub Actions): lint, type-check, test | Green pipeline on empty tests | 0.5 |
| 0.6 | Write the example `research-crew/` YAML files by hand | Valid YAML resources to test against | 0.5 |
| 0.7 | WASM proof-of-concept spike: compile a simple Python tool to WASM via componentize-py, load in wasmtime-py with Component Model, invoke, measure startup | Spike report: works / doesn't work / needs fallback. If fail → switch Phase 4 to subprocess-based Wasmtime CLI | 2 |

> **Gate:** The spike result gates Phase 4's approach. If the spike fails, Phase 4 switches to subprocess-based Wasmtime CLI immediately — do not wait until Phase 4 to discover this.

**Deliverable**: Run `docker compose up`, hit `localhost:3000` and see the UI shell, hit `localhost:8000/api/v1/health` and get 200, LiteLLM responds on `:4000` (dashboard at `:4000/ui`).

---

### Phase 1 — Resource Model + API (Weeks 2–3)

**Goal**: YAML resources can be created, validated, stored, and retrieved through the API.

| # | Task | Output | Days |
|---|------|--------|------|
| 1.1 | Create `resources` SQLAlchemy model (id, kind, name, namespace, labels, spec, raw_yaml, version) | Table created via `Base.metadata.create_all()` | 1 |
| 1.2 | Create `resource_refs` SQLAlchemy model (source_id, target_kind, target_name, ref_field) | Table created via `Base.metadata.create_all()` | 0.5 |
| 1.3 | Implement generic resource CRUD service | `create()`, `get()`, `list()`, `update()`, `delete()` with optimistic locking | 2 |
| 1.4 | Implement JSON Schema validators for each kind (Agent, Task, Crew, Tool, LLMConnection) | Schema files + validation on create/update | 2 |
| 1.5 | Implement `ref:` resolution — parse refs, build dependency graph, detect cycles | `ResourceLoader.resolve(name, kind) → Resource` | 2 |
| 1.6 | Implement REST API endpoints (`/api/v1/agents`, `/api/v1/tasks`, etc. — lowercase plural CRUD) | OpenAPI spec auto-generated | 1 |
| 1.7 | Implement `blackbeard validate` CLI command | Validates a directory of YAML files offline | 1 |
| 1.8 | Implement `blackbeard apply` CLI command | Creates/updates resources from YAML files | 1 |
| 1.9 | Write tests: CRUD, validation, ref resolution, cycle detection | ≥80% coverage on resource module | 1.5 |

**Deliverable**: `blackbeard apply -f examples/research-crew/` succeeds. `curl localhost:8000/api/v1/agents` returns the agents. Invalid YAML is rejected with actionable errors. `ref:` cross-references resolve correctly.

**Acceptance tests**:
```bash
blackbeard apply -f examples/research-crew/
blackbeard validate examples/research-crew/     # exits 0
curl localhost:8000/api/v1/agents                # returns researcher, writer
curl localhost:8000/api/v1/agents/researcher     # returns full spec
curl localhost:8000/api/v1/crews/research-crew   # returns crew with resolved refs
# Introduce a cycle → validate exits 1 with clear error
# Reference nonexistent tool → validate exits 1 with "tools/xyz not found"
```

---

### Phase 2 — Execution Engine (Weeks 3–5)

**Goal**: `blackbeard kickoff` runs a crew end-to-end using CrewAI, routed through LiteLLM.

| # | Task | Output | Days |
|---|------|--------|------|
| 2.0 | Create `executions`, `execution_tasks`, `execution_tool_calls` SQLAlchemy models | Tables created via `Base.metadata.create_all()` | 0.5 |
| 2.1 | Implement Resource Loader: YAML resources → CrewAI Agent/Task/Crew objects | `loader.build_crew(crew_name) → crewai.Crew` | 3 |
| 2.2 | Implement LiteLLM config generation: LLMConnection resources → `litellm_config.yaml` | Auto-regenerated on LLMConnection change. Includes schema validation before reload — malformed LLMConnection cannot crash LiteLLM (see PRD 06 config reload safety) | 2 |
| 2.3 | Implement LiteLLM virtual key manager: create per-execution key with model restrictions | `key_manager.create_key(agent, execution) → api_key` | 2 |
| 2.4 | Wire CrewAI `LLM` class to point at LiteLLM Proxy with per-agent virtual key | Agent LLM calls go through `http://litellm:4000` | 1 |
| 2.5 | Implement execution lifecycle: `kickoff()` → create execution record → run crew → store result | `executions` table, status transitions | 2 |
| 2.6 | Implement async execution (background thread with `concurrent.futures`) | Kickoff returns immediately, poll for status | 1 |

> **Note**: Each execution runs in its own thread. CrewAI uses thread-local state, so concurrent executions don't interfere. Maximum concurrent executions configurable via `MAX_CONCURRENT_EXECUTIONS` env var (default: 4).

| 2.7 | Implement callback resolver: dotted Python paths → callable | `"myproject.callbacks:on_done"` → function | 1 |
| 2.8 | Implement API: `POST /api/v1/crews/{name}/kickoff`, `GET /api/v1/executions/{id}` | Kickoff and poll endpoints | 1 |
| 2.9 | Implement SSE streaming endpoint: `GET /api/v1/executions/{id}/stream` | Real-time execution events for UI (task started/completed, tool calls, tokens) | 1 |
| 2.9b | Define SSE event type enum and payload schemas (see PRD 05 SSE Event Types) | Documented event schema that frontend team can build against | 0.5 |
| 2.10 | Implement `blackbeard kickoff` and `blackbeard status` CLI commands | CLI-driven execution | 1 |
| 2.11 | Write tests: loader, executor, LiteLLM key lifecycle | Integration tests with real CrewAI (mocked LLM) | 2 |
| 2.12 | Implement error handling: LLM timeout/retry, tool error feedback, callback failure isolation | Errors don't crash execution; agent receives error messages and adapts | 1.5 |

**Deliverable**: `blackbeard apply -f examples/research-crew/ && blackbeard kickoff crews/research-crew --input topic="AI safety"` runs the crew, all LLM calls go through LiteLLM, execution record stored in DB with status/outputs/token usage.

**Acceptance tests**:
```bash
blackbeard kickoff crews/research-crew --input topic="AI safety"
# → execution_id: exec-abc123, status: queued

blackbeard status exec-abc123
# → status: running, current_task: research, tokens: 4200

# (wait)
blackbeard status exec-abc123
# → status: completed, outputs: "...", total_tokens: 15600, cost_usd: 0.23

# LiteLLM spend:
curl litellm:4000/key/info -H "Authorization: Bearer $MASTER_KEY" -d '{"key": "sk-exec-abc123"}'
# → spend matches execution record
```

---

### Phase 3 — Execution Event System (Week 5)

**Goal**: Every execution produces a complete event log, streamed live to the frontend via SSE.

| # | Task | Output | Days |
|---|------|--------|------|
| 3.0 | Create `execution_events` SQLAlchemy model (id, execution_id, sequence, event_type, timestamp, data JSONB) | Table created via `Base.metadata.create_all()` | 0.5 |
| 3.1 | Register CrewAI `BaseEventListener` that captures events to `execution_events` table | `BlackbeardEventListener` class | 2 |
| 3.2 | Map CrewAI events: `CrewKickoff*` -> crew_started/completed, `TaskStarted/Completed` -> task_started/completed, `ToolUsage*` -> tool_started/finished, `LLMCall*` -> llm_started/completed | Correct event sequence | 1 |
| 3.3 | Implement SSE streaming endpoint: `GET /api/v1/executions/{id}/events/stream` with `?after_sequence=N` reconnection support | Live event streaming to frontend | 1.5 |
| 3.4 | Implement REST endpoint: `GET /api/v1/executions/{id}/events` with optional `event_type` filter | Historical event replay | 0.5 |
| 3.5 | Update `execution_tasks` status live as task events occur (running/completed/failed) | Real-time task progress | 0.5 |

**Deliverable**: After a crew runs, the execution detail page shows a complete event timeline. During execution, the SSE endpoint streams events in real-time. LLM request details are available in the LiteLLM dashboard at `:4000/ui`.

---

### Phase 4 — WASM Sandbox (Weeks 5–6)

**Goal**: Tools compiled to `.wasm` execute in an isolated Wasmtime sandbox with capability-based access control.

| # | Task | Output | Days |
|---|------|--------|------|
| 4.1 | Define WIT interface (`blackbeard:tool@0.1.0`) | `tool.wit` file | 0.5 |
| 4.2 | Write a reference WASM tool in Rust that implements the WIT interface | `examples/tools/echo-tool.wasm` | 1 |
| 4.3 | Implement Wasmtime wrapper: load `.wasm`, create instance with WASI capabilities, invoke, read result | `WasmSandbox.invoke(tool, input) → output` (budget extra time if Component Model or componentize-py integration proves difficult — see Technical Risks) | 3-5 |
| 4.4 | Implement capability grants: only enable `wasi:http` if tool declares it + policy allows it | Capability filtering at instantiation | 1 |
| 4.5 | Implement fuel metering: set fuel limit, catch `OutOfFuelError` → return timeout to agent | Deterministic execution limits | 0.5 |
| 4.6 | Implement module cache: compiled modules cached in memory, ~5ms instantiation | Cache with LRU eviction | 1 |
| 4.7 | Implement sandbox selection logic: tool.sandbox → policy.minimum_tier → default | `select_sandbox(tool, policy) → tier` | 1 |
| 4.8 | Implement `blackbeard tool compile --lang python` (componentize-py wrapper) | Python → `.wasm` compilation | 1 |
| 4.9 | Write a Python tool, compile to WASM, run it through the sandbox | End-to-end WASM tool test | 1 |

**Deliverable**: A Python tool compiled to `.wasm` with `blackbeard tool compile` runs in Wasmtime sandbox. It cannot access the filesystem or network unless capabilities are granted. Fuel limit enforces execution time bounds.

---

### Phase 5 — Agent Policies (Week 7)

**Goal**: Basic agent policies restrict which tools and LLMs an agent can use.

| # | Task | Output | Days |
|---|------|--------|------|
| 5.1 | Add `AgentPolicy` resource kind with schema validation | YAML resource, stored in DB | 1 |
| 5.2 | Implement policy resolution: agent.spec.policy → crew.spec.default_agent_policy → org default | `resolve_policy(agent, crew) → AgentPolicy` | 1 |
| 5.3 | Implement tool allowlist enforcement: before each tool call, check policy | Denied → system message back to agent | 1 |
| 5.4 | Implement LLM budget enforcement via LiteLLM virtual key `max_budget` | Budget exceeded → execution fails with clear error | 1 |
| 5.5 | Implement sandbox minimum tier enforcement: tool wants `none`, policy floor is `wasm` → promote | `max(tool_tier, policy_minimum)` logic | 0.5 |
| 5.6 | Log all policy denials to execution record + execution_events table | Audit trail | 0.5 |
| 5.7 | Write tests: tool denied, budget exceeded, tier promotion | Edge case coverage | 1 |
| 5.8 | Wire guardrails during resource loading: resolve `guardrails: [ref:guardrails/foo]` to CrewAI guardrail objects | Task guardrails execute on task completion | 1 |
| 5.9 | Implement `Guardrail` resource kind (function-based and LLM string types) | YAML resource, stored in DB, validated | 0.5 |

**Deliverable**: An agent with `tools.mode: allowlist, allow: [tools/search]` cannot invoke `tools/database-admin`. Denial feeds back to the agent as a message. Budget exceeded on LiteLLM key stops execution.

---

### Phase 6 — Studio (Visual Editor) (Weeks 7–10)

**Goal**: Users can compose crews visually with drag-and-drop and see results.

| # | Task | Output | Days |
|---|------|--------|------|
| 6.0 | Create `canvas_layouts` table (resource_kind, resource_name, namespace, layout JSONB, updated_at) | Table created via `Base.metadata.create_all()` | 0.5 |
| 6.1 | Implement `AgentNode` component (avatar, role name, LLM badge, tool count) | Draggable node | 1 |
| 6.2 | Implement `TaskNode` component (task name, agent badge, expected output preview) | Draggable node | 1 |
| 6.3 | Implement `ToolNode` component (tool name, type icon) | Draggable node | 0.5 |
| 6.4 | Implement edge types: `DataFlowEdge` (solid, task→task context) and `ToolAssignEdge` (dashed, tool→agent) | Edge rendering + labels | 1 |
| 6.5 | Implement Palette sidebar: drag Agent/Task/Tool onto canvas to create | Resource creation on drop | 1 |
| 6.6 | Implement PropertyPanel: auto-generated form from resource schema | Select node → edit properties | 3 |
| 6.7 | Implement YAML tab in PropertyPanel: Monaco editor with bidirectional sync | Edit YAML ↔ form ↔ canvas | 2 |
| 6.8 | Implement edge semantics: connecting Task→Task creates `context` ref; connecting Tool→Agent creates `tools` ref | YAML updated on edge creation/deletion | 2 |
| 6.9 | Implement auto-layout (ELK.js) | Toolbar button for automatic arrangement | 1 |
| 6.10 | Implement undo/redo (Zustand middleware) | Ctrl+Z / Ctrl+Shift+Z, 30-snapshot history | 1 |
| 6.11 | Implement save: canvas state → YAML resources → API `PUT` | "Save" button persists to backend | 1 |
| 6.12 | Implement "Run" button: triggers kickoff from studio, shows execution status inline | Run and see results without leaving studio | 1 |
| 6.13 | Implement Execution View: read-only canvas with live status badges on nodes | Nodes show pending/running/completed/failed | 2 |

**Note**: Tasks 6.12 and 6.13 require Phase 2 (Execution Engine) to be complete. If running Phases 2 and 6 in parallel, schedule 6.12–6.13 after Phase 2 finishes.

**Deliverable**: Open Studio → drag agents and tasks onto canvas → connect with arrows → edit properties in panel → click Run → see execution progress on nodes → click completed node to see output/trace.

---

### Phase 7 — Resource Management UI (Week 10–11)

**Goal**: Full web UI for managing resources and executions outside of Studio.

| # | Task | Output | Days |
|---|------|--------|------|
| 7.1 | Resources list page: filterable table by kind, sortable by name/updated | `/resources` route | 1 |
| 7.2 | Resource detail page: rendered spec, YAML view, edit-in-place | `/resources/{kind}/{name}` route | 1.5 |
| 7.3 | Executions list page: table with status, duration, cost, timestamps | `/executions` route | 1 |
| 7.4 | Execution detail page: summary cards (tokens, cost, duration), task list, live event log (SSE), link to LiteLLM dashboard | `/executions/{id}` route | 1.5 |
| 7.5 | Models page: LLMConnection management, health status from LiteLLM, spend summary | `/models` route | 1.5 |
| 7.6 | Tools page: tool registry browser, search, detail view | `/tools` route | 1 |
| 7.7 | Navigation: sidebar with Studio, Resources, Executions, Models, Tools | Layout component | 0.5 |

---

### Phase 8 — Polish & Ship (Week 11–12)

| # | Task | Output | Days |
|---|------|--------|------|
| 8.1 | Write `README.md` with quickstart (clone, `docker compose up`, open browser) | < 5 minutes to first crew run | 1 |
| 8.2 | Write `docs/getting-started.md` with a guided tutorial | Build first crew in Studio walkthrough | 1 |
| 8.3 | Write `docs/yaml-reference.md` with all resource kinds and fields | Complete YAML reference | 1 |
| 8.4 | End-to-end smoke test: `docker compose up` → apply examples → run from UI → check traces | Automated E2E test | 2 |
| 8.5 | Performance sanity check: run a crew with 5 agents, 10 tasks — completes without issues | No obvious bottlenecks | 1 |
| 8.6 | Security review: no secrets in logs, API key required, CORS configured | Basic security hygiene | 1 |
| 8.7 | Cut v0.1.0 release, publish Docker images | `ghcr.io/blackbeard/{api,ui}:0.1.0` (worker is bundled in api for MVP) | 1 |

---

## Timeline Summary

```
Week  1  ████████ Phase 0: Skeleton
Week  2  ████████ Phase 1: Resource Model + API
Week  3  ████████ Phase 1 (cont) + Phase 2 starts
Week  4  ████████ Phase 2: Execution Engine
Week  5  ████████ Phase 2 (finish) + Phase 3: Event System + Phase 4 starts
Week  6  ████████ Phase 4: WASM Sandbox
Week  7  ████████ Phase 5: Agent Policies + Phase 6 starts
Week  8  ████████ Phase 6: Studio (Visual Editor)
Week  9  ████████ Phase 6 (cont)
Week 10  ████████ Phase 6 (finish) + Phase 7: Resource UI
Week 11  ████████ Phase 7 (finish) + Phase 8: Polish
Week 12  ████████ Phase 8: Ship v0.1.0
```

**Total**: ~12 weeks for a solo developer (includes 2 weeks buffer absorbed into Phase 4 WASM and Phase 6 Studio estimates), ~7 weeks for a pair, ~5 weeks for a team of 4.

---

## Dependency Graph

```
Phase 0 (skeleton)
    │
    ▼
Phase 1 (resource model + API)
    │
    ├──────────────────┬─────────────────────┐
    ▼                  ▼                     ▼
Phase 2            Phase 4               Phase 6.1–6.11
(execution         (WASM sandbox)        (studio UI:
 engine)               │                  nodes, edges,
    │                  │                  panel, layout)
    ├──────────────────┘                     │
    ▼                  │                     │
Phase 3 (event system) │               Phase 6.12–6.13
    │                  │               (Run button +
    ├──────────────────┘                Execution View
    ▼                                   — needs Phase 2)
Phase 5 (agent policies
 — needs Phase 3 +
   Phase 4 for sandbox
   tier promotion tests)
    │                                        │
    ├────────────────────────────────────────┘
    ▼
Phase 7 (resource management UI)
    │
    ▼
Phase 8 (polish + ship)
```

Phases 2, 4, and 6 can run **in parallel** after Phase 1. This is the main parallelisation opportunity for a team. Note: Phase 6 tasks 6.12–6.13 (Run button and Execution View) depend on Phase 2 being complete. Phase 5 depends on Phase 4 for sandbox tier promotion tests (task 5.5: tool wants `none`, policy floor is `wasm` → promote).

---

## Key Technical Risks

| Risk | Mitigation |
|------|------------|
| **CrewAI version drift** | Pin to specific CrewAI version. Wrap all CrewAI imports through `blackbeard.engine.compat` module. Run CI against CrewAI latest weekly. |
| **LiteLLM config reload** | LiteLLM supports config reload via API. Blackbeard calls `POST /config/update` on LLMConnection changes. If reload fails, fall back to container restart. |
| **Wasmtime Python bindings maturity** | `wasmtime-py` is well-maintained but Component Model support is newer. Fallback: use subprocess-based Wasmtime CLI if Python bindings have issues. Budget 2x time for Phase 4 if Component Model or componentize-py integration proves difficult. |
| **React Flow performance at scale** | Test with 100 nodes. If laggy, implement viewport culling (React Flow supports this). MVP likely <50 nodes. |
| **YAML ↔ Canvas sync complexity** | Build unidirectional first (YAML → Canvas). Add Canvas → YAML second. Bidirectional sync with conflict resolution is Phase 6.7 — if it's too complex for MVP, ship one-way. |
| **LiteLLM unavailability during execution** | LiteLLM is critical -- if down, kickoffs are rejected with 503. Health checks every 30s detect outages. Execution events are stored in the same PostgreSQL instance, so they are available as long as the DB is up. |

### Most Likely Failure Modes Per Phase

| Phase | Most Likely Failure Mode | Mitigation |
|-------|--------------------------|------------|
| 0 | Docker compose networking issues between services | Test service discovery early; use explicit network aliases |
| 1 | Schema validation edge cases (valid YAML that produces invalid CrewAI objects) | Property-based testing with Hypothesis |
| 2 | Resource Loader ↔ CrewAI constructor mismatch (field name differences, type coercion) | Build comprehensive field mapping table; test with real CrewAI |
| 3 | CrewAI event listener missing events or incorrect event ordering | Test with sample crew; verify event sequence completeness |
| 4 | Component Model / componentize-py failure | Run spike in Phase 0; decide fallback before Phase 4 starts |
| 5 | Policy enforcement gaps (valid tool calls denied or denied calls allowed) | Exhaustive test matrix: (tool_type × policy_mode × sandbox_tier) |
| 6 | Bidirectional YAML sync bugs; form ↔ canvas state inconsistency | Start unidirectional (YAML → canvas); add canvas → YAML incrementally |
| 7 | UI performance with many resources; pagination edge cases | Test with 100+ resources; implement virtual scrolling if needed |
| 8 | E2E test flakiness; race conditions in async execution | Use deterministic mock LLM; add generous timeouts |

---

## Testing Strategy

| Layer | Tool | What |
|-------|------|------|
| **Unit** | pytest | Resource validation, ref resolution, policy logic, sandbox selection |
| **Integration** | pytest + testcontainers | API endpoints, DB operations, LiteLLM key lifecycle |
| **E2E** | pytest + docker compose | Full crew execution from `kickoff` to event log verification |
| **Frontend** | Vitest + React Testing Library | Component rendering, store logic, canvas operations |

**LLM mocking**: Integration tests use a mock LLM server (simple FastAPI app returning canned responses) registered as a LiteLLM model. No real LLM calls in CI. E2E tests optionally use real LLMs gated behind `RUN_E2E_WITH_LLM=true`.

**CI pipeline**: lint → type-check → unit tests → integration tests (with testcontainers) → build Docker images → E2E smoke test.

**Recommended additions to testing strategy:**
- **Property-based testing** (Hypothesis) for schema validation — catches edge cases in YAML parsing that hand-written tests miss
- **Load testing** definition: max concurrent executions (target: 4 per `MAX_CONCURRENT_EXECUTIONS`), max resources in DB (target: 1000+), max nodes on Studio canvas (target: 100)
- **Accessibility testing** is deferred to post-MVP
- **Frontend integration tests** for Studio should verify canvas ↔ API ↔ form consistency (e.g., drag node → API confirms resource → form shows correct values)

---

## Definition of Done (MVP)

- [ ] `docker compose up` starts all services in < 60 seconds
- [ ] `blackbeard apply -f examples/research-crew/` creates all resources
- [ ] `blackbeard kickoff crews/research-crew --input topic="AI"` runs and completes
- [ ] All LLM calls route through LiteLLM (verified in LiteLLM logs)
- [ ] Execution event log complete with correct event sequence; live SSE streaming works
- [ ] Studio: can drag agents/tasks/tools, connect with arrows, edit properties, click Run
- [ ] WASM sandbox: a tool compiled to `.wasm` runs with fuel limits and capability restrictions
- [ ] Agent policy: tool allowlist blocks unauthorized tool use; LLM budget stops execution
- [ ] API: full CRUD on all resource kinds + kickoff/status endpoints
- [ ] CLI: `apply`, `validate`, `kickoff`, `status` commands work
- [ ] Zero custom LLM provider code (all handled by LiteLLM)
- [ ] Execution events stored in PostgreSQL; LLM request details available in LiteLLM dashboard
- [ ] No external trace backend -- observability via execution_events + LiteLLM
- [ ] CI pipeline green: lint, type-check, unit tests, integration tests all pass
- [ ] No secrets in Docker images, logs, or API responses (verified in security review)
- [ ] README gets a developer from clone to running crew in < 5 minutes

---

## Glossary

| Term | Definition | Used In |
|------|-----------|---------|
| **Resource** | Any YAML-defined entity in Blackbeard (Agent, Task, Crew, Tool, etc.) | All PRDs |
| **Kickoff** | Starting an execution of a crew or flow | PRDs 05, 09 |
| **Execution** | A single run of a crew/flow, identified by `execution_id` | PRDs 05, 07 |
| **Automation** | A deployed instance of a Crew or Flow with triggers, versioning, and runtime config (post-MVP) | PRD 09 |
| **Namespace** | A logical isolation boundary for resources, scoping RBAC and defaults | PRDs 01, 03 |
| **Sandbox** | An isolated execution environment for tool code (none/wasm/docker/microvm) | PRDs 03, 05 |
| **Tier** | The isolation level of a sandbox (none < wasm < docker < microvm) | PRD 05 |
| **AgentPolicy** | Runtime constraints on what an agent can do (tools, LLMs, network, delegation) | PRD 03 |
| **Virtual Key** | A LiteLLM API key with budget/model restrictions, scoped to an agent or execution | PRD 06 |
| **ref:** | Cross-resource reference syntax in YAML (`ref:agents/researcher`) | PRD 01 |
| **Principal Chain** | The identity chain for authorization: User → Crew → Agent | PRD 03 |
