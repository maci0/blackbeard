# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Blackbeard

Self-hosted agent management platform wrapping CrewAI. Kubernetes-inspired resource model (Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail, Flow, KnowledgeSource, Role, RoleBinding, Automation, Project, ServiceAccount) with a visual graph editor, async execution engine (ThreadPoolExecutor or optional Temporal workflows), RBAC, LiteLLM proxy for model routing (with built-in spend/token/latency tracking), plugin SDK (4 extension types: tool, guardrail, auth_provider, execution_hook), and database-backed resource version snapshots (list/rollback).

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
bun install                      # install deps
bun run dev                      # dev server at :3000 (proxies /api to :8000)
bun run build                    # typecheck + production build
bun run lint                     # eslint (type-aware)
bun run format:check             # prettier check
bun run format                   # prettier fix
bun run check                    # typecheck + lint + format:check (all-in-one)
bun run test -- --run            # vitest (single run)
```

### CLI (from `cli/` — standalone package, no server deps)

```bash
uv sync --extra dev              # install deps (runtime: click, httpx, rich, pyyaml, jsonschema, prompt-toolkit)
uv run blackbeard --help         # all commands
uv run blackbeard validate -f ../examples/research-crew/  # offline validation
uv run blackbeard login          # store JWT credentials
uv run blackbeard shell          # interactive TUI REPL
uv run ruff check blackbeard_cli/  # lint (needs --extra dev)
```

### Full Stack

```bash
./run.sh                         # build + start all services (auto-detects docker compose / podman-compose)
./run.sh --detach                # background mode
bash deploy/seed.sh              # seed DB with RBAC roles, example crew, and tools (requires running stack)
```

## Architecture

### Backend (FastAPI + CrewAI)

**Resource system**: All entities (Agent, Task, Crew, etc.) are stored as generic `Resource` rows with a JSONB `spec` column, validated against per-kind JSON schemas (`resources/spec_schemas.py`). Resources reference each other with strings like `ref:agents/researcher`, tracked in a `ResourceRef` table. `kinds.py` is the single source of truth for the kind registry and URL plural mapping.

**Execution flow**: `POST /api/v1/crews/{crew_name}/kickoff` (also `/train`, `/test`, `/flows/{name}/run`) → creates `Execution` record with `initiated_by` (user) + `principal_chain` (User → Crew → Agent/ServiceAccount) → submits to Temporal workflow (if configured) or `ThreadPoolExecutor` → background thread/workflow derives budget limits from AgentPolicy → creates per-execution LiteLLM virtual key with budget caps → builds CrewAI objects via `ResourceLoader` (resolves refs, builds LLM/Agent/Task/Crew with virtual key) → calls `crew.kickoff(inputs=...)` (or `.train()`/`.test()`, or sequential flow step execution) → stores result + token usage → deletes virtual key → delivers webhook events. Each crew run gets its own thread with an isolated asyncio event loop (ThreadPoolExecutor path) or a Temporal activity (Temporal path).

**Budget enforcement**: AgentPolicy `max_usd`/`max_tokens` → LiteLLM virtual key with budget limits → LiteLLM Proxy enforces at call time. Key created inside the background thread before crew.kickoff(), deleted after (success or failure). Most restrictive policy across all agents wins.

**CrewAI delegation**: Blackbeard delegates to CrewAI native features where possible — memory, knowledge/RAG, guardrails (function-based + LLM-prompt), structured outputs (`output_json`/`output_pydantic`), delegation, tool discovery. Only extends where needed (event persistence, sandbox tiers, policy enforcement).

**Auth & RBAC**: Built-in email/password with JWT (access 15min + refresh 7d). User/Group models in `models/user.py`. Role and RoleBinding as resource kinds. Predefined roles seeded by `deploy/seed.sh`. Auth middleware accepts both `X-API-Key` and `Authorization: Bearer <jwt>`. Agent execution tracks principal chain: User → Crew → Agent (ServiceAccount via `spec.serviceAccount`, defaults to `sa-<name>`).

**Middleware stack** (outermost → innermost): security headers → API key auth (hmac.compare_digest or JWT Bearer) + request ID → body size limiter (10MB) → CORS (`CORSMiddleware` via `add_middleware`, registered first in `main.py` so it ends up innermost). The three `app.middleware("http")` middlewares are registered LIFO in `main.py`. Note: responses short-circuited by auth or the body limiter never reach `CORSMiddleware`, so they carry no CORS headers. When `OIDC_ISSUER` is set, `SessionMiddleware` is added last and becomes the true outermost layer. Auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`), OIDC endpoints (`/auth/oidc/login`, `/auth/oidc/callback`, `/config/public`), health checks, `/api/v1/metrics`, `/api/v1/asyncapi.json`, `/.well-known/agent-card.json`, docs paths (`/docs`, `/redoc`, `/openapi.json` — DEBUG only), and automation webhook paths (`/automations/{name}/webhook`) are public (no auth required — automation webhooks use their own HMAC validation inside the route handler).

