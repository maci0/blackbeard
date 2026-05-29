# Architecture

This document describes how Blackbeard is structured: the backend API, the frontend UI, the CLI, the database schema, and how crew executions flow through the system.

---

## System Overview

```
                        ┌──────────────────┐
                        │     Browser      │
                        │                  │
                        └────────┬─────────┘
                                 │ HTTPS
                        ┌────────▼─────────┐
                        │       UI         │
                        │  React + Vite    │
                        │  :3000           │
                        │  (Nginx in prod) │
                        └────────┬─────────┘
                                 │ /api proxy
                        ┌────────▼─────────┐
                        │      API         │
                        │  FastAPI         │
                        │  :8000           │
                        └──┬─────┬──────┬──┘
                           │     │      │
              ┌────────────┘     │      └────────────┐
              │                  │                   │
     ┌────────▼────────┐ ┌──────▼──────┐  ┌─────────▼─────────┐
     │   PostgreSQL    │ │   Valkey    │  │     LiteLLM       │
     │   18            │ │   9         │  │     Proxy         │
     │                 │ │  (pub/sub)  │  │     :4000         │
     │ - resources     │ └─────────────┘  └─────────┬─────────┘
     │ - executions    │                            │
     │ - users/groups  │               ┌────────────┼────────────┐
     │ - litellm data  │               │            │            │
     └─────────────────┘        ┌──────▼──┐  ┌──────▼──┐  ┌─────▼────┐
                                │ Vertex  │  │ OpenAI  │  │ Ollama   │
                                │ AI      │  │         │  │          │
                                └─────────┘  └─────────┘  └──────────┘
```

Five services run in Docker Compose:

1. **UI** -- Static React SPA served by Nginx (Vite dev server in development). Proxies `/api` requests to the API server.
2. **API** -- FastAPI application handling resource CRUD, crew execution, authentication, and WebSocket/SSE streaming.
3. **PostgreSQL 18** -- Primary data store for resources, executions, users, groups, and LiteLLM's own tables.
4. **Valkey 9** -- Redis-compatible store used for real-time collaboration pub/sub (multi-replica WebSocket fan-out).
5. **LiteLLM Proxy** -- Routes LLM calls to configured providers (Vertex AI, OpenAI, Ollama, etc.) and tracks spend, tokens, and latency per virtual key.

---

## Backend Architecture

### Resource System

All entities in Blackbeard are **resources**. Every resource shares a common envelope:

```yaml
apiVersion: blackbeard/v1
kind: Agent          # one of 13 kinds
metadata:
  name: researcher
  project: default
  labels: {}
spec: { ... }        # kind-specific fields
```

Resources are stored in a single `resources` table with a JSONB `spec` column. This design means adding a new resource kind requires only a schema definition -- no new tables or migrations.

```
resources table
┌────┬──────────┬──────────┬───────────┬──────────────────┬─────────┐
│ id │  kind    │  name    │ namespace │       spec       │ version │
├────┼──────────┼──────────┼───────────┼──────────────────┼─────────┤
│  1 │ Agent    │ researcher│ default  │ {"role": "..."}  │       1 │
│  2 │ Task     │ research │ default   │ {"desc": "..."}  │       1 │
│  3 │ Crew     │ my-crew  │ default   │ {"process":...}  │       2 │
└────┴──────────┴──────────┴───────────┴──────────────────┴─────────┘
```

**Key components:**

- **`kinds.py`** -- Single source of truth for the kind registry and URL plural mapping (e.g., `Agent` -> `agents`, `LLMConnection` -> `llm-connections`)
- **`resources/spec_schemas.py`** -- Per-kind JSON schemas used for `spec` validation on create and update
- **`resources/validator.py`** -- Validates resource payloads against schemas and checks structural rules
- **`resources/refs.py`** -- Parses `ref:` strings (e.g., `ref:agents/researcher`) and tracks cross-resource dependencies in a `ResourceRef` table
- **`resources/service.py`** -- Resource CRUD operations (create, read, update, delete, list with filtering)

