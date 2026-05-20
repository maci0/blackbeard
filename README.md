<p align="center">
  <img src="frontend/public/favicon.svg" alt="Blackbeard" width="64" height="64">
</p>

<h1 align="center">Blackbeard</h1>

<p align="center">
  Self-hosted agent management platform wrapping CrewAI
</p>

<p align="center">
  <a href="https://github.com/blackbeard/blackbeard/actions/workflows/ci.yaml"><img src="https://github.com/blackbeard/blackbeard/actions/workflows/ci.yaml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/node-18%2B-green" alt="Node 18+">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT">
</p>

---

## What is Blackbeard?

Blackbeard gives you a self-hosted platform to build, deploy, and manage AI agent crews powered by [CrewAI](https://crewai.com). Define agents, tasks, tools, and crews as declarative YAML resources -- a Kubernetes-inspired model -- then orchestrate them through a visual graph editor, a REST API, or a full-featured CLI.

**Key differentiators:**

- **Visual graph editor** -- drag-and-drop Studio built on React Flow for designing crews
- **Declarative resource model** -- 12 resource kinds (Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail, Flow, KnowledgeSource, Role, RoleBinding, Automation)
- **Full RBAC** -- JWT authentication with roles, role bindings, and per-resource permissions
- **LiteLLM routing** -- multi-provider model access (Vertex AI, OpenAI, Ollama, etc.) with built-in spend/token/latency tracking
- **Budget enforcement** -- per-execution spending limits via AgentPolicy and LiteLLM virtual keys
- **Multi-tier sandbox isolation** -- run untrusted tool code in WASM, Docker/Podman, gVisor, or Firecracker MicroVM sandboxes
- **CLI parity** -- everything you can do in the UI, you can do from the command line

## Quick Start

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) (or [Podman](https://podman.io/)) with Compose support, and [Git](https://git-scm.com/).

```bash
git clone https://github.com/blackbeard/blackbeard.git
cd blackbeard
./run.sh
```

Open **http://localhost:3000** in your browser. The API is at **http://localhost:8000** (Swagger docs at `/docs` in debug mode).

`run.sh` auto-detects `docker compose` or `podman-compose`, creates a `.env` from `.env.example` if one does not exist, and starts all five services:

| Service  | URL                    | Description                       |
|----------|------------------------|-----------------------------------|
| UI       | http://localhost:3000   | React visual editor + management  |
| API      | http://localhost:8000   | FastAPI REST API                  |
| LiteLLM  | http://localhost:4000   | LLM routing proxy                 |
| Postgres | localhost:5432          | Resource and execution storage    |
| Valkey   | localhost:6379          | Cache (Redis-compatible)          |

Seed the database with example resources (RBAC roles, a research crew, builtin tools, and MCP server tools):

```bash
bash deploy/seed.sh
```

Then run the example crew:

```bash
cd cli && uv sync
blackbeard kickoff research-crew --input topic="AI agents" --wait
```

> See [docs/quickstart.md](docs/quickstart.md) for a full walkthrough.

## Architecture

```
                       ┌──────────────┐
                       │     UI       │
                       │  React Flow  │
                       │  :3000       │
                       └──────┬───────┘
                              │
                       ┌──────▼───────┐        ┌──────────────┐
                       │     API      │───────▶│   CrewAI     │
                       │   FastAPI    │        │   Agents     │
                       │   :8000      │        └──────────────┘
                       └──┬───┬───┬───┘
                          │   │   │
                ┌─────────┘   │   └─────────┐
                │             │             │
         ┌──────▼──────┐ ┌───▼────┐ ┌──────▼───────┐
         │ PostgreSQL   │ │ Valkey │ │   LiteLLM    │
         │   18         │ │   9    │ │   Proxy      │
         │   :5432      │ │  :6379 │ │   :4000      │
         └─────────────┘ └────────┘ └──────┬───────┘
                                           │
                                    ┌──────▼───────┐
                                    │  LLM APIs    │
                                    │  Vertex AI   │
                                    │  OpenAI      │
                                    │  Ollama      │
                                    └──────────────┘
```

**Backend (FastAPI):** All resources are stored as generic rows with a JSONB `spec` column, validated against per-kind JSON schemas. Crew executions run in background threads via `ThreadPoolExecutor`, each with an isolated asyncio event loop. Auth supports both API key (`X-API-Key`) and JWT Bearer tokens.

**Frontend (React + React Flow):** The Studio visual editor lets you drag Agent, Task, and Tool nodes onto a canvas, configure them via a property panel, save as resources, and kick off executions. State is managed with Zustand (undo/redo with 30-snapshot history).

**CLI:** Standalone Python package (`blackbeard-cli`) with no server dependencies. Validates YAML offline, applies resources in dependency order, and manages executions, users, roles, and exports.

> See [docs/architecture.md](docs/architecture.md) for a detailed breakdown.

## Features

- **12 resource kinds** -- Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail, Flow, KnowledgeSource, Role, RoleBinding, Automation
- **Visual graph editor** -- drag-and-drop crew design with React Flow, undo/redo, YAML preview
- **Full RBAC** -- JWT auth (access + refresh tokens), predefined roles (owner, admin, developer, operator, viewer, policy-admin), user/group management
- **CLI with 25+ commands** -- apply, validate, kickoff, train, test-crew, export, pull, status, login, and more
- **Budget enforcement** -- per-execution spending caps via AgentPolicy `max_usd`/`max_tokens` and LiteLLM virtual keys
- **Multi-provider LLM routing** -- Vertex AI, OpenAI, Anthropic, Ollama, and any LiteLLM-supported provider
- **Execution streaming** -- SSE stream and event replay for real-time execution monitoring
- **Tool ecosystem** -- Python tools, builtin CrewAI tools, sandboxed tools (WASM/Docker/gVisor/MicroVM), MCP servers (stdio + HTTP)
- **Marketplace** -- import crews from git repositories (`blackbeard pull`)
- **Train/test** -- CrewAI native training and testing via CLI or API
- **Policy enforcement** -- tool allowlists/denylists, delegation control, sandbox tier requirements
- **Guardrails** -- function-based or LLM-judge output validation on tasks
- **Knowledge sources** -- RAG-accessible content (text, PDF, CSV, JSON) attached to agents
- **Helm chart** -- Kubernetes deployment via `deploy/helm/blackbeard/`
- **SDKs** -- Python, TypeScript, and React client libraries in `sdks/`

## Resource Kinds

| Kind              | Description                                              |
|-------------------|----------------------------------------------------------|
| `Agent`           | AI actor with role, goal, backstory, and optional tools  |
| `Task`            | Unit of work assigned to an agent                        |
| `Crew`            | Orchestrates agents + tasks (sequential or hierarchical) |
| `Tool`            | Callable tool: Python, builtin, WASM, or MCP server      |
| `LLMConnection`   | LLM provider config routed through LiteLLM              |
| `AgentPolicy`     | Tool allowlists, budget limits, sandbox requirements     |
| `Guardrail`       | Task output validation (function or LLM-based)           |
| `Flow`            | Multi-step pipeline orchestrating crews and functions    |
| `KnowledgeSource` | RAG-accessible content for agent knowledge               |
| `Role`            | RBAC role defining resource/verb permissions              |
| `RoleBinding`     | Binds roles to users, groups, agents, or crews           |
| `Automation`      | Cron, webhook, or API-triggered crew/flow executions     |

> See [docs/yaml-reference.md](docs/yaml-reference.md) for the full field-by-field reference.

## CLI

The CLI is a standalone package with no backend dependencies.

```bash
# Install
cd cli && uv sync

# Authenticate
blackbeard login                                     # store JWT credentials
blackbeard whoami                                    # check current identity

# Resources
blackbeard validate -f examples/research-crew/       # offline validation
blackbeard apply -f examples/research-crew/          # create/update resources
blackbeard list Agent                                # list all agents
blackbeard get Crew research-crew                    # inspect a resource
blackbeard delete Agent my-agent                     # remove a resource
blackbeard export --all                              # export all resources as YAML

# Executions
blackbeard kickoff research-crew --input topic="AI"  # run a crew
blackbeard kickoff research-crew --wait              # run and wait for completion
blackbeard train research-crew --iterations 3        # train a crew
blackbeard test-crew research-crew --iterations 3    # test a crew
blackbeard status <execution-id> --watch             # watch execution progress
blackbeard cancel <execution-id>                     # cancel a running execution
blackbeard executions                                # list all executions

# Marketplace
blackbeard pull https://github.com/org/crew-repo.git # import from git

# Users & RBAC
blackbeard user list                                 # list users
blackbeard role list                                 # list roles
blackbeard rolebinding create ...                    # bind roles to subjects
```

All commands support `--json` for scripting and `--server` / `--api-key` / `--namespace` overrides.

## Development

For full dev commands, see [CLAUDE.md](CLAUDE.md).

```bash
# Backend (Python 3.12+, uv required)
cd backend && uv sync --extra dev
uv run pytest tests/ -x                    # tests (in-memory SQLite, no services needed)
uv run ruff check blackbeard/ tests/       # lint
uv run mypy blackbeard/ --ignore-missing-imports  # type check

# Frontend (Bun required)
cd frontend && bun install
bun run dev                                # dev server at :3000
bun run check                              # typecheck + lint + format check
bun run test -- --run                      # vitest

# CLI
cd cli && uv sync
uv run blackbeard --help                   # verify CLI loads
uv run ruff check blackbeard_cli/          # lint
```

### Tech Stack

| Layer        | Technology                                    |
|--------------|-----------------------------------------------|
| Backend      | Python 3.12+, FastAPI, SQLAlchemy, Pydantic v2 |
| Frontend     | React 19, TypeScript, Vite, Tailwind CSS, Radix UI |
| Graph Editor | React Flow (@xyflow/react v12)                |
| Database     | PostgreSQL 18                                 |
| Cache        | Valkey 9                                      |
| LLM Gateway  | LiteLLM Proxy                                |
| WASM Runtime | wasmtime-py                                   |
| Orchestration| CrewAI                                        |

### Project Structure

```
blackbeard/
├── backend/                   # FastAPI backend
│   ├── blackbeard/
│   │   ├── api/               # REST endpoints
│   │   ├── auth/              # JWT auth, RBAC
│   │   ├── engine/            # Execution engine + sandbox runtimes
│   │   ├── litellm/           # LiteLLM config + key management
│   │   ├── models/            # SQLAlchemy + Pydantic models
│   │   └── resources/         # Resource CRUD + validation
│   └── tests/
├── cli/                       # Standalone CLI package (blackbeard-cli)
│   └── blackbeard_cli/
├── frontend/                  # React + TypeScript SPA
│   └── src/
│       ├── components/studio/ # Visual editor (React Flow)
│       ├── pages/             # Studio, Resources, Executions, Models, etc.
│       └── stores/            # Zustand state management
├── sdks/                      # Client libraries
│   ├── python/                # Python SDK
│   ├── typescript/            # TypeScript SDK
│   └── react/                 # React SDK (@blackbeard/react)
├── examples/                  # Example YAML crews
├── deploy/
│   ├── docker/                # Dockerfiles
│   ├── helm/blackbeard/       # Helm chart for Kubernetes
│   ├── litellm/               # LiteLLM proxy config
│   └── seed.sh                # Database seeding script
├── docs/                      # Documentation
├── docker-compose.yaml
└── run.sh                     # One-command startup
```

## Deployment

### Docker Compose (recommended for development)

```bash
cp .env.example .env
# Edit .env: set BLACKBEARD_API_KEY, JWT_SECRET, and database passwords
./run.sh
./run.sh --detach  # background mode
```

### Kubernetes (Helm)

```bash
helm install blackbeard deploy/helm/blackbeard/ \
  --set auth.apiKey=your-secret-key \
  --set auth.jwtSecret=your-jwt-secret
```

### Environment Variables

Key variables (see [.env.example](.env.example) for the full list):

| Variable                        | Description                                      | Default                    |
|---------------------------------|--------------------------------------------------|----------------------------|
| `BLACKBEARD_API_KEY`            | API key for `X-API-Key` header auth              | `change-me-in-production`  |
| `JWT_SECRET`                    | Secret for signing JWT tokens                    | `change-jwt-secret-in-production` |
| `DATABASE_URL`                  | PostgreSQL connection string (asyncpg)           | See `.env.example`         |
| `LITELLM_MASTER_KEY`           | LiteLLM proxy master key                         | `sk-litellm-master-key`    |
| `GOOGLE_APPLICATION_CREDENTIALS`| Path to GCP service account key (for Vertex AI)  | Empty placeholder          |
| `DEBUG`                         | Enable debug mode (Swagger UI, relaxed auth)     | `false`                    |

## API

The API accepts `X-API-Key` header or `Authorization: Bearer <JWT>`. Public endpoints (no auth): health checks, register, login, refresh.

```bash
# Health
curl http://localhost:8000/api/v1/health

# Resources
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/agents
curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/agents/researcher

# Kick off an execution
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"inputs":{"topic":"AI"}}' \
  http://localhost:8000/api/v1/crews/research-crew/kickoff
```

Interactive API documentation is available at `/docs` (Swagger) and `/redoc` when `DEBUG=true`.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests before committing:
   ```bash
   cd backend && uv run pytest tests/ -x && uv run ruff check .
   cd ../frontend && bun run check && bun run test -- --run
   cd ../cli && uv run ruff check blackbeard_cli/
   ```
4. Commit your changes with a descriptive message
5. Push and open a pull request

CI runs lint, type checking, tests, and Docker image builds on every PR. All checks must pass before merging.

### Conventions

- **Python:** ruff lint + format, mypy strict, `from __future__ import annotations` in all modules
- **TypeScript:** ESLint `recommendedTypeChecked` + Prettier, strict mode
- **Resource names:** lowercase alphanumeric + hyphens (`^[a-z0-9][a-z0-9\-]*$`)
- **Ref format:** `ref:<kind-plural>/<name>` (e.g., `ref:agents/researcher`)

## License

MIT
