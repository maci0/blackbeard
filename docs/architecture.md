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
     │                 │ │   (cache)   │  │     :4000         │
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
4. **Valkey 9** -- Redis-compatible cache used for session data and rate limiting.
5. **LiteLLM Proxy** -- Routes LLM calls to configured providers (Vertex AI, OpenAI, Ollama, etc.) and tracks spend, tokens, and latency per virtual key.

---

## Backend Architecture

### Resource System

All entities in Blackbeard are **resources**. Every resource shares a common envelope:

```yaml
apiVersion: blackbeard/v1
kind: Agent          # one of 11 kinds
metadata:
  name: researcher
  namespace: default
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

**Budget enforcement chain:**

1. `AgentPolicy` resource defines `max_usd` and `max_tokens`
2. API creates a LiteLLM virtual key with those limits before execution starts
3. LiteLLM Proxy enforces the limits at call time, rejecting requests that exceed the budget
4. Virtual key is deleted after execution completes (success or failure)

### Authentication and RBAC

Blackbeard supports two authentication methods:

- **API key** -- `X-API-Key` header, validated with `hmac.compare_digest` against `BLACKBEARD_API_KEY`
- **JWT Bearer** -- `Authorization: Bearer <token>`, with 15-minute access tokens and 7-day refresh tokens

**Public endpoints** (no auth required): health checks (`/api/v1/health`, `/api/v1/health/ready`), auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`), and API docs (`/docs`, `/redoc` in debug mode).

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

LiteLLM's own data (spend tracking, virtual keys) is stored in a separate `litellm` database within the same PostgreSQL instance.

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
/                     → Studio (default)
/studio               → Visual crew editor
/resources            → Generic resource list (all kinds)
/resources/:kind/:name→ Resource detail view
/executions           → Execution list
/executions/:id       → Execution detail with task breakdown
/models               → LLM model management + connectivity test
/tools                → Tool management
/roles                → RBAC role management
/users                → User management
/login                → Login form
/register             → Registration form
/marketplace          → Import crews from git
```

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
| API        | ALL      | (none)                                         | No        | 256       |
| UI         | ALL      | (none)                                         | No        | 64        |
| PostgreSQL | ALL      | CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID    | No        | 128       |
| Valkey     | ALL      | SETGID, SETUID                                 | Yes       | 64        |
| LiteLLM    | ALL      | (none)                                         | No        | 128       |

### API Security

- Request body size limited to 10MB
- Security headers on all responses (CSP, X-Content-Type-Options, X-Frame-Options)
- API keys compared with `hmac.compare_digest` (constant-time) to prevent timing attacks
- JWT tokens: 15-minute access, 7-day refresh
- All ports bound to `127.0.0.1` only (not exposed to external networks)
- `X-Request-Id` on every response for tracing

### WASM Sandbox

Tools with `sandbox: wasm` run in a WebAssembly runtime (`wasmtime-py`) with restricted capabilities. WASI grants are explicitly enumerated (e.g., `http_fetch`, `env`). The `env` capability exposes only a fixed set of safe variables (`LANG`, `LC_ALL`, `TZ`, `TERM`).