**Optimistic locking:** Every resource has a `version` integer. Updates must include the current version. If the version does not match, the API returns `409 Conflict`.

**Label selectors:** List endpoints support `label_selector` query parameters (e.g., `?label_selector=env=prod,team=ml`) for filtering resources by labels.

### Execution Engine

The execution engine takes a crew name, resolves all referenced resources, builds CrewAI objects, and runs the crew in a background thread.

```
Execution Flow
──────────────

  POST /api/v1/crews/{name}/kickoff
         │
         ▼
  ┌──────────────────┐
  │ Create Execution │  status: queued
  │ record in DB     │  initiated_by: user
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Derive budget    │  AgentPolicy max_usd/max_tokens
  │ from policies    │  → most restrictive wins
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Create LiteLLM   │  Per-execution virtual key
  │ virtual key      │  with budget caps
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Submit to        │  ThreadPoolExecutor
  │ thread pool      │  (MAX_CONCURRENT_EXECUTIONS)
  └────────┬─────────┘
           │
           ▼  (background thread)
  ┌──────────────────┐
  │ ResourceLoader   │  Resolve refs → build
  │                  │  LLM, Agent, Task, Crew
  │ - resolve refs   │  objects from CrewAI
  │ - build agents   │
  │ - build tasks    │
  │ - build crew     │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ crew.kickoff()   │  status: running
  │ (or .train()     │  CrewAI handles agent
  │  or .test())     │  orchestration
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │ Store results    │  status: completed/failed
  │ Delete virtual   │  Store outputs, token
  │ key              │  usage, cost, error
  └──────────────────┘
```

Each execution gets its own thread with an isolated asyncio event loop. This prevents blocking the FastAPI async loop during long-running crew executions.

**Execution modes:**

| Endpoint                              | Mode      | Description                              |
|---------------------------------------|-----------|------------------------------------------|
| `POST /crews/{name}/kickoff`          | `kickoff` | Standard crew execution                  |
| `POST /crews/{name}/train`            | `train`   | Iterative training with data persistence |
| `POST /crews/{name}/test`             | `test`    | Test run with performance metrics        |
| `POST /flows/{name}/run`              | `flow`    | Multi-step flow execution                |
| `POST /automations/{name}/trigger`    | varies    | API-triggered automation                 |

Executions can also be triggered by Automation resources via cron schedules or incoming webhooks. An `AutomationScheduler` starts during application lifespan and polls for cron-triggered automations.

**Budget enforcement chain:**

1. `AgentPolicy` resource defines `max_usd` and `max_tokens`
2. API creates a LiteLLM virtual key with those limits before execution starts
3. LiteLLM Proxy enforces the limits at call time, rejecting requests that exceed the budget
4. Virtual key is deleted after execution completes (success or failure)

### Authentication and RBAC

Blackbeard supports two authentication methods:

- **API key** -- `X-API-Key` header, validated with `hmac.compare_digest` against `BLACKBEARD_API_KEY`
- **JWT Bearer** -- `Authorization: Bearer <token>`, with 15-minute access tokens and 7-day refresh tokens