**CLI** (`cli/` -- separate package `blackbeard-cli`): Standalone package with no server deps (click, httpx, rich, pyyaml, jsonschema, prompt-toolkit only). 31 commands (21 top-level plus 4 groups with 10 subcommands) across 6 modules. Includes `blackbeard shell` for an interactive TUI REPL. Copies `kinds.py` and `resources/` (schemas, validation, ref parsing) from backend to avoid coupling. Auth resolution: `--api-key` > `BLACKBEARD_API_KEY` env > stored JWT in `~/.config/blackbeard/`.

**Dynamic LiteLLM sync**: When `LLMConnection` resources are created/updated/deleted, the API pushes changes to LiteLLM via `POST /model/new`, `/model/update`, and `/model/delete` — no container restart needed.

**RBAC enforcement**: API endpoints use a `require_permission()` FastAPI dependency that checks the authenticated user's roles and role bindings before allowing access. Permissions are checked as `(resource_kind, verb)` pairs.

**API key management**: `POST /api/v1/auth/api-key` generates a personal API key; `DELETE /api/v1/auth/api-key` revokes it.

**Bulk resource export**: `GET /api/v1/resources/export` returns all resources as multi-document YAML (each resource separated by `---`).

**HITL (Human-in-the-Loop)**: Tasks with `human_input: true` pause execution. Frontend polls for `hitl_request` events and submits responses via `POST /executions/{id}/respond`. Response recorded as `hitl_response` event.

**Chat streaming**: `POST /api/v1/chat/stream` provides real SSE streaming endpoint. Backend proxies through LiteLLM with `stream=True`, forwarding SSE chunks to the client.

**Model fallback chains**: Configured per `LLMConnection` via `spec.fallbacks` (array of model strings). LiteLLM automatically retries with fallback models on provider errors.

**Cost alert thresholds**: AgentPolicy supports `budget.alerts.warn_at_usd` and `budget.alerts.warn_at_tokens` fields. Triggers `cost_alert` event when spend crosses warning thresholds during execution, before the hard budget limit.

**A2A Protocol**: `GET /.well-known/agent-card.json` auto-generates agent cards from Crew resources with `spec.a2a.enabled: true`. Public endpoint (no auth). Cards include skills from task refs, auth schemes, capabilities. Cached 60s in-memory.

**Resource versioning**: `resource_versions` table stores spec/labels snapshots on every create/update. Endpoints: `GET /{kind}/{name}/versions` (list), `GET /{kind}/{name}/versions/{version}` (detail), `POST /{kind}/{name}/rollback` (restore from snapshot).

**Plugin SDK**: Extension system with 4 plugin types: `tool` (custom tool implementations), `guardrail` (custom validation logic), `auth_provider` (external auth integration), and `execution_hook` (pre/post execution callbacks). Plugins are registered via entry points or the plugin API.

**Temporal workflow engine**: Optional durable workflow execution via Temporal. When `TEMPORAL_HOST` is configured, crew executions run as Temporal workflows instead of ThreadPoolExecutor threads. Falls back to ThreadPoolExecutor when Temporal is not available. Configuration in `backend/blackbeard/engine/temporal.py`.

**Project-level guardrails**: Project resources support `spec.guardrails` array. At execution time, project guardrails are prepended to task-level guardrails.

