# Blackbeard

Open, self-hosted **Agent Management Platform** wrapping [CrewAI](https://crewai.com) with enterprise features: visual crew editor, LLM routing via LiteLLM, execution tracing via Langfuse, WASM tool sandboxing, and agent policies.

## Quickstart

**Prerequisites:** [Podman](https://podman.io/) (or Docker), [podman-compose](https://github.com/containers/podman-compose), GCP service account with Vertex AI access.

```bash
# 1. Clone and enter the project
git clone <repo-url> blackbeard && cd blackbeard

# 2. Configure credentials
cp .env.example .env
# Edit .env — set GOOGLE_APPLICATION_CREDENTIALS to your GCP service account key path

# 3. Start everything
./run.sh
# Or: podman-compose up -d

# 4. Open the UI
open http://localhost:3000
```

**Services started:**

| Service | URL | Description |
|---------|-----|-------------|
| UI | http://localhost:3000 | React visual editor + management |
| API | http://localhost:8000 | FastAPI REST API |
| API Docs (Swagger) | http://localhost:8000/docs | Interactive API documentation (no API key required) |
| LiteLLM | http://localhost:4000 | LLM proxy (Vertex AI) |
| Langfuse | http://localhost:3001 | Execution traces |

## Apply Example Crew

```bash
# Install CLI
cd backend && pip install -e . && cd ..

# Validate and apply the research crew
blackbeard validate -f examples/research-crew/
blackbeard apply -f examples/research-crew/
blackbeard apply -f examples/research-crew/ --dry-run  # validate without applying

# Kick off an execution
blackbeard kickoff research-crew --input topic="AI agents"

# Check status
blackbeard status <execution-id>
blackbeard status <execution-id> --watch               # poll until complete
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   React UI  │────▶│  FastAPI API  │────▶│  PostgreSQL   │
│  (Studio)   │     │  (Blackbeard) │     │              │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────┴───────┐
                    │              │
              ┌─────▼─────┐ ┌─────▼─────┐
              │  LiteLLM  │ │  Langfuse  │
              │  (Proxy)  │ │  (Traces)  │
              └─────┬─────┘ └───────────┘
                    │
              ┌─────▼─────┐
              │ Vertex AI  │
              │ Claude/    │
              │ Gemini     │
              └───────────┘
```

## Project Structure

```
blackbeard/
├── backend/                    # Python FastAPI backend
│   ├── blackbeard/
│   │   ├── api/                # REST endpoints
│   │   ├── engine/             # Execution engine + WASM sandbox
│   │   ├── langfuse/           # Langfuse tracing
│   │   ├── litellm/            # LiteLLM config + key management
│   │   ├── models/             # SQLAlchemy + Pydantic models
│   │   ├── resources/          # Resource CRUD + validation
│   │   └── cli/                # CLI commands
│   └── tests/                  # backend test suite
├── frontend/                   # React + TypeScript SPA
│   └── src/
│       ├── components/studio/  # Visual editor (React Flow)
│       ├── pages/              # Resources, Executions, Models, Tools
│       └── stores/             # Zustand state management
├── examples/                   # Example YAML crews
├── deploy/                     # Dockerfiles + LiteLLM config
└── docker-compose.yaml         # 10 services
```

## Resource Kinds

| Kind | Description |
|------|-------------|
| `Agent` | CrewAI agent with role, goal, backstory, LLM |
| `Task` | Work unit assigned to an agent |
| `Crew` | Orchestrates agents + tasks (sequential/hierarchical) |
| `Tool` | Python or WASM tool for agents |
| `LLMConnection` | LLM provider config (Vertex AI, OpenAI, etc.) |
| `AgentPolicy` | Tool allowlists, budget limits, sandbox tiers |
| `Guardrail` | Task-level safety checks (function or LLM-based) |

## API

All endpoints require `X-API-Key` header (set via `BLACKBEARD_API_KEY` env var).

All API responses include an `X-Request-Id` header for tracing. Pass your own via the request header, or one is auto-generated.

```bash
# Resources CRUD
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/agents
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/agents/researcher

# Update a resource (optimistic locking via version field)
curl -X PUT http://localhost:8000/api/v1/agents/researcher \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"spec": {...}, "version": 1}'

# Delete a resource
curl -X DELETE http://localhost:8000/api/v1/agents/researcher \
  -H "X-API-Key: $KEY"

# Execution
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"inputs":{"topic":"AI"}}' \
  http://localhost:8000/api/v1/crews/research-crew/kickoff

> Returns `202 Accepted` with execution details (`status: queued`).

curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/executions/<id>

# Cancel a running execution
curl -X POST http://localhost:8000/api/v1/executions/{id}/cancel \
  -H "X-API-Key: $KEY"

# SSE + health
GET  /api/v1/executions/{id}/stream  # SSE stream of execution status events
GET  /api/v1/health                  # liveness check
GET  /api/v1/health/ready            # readiness check (probes database)
```

> **Note:** `POST` creates a new resource (201) or updates an existing one with the same name/namespace (200). Use the response status code to distinguish create from update.

> If the `version` doesn't match the server's current version, the API returns `409 Conflict`. Fetch the resource first to get the current version.

**Query Parameters** (on list endpoints):
- `namespace` — Filter by namespace (default: all for resources, `default` for executions)
- `limit` / `offset` — Pagination (default: 50-100)
- `status` — Filter executions by status (`queued`, `running`, `completed`, `failed`, `cancelled`)
- `crew_name` — Filter executions by crew name

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install uv && uv pip install -e ".[dev]"
pytest                          # run all tests
ruff check .                    # lint
mypy blackbeard/ --ignore-missing-imports  # type check

# Frontend
cd frontend
npm install
npm run dev                     # dev server on :3000
npm run typecheck               # TypeScript check
npm run build                   # production build
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic v2 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Graph Editor | React Flow (xyflow v12) |
| Database | PostgreSQL 17 |
| Cache | Valkey 8 |
| LLM Gateway | LiteLLM Proxy |
| Observability | Langfuse (self-hosted) |
| WASM Runtime | wasmtime-py |
| Orchestration | CrewAI |

## Known Limitations

- **Tool refs on agents** are stored but not yet loaded at execution time. Tools must be registered directly via CrewAI's tool system.
- **Inline crew resources** (`spec.inline`) are validated as an opaque object — individual inline agents/tasks are not schema-validated.

## License

MIT