**Public endpoints** (no auth required): health checks (`/api/v1/health`, `/api/v1/health/ready`), auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`), OIDC endpoints (`/auth/oidc/login`, `/auth/oidc/callback`, `/config/public`), automation webhook paths (`/automations/{name}/webhook` -- use their own HMAC validation), and API docs (`/docs`, `/redoc` in debug mode).

**RBAC model:**

```
Role                     RoleBinding                 Subject
┌──────────────┐         ┌───────────────────┐       ┌──────────┐
│ name: admin  │◄────────│ role: ref:roles/.. │       │ User     │
│ rules:       │         │ subjects:          │──────▶│ Group    │
│  - resources │         │   - kind: User     │       │ Agent    │
│  - verbs     │         │     name: alice@.. │       │ Crew     │
└──────────────┘         └───────────────────┘       └──────────┘
```

Both `Role` and `RoleBinding` are first-class resources -- managed through the same CRUD API as agents and tasks. The seed script (`deploy/seed.sh`) creates predefined roles: owner, admin, developer, operator, viewer, policy-admin, and agent-scoped roles.

**RBAC enforcement:** API endpoints use a `require_permission()` FastAPI dependency that checks the authenticated user's roles and role bindings before allowing access. Permissions are checked as `(resource_kind, verb)` pairs (e.g., `("Agent", "create")`). If the user lacks the required permission, the API returns `403 Forbidden`.

**Principal chain:** During crew execution, Blackbeard tracks the identity chain: `User -> Crew -> Agent (ServiceAccount)`. Each agent defaults to a service account named `sa-<agent-name>`.

### Middleware Stack

Middleware is applied from outermost to innermost:

1. **CORS** -- `CORSMiddleware` configured via `CORS_ORIGINS`
2. **Security headers** -- CSP, X-Content-Type-Options, X-Frame-Options, etc.
3. **Auth + Request ID** -- API key or JWT validation, `X-Request-Id` header injection
4. **Body size limiter** -- Rejects request bodies over 10MB

### LiteLLM Integration

The API server manages LiteLLM's configuration and uses it as a proxy for all LLM calls:

- **`litellm/config_gen.py`** -- Generates LiteLLM router config from `LLMConnection` resources
- **`litellm/key_manager.py`** -- Creates and deletes per-execution virtual keys for budget enforcement
- **`litellm/helpers.py`** -- Utility functions for model name resolution

**Dynamic model sync:** When `LLMConnection` resources are created, updated, or deleted, the API server pushes changes to LiteLLM via `POST /model/new`, `/model/update`, and `/model/delete`. This means model changes take effect without restarting the LiteLLM container.

LiteLLM's own data (spend tracking, virtual keys) is stored in a separate `litellm` database within the same PostgreSQL instance.

### gRPC Interface

A gRPC server (`blackbeard/grpc/server.py`) starts alongside FastAPI during the application lifespan on port `GRPC_PORT` (default 50051). It delegates to the same `ResourceService` and executor used by the REST API, providing a high-performance interface for programmatic clients. Auth uses the same API key validation (via gRPC metadata). If the gRPC server fails to start, the application continues without it.

---

## Frontend Architecture

### Technology Stack

| Component    | Technology                                |
|-------------|-------------------------------------------|
| Framework   | React 19                                  |
| Language    | TypeScript (strict mode)                  |
| Build       | Vite                                      |
| Styling     | Tailwind CSS                              |
| Components  | Radix UI                                  |
| Graph Editor| @xyflow/react (React Flow v12)            |
| State       | Zustand                                   |

### Page Structure

```
/                     → Dashboard (default) — execution metrics, resource counts, recent activity
/studio               → Visual crew editor
/resources            → Generic resource list (all kinds)
/resources/:kindPlural/:name → Resource detail view
/executions           → Execution list
/executions/:id       → Execution detail with task breakdown
/models               → LLM model management + connectivity test
/chat                 → Chat playground for interactive LLM conversations
/tools                → Tool management
/roles                → RBAC role management
/users                → User management
/audit-logs           → Audit log viewer (all mutation history)
/automations          → Automation management (cron, webhook, API triggers)
/webhooks             → Webhook subscription management
/login                → Login form
/register             → Registration form
/marketplace          → Import crews from git (search, category chips, preview dialog)
/settings             → Platform configuration (user preferences, scheduled reports)
/knowledge            → Knowledge Sources management (card grid with source type badges)
/credentials          → Credentials Manager (centralized secret management)
/guardrails/playground → Guardrail Playground (test guardrails with sample input)
/executions/compare   → Execution Comparison (side-by-side metrics diff, ?a=&b= params)
```

**Command palette:** Press `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux) to open the command palette for quick navigation to any page, resource, or action.

**Global keyboard shortcuts:** `Cmd+Shift+S` (save), `Cmd+Shift+E` (executions), `Cmd+Shift+N` (new resource), `Cmd+.` (settings), `?` (keyboard shortcuts dialog).