**OpenTelemetry**: Optional trace export via `OTEL_ENDPOINT` env var. When unset, tracing is disabled with no overhead.

**External services**: PostgreSQL (resources + executions + users), Valkey (real-time collaboration pub/sub for multi-replica WebSocket fan-out + health checks), LiteLLM proxy (model routing to Vertex AI / OpenAI, with per-execution virtual keys for budget enforcement + spend tracking).

### Frontend (React + React Flow)

**Studio**: Visual graph editor (`@xyflow/react`) where users drag Agent/Task/Tool/FlowStep/Condition/Router/Parallel/IF-ELSE/Switch/Merge/Filter/Gate nodes and sticky notes (4 colors) onto a canvas, configure them via PropertyPanel, save as resources, and run/train/test crews. `studioStore` (Zustand) manages canvas state with undo/redo (30-snapshot history). Crew group nodes wrap agents+tasks in a visual bounding box. ELK.js auto-layout arranges nodes left-to-right. Bidirectional YAML editor syncs with canvas. Per-node testing ("Test Agent"/"Test Task" in PropertyPanel). Expression editor with syntax validation and variable autocomplete for Condition/Router nodes. Execution data overlay (green/red borders, output preview). Gantt timeline and grouped/collapsible execution logs. Crew Settings dialog (error workflow). Canvas export (PNG, SVG, JSON).

**Resource CRUD**: `resourceStore` handles all resource kinds through the generic `/api/v1/{kind_plural}` endpoints. Updates use optimistic locking via `version` field.

**Dashboard**: Default landing page (`/`) with execution metrics, resource counts, and recent activity.

**Chat**: `/chat` playground for interactive LLM conversations via configured LLMConnections.

**Audit Logs**: `/audit-logs` page for viewing all mutation history (resource creates/updates/deletes, execution events, user management).

**Webhooks**: `/webhooks` page for managing webhook subscriptions — register, view, and delete webhook endpoints.

**Command palette**: `Cmd+K` / `Ctrl+K` opens a fuzzy-search command palette for quick navigation to any page, resource, or action.

**Notifications**: Toast notification system for async feedback (execution started, resource saved, errors).

**YAML import**: File-based YAML import in the UI for bulk resource creation.

**Health indicator**: Sidebar displays a live health status indicator for the backend API connection.

**Marketplace**: `/marketplace` page for importing resources from git repos. Backend clones repos, validates YAML, upserts resources. 8 built-in example crews plus a shared tools collection available. Enhanced template gallery with search, category chips, preview dialog, and resource summaries.

**Knowledge Sources**: `/knowledge` page with card grid showing knowledge sources and source type badges.

**Credentials Manager**: `/credentials` page for centralized secret management.

**Guardrail Playground**: `/guardrails/playground` for testing guardrails with sample input before deploying to tasks.

**Execution Comparison**: `/executions/compare?a=&b=` for side-by-side metrics diff of two executions.

**Streaming chat**: `POST /api/v1/chat/stream` provides real SSE streaming. Chat page renders tokens as they arrive with a stop button for in-flight cancellation.

**Presence indicators**: `PresenceAvatars` component shows colored avatar circles on ResourceDetail and Studio pages for users viewing the same resource.

**Loading skeletons**: Dashboard, Chat, and KnowledgeSources pages display pulse-animated placeholders while data loads.

**Keyboard shortcuts**: `Cmd+Shift+S` (save), `Cmd+Shift+E` (executions), `Cmd+Shift+N` (new resource), `Cmd+.` (settings), `?` (shortcuts dialog).

**Bulk operations**: Multi-select with bulk delete in table and card views. Clipboard YAML import (paste multi-doc YAML).

**Resource version history**: Audit log timeline tab on ResourceDetail pages showing all mutations for that resource.

**User preferences**: Settings page includes default project, notification preferences, and sound settings.

**Rate limit badges**: Models page shows RPM/TPM badges on model cards.

**Run history**: Crew ResourceDetail pages include a run history tab showing past executions with re-run button.

