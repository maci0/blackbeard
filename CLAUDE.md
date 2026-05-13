# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Blackbeard

Self-hosted agent management platform wrapping CrewAI. Kubernetes-inspired resource model (Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail) with a visual graph editor, async execution engine, LiteLLM proxy for model routing, and Langfuse for tracing.

## Commands

### Backend (from `backend/`)

```bash
uv sync --extra dev              # install deps
uv run pytest tests/ -x          # run all tests (needs no external services — uses in-memory SQLite)
uv run pytest tests/test_loader.py::test_build_crew -x  # single test
uv run ruff check blackbeard/ tests/   # lint
uv run ruff format blackbeard/ tests/  # format
uv run mypy blackbeard/ --ignore-missing-imports  # type check
```

### Frontend (from `frontend/`)

```bash
npm ci                           # install deps
npm run dev                      # dev server at :3000 (proxies /api to :8000)
npm run build                    # typecheck + production build
npm run lint                     # eslint (type-aware)
npm run format:check             # prettier check
npm run format                   # prettier fix
npm run check                    # typecheck + lint + format:check (all-in-one)
npm run test -- --run            # vitest (single run)
```

### Full Stack

```bash
./run.sh                         # build + start all services (auto-detects docker compose / podman-compose)
./run.sh --detach                # background mode
```

## Architecture

### Backend (FastAPI + CrewAI)

**Resource system**: All entities (Agent, Task, Crew, etc.) are stored as generic `Resource` rows with a JSONB `spec` column, validated against per-kind JSON schemas (`resources/spec_schemas.py`). Resources reference each other via `ref:agents/my-agent` strings, tracked in a `ResourceRef` table. `kinds.py` is the single source of truth for the kind registry and URL plural mapping.

**Execution flow**: `POST /api/v1/crews/{name}/kickoff` → creates `Execution` record → submits to `ThreadPoolExecutor` → background thread builds CrewAI objects via `ResourceLoader` (resolves refs, builds LLM/Agent/Task/Crew) → calls `crew.kickoff(inputs=...)` → stores result + token usage. Each crew run gets its own thread with an isolated asyncio event loop to avoid blocking the FastAPI async loop.

**Middleware stack** (LIFO): security headers → API key auth (hmac.compare_digest) + request ID → body size limiter (10MB).

**External services**: PostgreSQL (resources + executions), Valkey (cache), LiteLLM proxy (model routing to Vertex AI / OpenAI), Langfuse (tracing via CrewAI event listener → `start_observation()` API).

### Frontend (React + React Flow)

**Studio**: Visual graph editor (`@xyflow/react`) where users drag Agent/Task/Tool nodes onto a canvas, configure them via PropertyPanel, save as resources, and run crews. `studioStore` (Zustand) manages canvas state with undo/redo (30-snapshot history).

**Resource CRUD**: `resourceStore` handles all resource kinds through the generic `/api/v1/{kind_plural}` endpoints. Updates use optimistic locking via `version` field.

**API client**: `src/api/client.ts` — typed fetch wrapper, proxied through Vite dev server (`:3000/api → :8000`).

### Infrastructure

**docker-compose.yaml**: 10 services — api, ui, postgres (18), valkey (9), litellm, langfuse-web, langfuse-worker, clickhouse, minio, redis. API and UI containers run read-only with `cap_drop: ALL` and `no-new-privileges`.

**CI**: GitHub Actions — backend (ruff + mypy + pytest with Postgres service) → frontend (prettier + eslint + tsc + vitest + build) → Docker image builds (parallel, cached).

## Conventions

- **Python**: ruff lint + format, mypy strict, `from __future__ import annotations` in all modules, type annotations on all functions. Rules: `E F I N W UP B SIM ANN RUF PT C4 PIE T20 TCH`. Tests exempt from `ANN`; API files exempt from `TCH` (FastAPI needs types at runtime) and `B008` (Depends in defaults).
- **TypeScript**: ESLint `recommendedTypeChecked` + Prettier. Strict mode, `noUncheckedIndexedAccess`. Use `void` for fire-and-forget promises in React (e.g., `onClick={() => void handleClick()}`).
- **Imports**: Use `@/` path alias in frontend. Backend uses relative imports within packages.
- **Resource names**: lowercase alphanumeric + hyphens (`^[a-z0-9][a-z0-9\-]*$`).
- **Ref format**: `ref:<kind-plural>/<name>` (e.g., `ref:agents/researcher`).
- **No backward compat**: This is a fresh MVP. Use current API versions directly — no `hasattr`/`getattr` guards, no `try/except ImportError` fallbacks.
- **Tests**: Backend tests use in-memory SQLite with PostgreSQL types monkey-patched in `conftest.py`. No external services needed. `test_health.py` is the exception — it needs a live Postgres.