**Real-time presence:** `PresenceAvatars` component shows colored avatar circles for users currently viewing the same resource or canvas, powered by WebSocket rooms and Valkey pub/sub.

**Streaming chat:** `POST /api/v1/chat/stream` provides real SSE streaming. The Chat page renders tokens incrementally with a stop button for in-flight cancellation.

**Loading skeletons:** Dashboard, Chat, and KnowledgeSources pages display pulse-animated placeholder shapes while data loads.

### State Management

Two primary Zustand stores:

**`studioStore`** -- Manages the visual editor canvas state:

- Node and edge state for React Flow
- Undo/redo stack (30-snapshot circular buffer)
- Selected node tracking
- Save and load operations

**`resourceStore`** -- Manages CRUD operations for all resource kinds:

- Fetches resources from `/api/v1/{kind_plural}` endpoints
- Handles optimistic locking via `version` field
- Provides loading and error states

### API Client

`src/api/client.ts` is a typed fetch wrapper that:

- Prepends the base URL (proxied through Vite in dev: `:3000/api` -> `:8000`)
- Attaches auth headers (API key or JWT)
- Handles error responses consistently
- Provides typed response objects

---

## CLI Architecture

The CLI (`cli/` directory) is a standalone Python package named `blackbeard-cli` with minimal dependencies:

```
Dependencies: click, httpx, rich, pyyaml, jsonschema
No backend deps: no FastAPI, SQLAlchemy, or CrewAI
```

### Module Structure

```
blackbeard_cli/
├── __main__.py        # Entry point: core commands (apply, validate, get,
│                      #   list, delete, kickoff, train, test-crew, status,
│                      #   pull, health)
├── auth_cmds.py       # login, logout, whoami, register
├── exec.py            # executions (list), events, cancel
├── export_cmd.py      # export (YAML dump of all resources)
├── rbac.py            # role, rolebinding management
├── users.py           # user, group management
├── credentials.py     # JWT credential storage (~/.config/blackbeard/)
├── helpers.py         # Shared utilities, output formatting, auth resolution
├── kinds.py           # Kind registry (copied from backend)
└── resources/         # Schema validation (copied from backend)
```

**Design decisions:**

- The CLI copies `kinds.py` and the `resources/` validation code from the backend. This avoids a runtime dependency on the backend package while keeping validation logic identical.
- Auth resolution order: `--api-key` flag > `BLACKBEARD_API_KEY` env var > stored JWT in `~/.config/blackbeard/`
- All commands support `--json` for machine-readable output
- Resources are applied in topological order (by dependency) to avoid reference errors

---

## Database Schema

### Core Tables

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    resources     │     │  resource_refs   │     │   executions     │
├─────────────────┤     ├──────────────────┤     ├──────────────────┤
│ id         (PK) │     │ id          (PK) │     │ id          (PK) │
│ kind             │◄────│ source_id   (FK) │     │ crew_name        │
│ name             │◄────│ target_kind      │     │ namespace        │
│ namespace        │     │ target_name      │     │ status           │
│ spec      (JSONB)│     │ ref_field        │     │ inputs    (JSONB)│
│ labels    (JSONB)│     └──────────────────┘     │ outputs   (JSONB)│
│ version    (int) │                              │ error            │
│ created_at       │     ┌──────────────────┐     │ total_tokens     │
│ updated_at       │     │     users        │     │ cost_usd         │
└─────────────────┘     ├──────────────────┤     │ initiated_by     │
                        │ id          (PK) │     │ started_at       │
                        │ email       (UQ) │     │ completed_at     │
                        │ display_name     │     │ created_at       │
                        │ password_hash    │     └──────────────────┘
                        │ is_active        │
                        │ created_at       │     ┌──────────────────┐
                        └──────────────────┘     │     groups       │
                                                 ├──────────────────┤
                                                 │ id          (PK) │
                                                 │ name        (UQ) │
                                                 │ description      │
                                                 └──────────────────┘