**API client**: `src/api/client.ts` — typed fetch wrapper, proxied through Vite dev server (`:3000/api → :8000`). Auto-generated OpenAPI types in `src/api/schema.d.ts` (`bun run generate:api`).

### Infrastructure

**docker-compose.yaml**: 5 services — api, ui, postgres (18), valkey (9), litellm. All containers use `no-new-privileges`, `cap_drop: ALL`. Postgres adds back CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID; Valkey adds back SETGID, SETUID.

DB schema is managed by `backend/blackbeard/db_setup.py` (invoked from `backend/entrypoint.sh` under `MIGRATION_TIMEOUT`, default 120s): first creates PostgreSQL enum types, runs `Base.metadata.create_all()` (for initial table creation), and applies CHECK constraints, then runs `alembic upgrade head` if configured. `create_all` only creates new tables — it cannot alter existing ones — so Alembic handles schema evolution. If `alembic.ini` or `alembic/versions` doesn't exist, migrations are skipped.

**Helm chart**: `deploy/helm/blackbeard/` -- full Kubernetes deployment. PG StatefulSet, Valkey, LiteLLM, API, UI, Ingress, Secrets, HPA autoscaling. Install: `helm install blackbeard deploy/helm/blackbeard/ --set auth.apiKey=... --set auth.jwtSecret=...`

**Multi-replica compose**: Docker Compose supports multi-replica API deployment with an nginx load balancer for horizontal scaling.

**Monitoring stack**: Prometheus, Grafana dashboards, and alerting rules in `deploy/monitoring/`. Scrapes API and LiteLLM metrics.

**SDKs**: Python (`sdks/python/`), TypeScript (`sdks/typescript/`), and React (`sdks/react/`) — thin wrappers over httpx/fetch. Cover auth, resources, executions, train/test/flow. React SDK provides `BlackbeardProvider`, `CrewViewer`, `CrewRunner`, and `ExecutionStatus` components.

**CI**: GitHub Actions — 10 jobs: backend (ruff check + ruff format + mypy + pytest + pip-audit + bandit security scan) → CLI (lint + validate) → Python SDK (pytest) → TypeScript SDK (tsc) → React SDK (tsc) → Helm lint → frontend (prettier + eslint + tsc + vitest + build) → Docker image builds (docker-api after backend, docker-ui after frontend, cached) → ci-gate (all-green check). Includes Hypothesis property-based testing (backend) and fast-check fuzzing (frontend) for schema validation edge cases.

**Webhooks**: Register webhook URLs via `POST /api/v1/webhooks`. Execution events delivered with HMAC-SHA256 signature. Fire-and-forget delivery.

**Audit logging**: All mutations logged to `audit_logs` table. Query via `GET /api/v1/audit-logs`.

## Conventions

- **Python**: ruff lint + format, mypy strict, `from __future__ import annotations` in all modules, type annotations on all functions. Rules: `E F I N W UP B SIM ANN RUF PT C4 PIE T20 TCH`. Tests exempt from `ANN E402 PT011 B017 TC002 E501 SIM117`; API and auth files exempt from `TCH` and `B008` (FastAPI needs types at runtime); API and executor files exempt from `PT` (functions named `test_*` are not pytest tests).
- **TypeScript**: ESLint `recommendedTypeChecked` + Prettier. Strict mode, `noUncheckedIndexedAccess`. Use `void` for fire-and-forget promises in React (e.g., `onClick={() => void handleClick()}`).
- **Imports**: Use `@/` path alias in frontend. Backend uses relative imports within packages.
- **Resource names**: lowercase alphanumeric + hyphens (`^[a-z0-9][a-z0-9\-]*$`).
- **Ref format**: `ref:<kind-plural>/<name>` (e.g., `ref:agents/researcher`).
- **No backward compat**: This is a fresh MVP. Use current API versions directly — no `hasattr`/`getattr` guards, no `try/except ImportError` fallbacks.
- **Tests**: Backend tests use in-memory SQLite with PostgreSQL types monkey-patched in `conftest.py`. No external services needed. Frontend uses vitest + @testing-library/react with jsdom. E2E tests in `frontend/e2e/` using Playwright (need running stack). Python SDK has its own pytest suite with mock transport.