```

### Schema Management

The database schema is initialized in `backend/entrypoint.sh`:

1. PostgreSQL enum types are created (for execution status, etc.)
2. `Base.metadata.create_all()` creates any missing tables
3. If Alembic is configured (`alembic.ini` + `alembic/versions`), `alembic upgrade head` runs for schema evolution

`create_all` can only create new tables -- it cannot alter existing ones. Alembic handles all schema migrations after initial creation.

---

## Network Architecture

Docker Compose defines two networks:

```
┌──────────────────────────────────────────────────┐
│                 frontend network                  │
│                                                   │
│   ┌──────┐          ┌──────┐                     │
│   │  UI  │─────────▶│  API │                     │
│   └──────┘          └──┬───┘                     │
│                        │                          │
└────────────────────────┼──────────────────────────┘
                         │
┌────────────────────────┼──────────────────────────┐
│                 backend network                    │
│                        │                          │
│   ┌──────┐    ┌────────▼──┐    ┌─────────┐       │
│   │Valkey│◄───│    API    │───▶│LiteLLM  │       │
│   └──────┘    └─────┬─────┘    └────┬────┘       │
│                     │               │             │
│               ┌─────▼───────────────▼────┐       │
│               │       PostgreSQL          │       │
│               └──────────────────────────┘       │
│                                                   │
└───────────────────────────────────────────────────┘
```

- The **UI** container is only on the frontend network. It can reach the API but not the database or cache directly.
- The **API** container is on both networks -- it serves HTTP to the frontend and connects to backend services.
- **PostgreSQL**, **Valkey**, and **LiteLLM** are only on the backend network, not exposed to the frontend.

All containers use `no-new-privileges` and `cap_drop: ALL`. PostgreSQL and Valkey add back only the capabilities they require.

---

## Security Model

### Container Security

| Container  | cap_drop | cap_add                                        | Read-only | PID limit |
|------------|----------|------------------------------------------------|-----------|-----------|
| API        | ALL      | (none)                                         | Yes       | 256       |
| UI         | ALL      | (none)                                         | Yes       | 64        |
| PostgreSQL | ALL      | CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID    | No        | 128       |
| Valkey     | ALL      | SETGID, SETUID                                 | Yes       | 64        |
| LiteLLM    | ALL      | (none)                                         | Yes       | 128       |

### API Security

- Request body size limited to 10MB
- Security headers on all responses (CSP, X-Content-Type-Options, X-Frame-Options)
- API keys compared with `hmac.compare_digest` (constant-time) to prevent timing attacks
- JWT tokens: 15-minute access, 7-day refresh
- All ports bound to `127.0.0.1` only (not exposed to external networks)
- `X-Request-Id` on every response for tracing

### Tool Sandbox Tiers

Tools run in one of five sandbox tiers, ordered by isolation strength:

| Tier | Runtime | Isolation |
|------|---------|-----------|
| `none` | In-process | No isolation |
| `wasm` | wasmtime-py | WebAssembly with WASI capability grants (`http_fetch`, `env`) |
| `docker`/`podman` | Container | Disposable container, no network, read-only FS, caps dropped |
| `gvisor` | runsc | Syscall-level isolation via application kernel on top of Docker/Podman |
| `microvm` | Firecracker or libkrun | Dedicated VM with its own kernel via KVM |

AgentPolicy `sandbox.minimum_tier` promotes tools to a higher tier. The `env` WASI capability exposes only safe variables (`LANG`, `LC_ALL`, `TZ`, `TERM`).

---

## Webhook Delivery

Blackbeard supports webhook notifications for execution lifecycle events. Webhooks are registered via the API and receive HTTP POST callbacks with HMAC-SHA256 signed payloads.

```
POST /api/v1/webhooks           → Register a webhook URL
GET  /api/v1/webhooks           → List registered webhooks
DELETE /api/v1/webhooks/{id}    → Remove a webhook
```

**Event types:** `crew_started`, `task_completed`, `execution_completed`, `execution_failed`, and others. Register with an empty `events` list to receive all event types.

**Signing:** Each webhook has an HMAC-SHA256 signing secret (auto-generated or user-provided). The signature is included in the delivery headers so you can verify authenticity.

**Delivery:** Webhooks are delivered fire-and-forget during execution. The delivery system does not retry failed deliveries in the current implementation.

---

## API Key Management

Users can generate and revoke personal API keys through the API:

```
POST   /api/v1/auth/api-key          → Generate a new API key
DELETE /api/v1/auth/api-key          → Revoke the current API key
```

Generated API keys can be used in the `X-API-Key` header as an alternative to JWT authentication.

---

## Bulk Resource Export

All resources can be exported as a single multi-document YAML file:

```
GET    /api/v1/resources/export      → Returns all resources as multi-document YAML
```

Each resource is separated by `---` in the output. This is useful for backup, version control, or migrating resources between Blackbeard instances. The CLI `blackbeard export --all` command wraps this endpoint.

---

## Audit Logging

All mutation operations are logged to the `audit_logs` table. Each entry records the action, resource type, resource ID, the user who performed the action, and a timestamp.

```
GET /api/v1/audit-logs          → Query the audit log
```

Audited actions include: resource create/update/delete, execution start/cancel, HITL responses, marketplace imports, user management, and webhook registration.

---

## Flow Execution

Flows orchestrate multiple crews and functions into multi-step pipelines with state passing.

```
POST /api/v1/flows/{name}/run   → Run a flow
```

**Execution model:** Flow steps are executed sequentially. Each step of type `crew` builds and kicks off the referenced crew. Step outputs are chained -- the result of step N is available as input context to step N+1.

**Step types:**

| Type | Description |
|------|-------------|
| `crew` | Builds and runs a referenced crew |
| `function` | Invokes a Python function (module:function format, allowlisted) |
| `router` | Routes to different steps based on output |
| `condition` | Conditional step execution based on a simple expression |
| `transform` | Runs a WASM module via `WasmSandbox` to transform step data |

---

## Human-in-the-Loop (HITL)

Tasks with `human_input: true` pause execution and wait for human review. The system supports this through execution events.

```
POST /api/v1/executions/{id}/respond    → Submit a HITL response
GET  /api/v1/executions/{id}/events     → Poll for hitl_request events
```

The frontend polls the events endpoint for `hitl_request` events, presents them to the user, and submits responses via the respond endpoint. The response is recorded as an `hitl_response` event that the execution listener picks up.

---

## Studio: Auto-Layout

The Studio visual editor uses [ELK.js](https://github.com/kieler/elkjs) for automatic graph layout. When you click the auto-layout button, nodes are arranged left-to-right using the ELK layered algorithm, respecting agent-to-task and task-to-crew edges.

**Node types:** Agent, Task, Tool, FlowStep, Condition (diamond, true/false outputs), Router (diamond, N labelled outputs), Parallel (fork/join bar), Crew (bounding box group), and Sticky Note (4 colors, annotation-only, no ports).

**Expression editor:** Condition and Router nodes include an expression editor with syntax validation and variable autocomplete (triggered by `{{` or Ctrl+Space).

**Per-node testing:** PropertyPanel includes "Test Agent" and "Test Task" buttons that run individual nodes against the first available LLMConnection and display results inline.

**Execution data overlay:** After a crew runs, nodes display green borders (success) or red borders (failure) with output preview on hover. A "Clear Results" button resets the overlay.

**Execution timeline:** A Gantt chart at the bottom of the execution view shows horizontal bars per task with status colors and a time scale axis.

**Grouped execution logs:** Execution events are grouped by task with expand/collapse controls (similar to GitHub Actions), showing task name, status, duration, and token count per group.

**Canvas JSON export:** Toolbar "Export" button downloads canvas state as JSON; "Copy as JSON" copies to clipboard.

**Crew Settings:** Configures error workflow (run error crew / retry N times / ignore) via a dialog accessible from crew node context menu.

---

## Marketplace

The Marketplace (`/marketplace` page) allows importing resources from external git repositories or the bundled example library.

**Built-in examples:** Seven example crews (research, code-review, content-pipeline, data-analysis, seo-writer, simple-crew, support-triage) plus a shared tools collection are bundled with the platform and can be imported without any external connectivity.

**Git import:** The backend clones repositories (shallow, HTTPS only), finds all YAML files, validates them against resource schemas, and upserts them via the standard ResourceService. Safety limits apply: 60-second clone timeout, max 200 YAML files, max 256KB per file, symlinks are skipped, and path traversal is prevented.

**Enhanced template gallery:** The Marketplace page includes a search bar for filtering templates, category chips (research, content, code, data, SEO, support), a preview dialog showing full crew details before import, and resource summary badges (agent count, task count, tool count) on each template card.

---

## CLI Package

The CLI (`cli/` directory) is a standalone Python package named `blackbeard-cli` with no server dependencies.

**Dependencies:** click, httpx, rich, pyyaml, jsonschema only -- no FastAPI, SQLAlchemy, or CrewAI.

**Module structure:**

| Module | Commands |
|--------|----------|
| `__main__.py` | apply, validate, get, list, delete, kickoff, train, test-crew, status, pull, health |
| `auth_cmds.py` | login, logout, whoami, register |
| `exec.py` | executions (list), events, cancel |
| `export_cmd.py` | export (YAML dump) |
| `rbac.py` | role, rolebinding management |
| `users.py` | user (list, invite), group (list, create, delete) |

**Auth resolution order:** `--api-key` flag > `BLACKBEARD_API_KEY` env var > stored JWT in `~/.config/blackbeard/`.

The CLI copies `kinds.py` and the `resources/` validation code from the backend. This avoids a runtime dependency on the backend package while keeping validation logic identical.

---

## SDKs

**Python SDK** (`sdks/python/`): Thin wrapper over httpx. Covers auth (login, register, refresh, whoami), resource CRUD (list, get, create, update, delete, apply, export), and executions (kickoff, train, test, run_flow, cancel, wait, events, spend).

**TypeScript SDK** (`sdks/typescript/`): Thin wrapper over fetch. Mirrors the Python SDK's API coverage.

**React SDK** (`sdks/react/`): React component library (`@blackbeard/react`). Provides `BlackbeardProvider`, `CrewViewer`, `CrewRunner`, and `ExecutionStatus` components for embedding Blackbeard into React applications.

---

## Helm Chart

A Helm chart is available at `deploy/helm/blackbeard/` for Kubernetes deployment. It includes:

- PostgreSQL StatefulSet
- Valkey deployment
- LiteLLM proxy deployment
- API and UI deployments
- Ingress, Secrets, ConfigMaps

Install with:

```bash
helm install blackbeard deploy/helm/blackbeard/ \
  --set auth.apiKey=... \
  --set auth.jwtSecret=...
```

---

## Observability

### OpenTelemetry (Optional)

The backend supports exporting traces to an OpenTelemetry collector. Set the `OTEL_ENDPOINT` environment variable to enable trace export. When not set, tracing is disabled and has no performance impact.

### Structured Logging

All backend log entries are structured with `extra` dicts containing event names and contextual fields (execution IDs, crew names, error types). This makes logs machine-parseable for aggregation in tools like Loki, Elasticsearch, or CloudWatch.

---

## CI Pipeline

GitHub Actions runs 9 jobs on every push:

1. **Backend** -- ruff check + ruff format + mypy + pytest + pip-audit + bandit (security scanning)
2. **CLI** -- ruff lint + offline validation
3. **Python SDK** -- pytest with mock transport
4. **TypeScript SDK** -- tsc type-check
5. **React SDK** -- tsc type-check
6. **Helm** -- helm lint
7. **Frontend** -- prettier + eslint + tsc + vitest + production build
8. **Docker API image** -- build (after backend passes)
9. **Docker UI image** -- build (after frontend passes)

**Security scanning:** Bandit runs as part of the backend CI job, checking for common Python security issues (SQL injection, hardcoded secrets, unsafe deserialization, etc.).

**Property-based testing:** Hypothesis (backend) and fast-check (frontend) are used for property-based testing of schema validation, YAML parsing, and input coercion. These catch edge cases that hand-written tests miss.
