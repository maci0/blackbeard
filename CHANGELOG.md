# Changelog

All notable changes to Blackbeard are documented here. Grouped by release, newest first.

## Unreleased

### Features
- **Sandbox enforcement** at tool call time: select tier from tool spec + policy floor, run `command` tools and python tools in docker/podman/gvisor/microvm, load `type: wasm` via WasmSandbox.
- **Sandbox hardening**: per-tool `image` override, network deny-by-default unless `capabilities: [network]`, command-only tools, docs (`docs/tool-sandboxes.md`), example `examples/tools/echo-sandboxed.yaml`, optional docker smoke test.

### Removed
- **Git-backed resource store** (auto-commit, log/diff/blame/show, remotes). Database resource versioning (list/rollback) remains.
- **gRPC API** (proto, server on port 50051, grpcio dependency). REST + SSE remain the public API surface.
- **Observability page** at `/observability` (Dashboard covers high-level metrics; OTEL/Prometheus/Grafana stack unchanged).
- Coverage-theater test suites and non-CUJ e2e duplicates of CUJ specs.
- Unused frontend deps: `@radix-ui/react-context-menu`, `scroll-area`, `select`, `recharts`.

## 0.2.0

### Features
- **Plugin SDK** with 4 extension types: tool, guardrail, auth_provider, execution_hook
- **Interactive TUI shell** (`blackbeard shell`) for exploratory REPL-based resource management
- **Temporal workflow engine** integration for durable execution (optional, falls back to ThreadPoolExecutor)
- **Git-backed resource versioning** with auto-commit on every mutation, log/diff/blame/show API
- **Observability dashboard** page at `/observability` with traces, metrics, and system health
- **Nested project hierarchy** with parent refs and `inherit_policies` for cascading policy inheritance
- **Tool versioning** with `tool_version` semver field and `deprecated`/`deprecated_message` support
- **Composite guardrail chains** with AND/OR operators for combining multiple guardrails
- **Hallucination detection** guardrail type for factual accuracy validation
- **Crew-level guardrails** applied to all tasks in a crew
- **Canvas PNG/SVG export** from the Studio visual editor
- **AsyncAPI 3.0 spec** served at `/api/v1/asyncapi.json`
- **HPA autoscaling** in Helm chart for Kubernetes deployments
- **Multi-replica Docker Compose** with nginx load balancer
- **Monitoring stack** with Prometheus, Grafana dashboards, and alerting rules
- **`ALLOW_INTERNAL_URLS`** env var for local dev marketplace imports
- **22 Critical User Journeys** documented with 230 Playwright E2E test specs
- **Event storming** map covering 11 bounded contexts
- **Studio guide** and **features reference** documentation
- **Agency Agents import** with GitHub API caching, division browsing, one-click import
- **Tools Library** with bundled YAML catalog and install-from-catalog flow
- **Credentials manager** for centralized secret storage
- **A2A Protocol** at `/.well-known/agent-card.json` with 60s cache
- **Resource versioning** with snapshot on every mutation, list/view/rollback
- **PII compliance presets** (HIPAA, GDPR, PCI-DSS, CCPA) with Presidio integration
- **Logic block nodes** in Studio (IF/ELSE, Switch, Merge, Filter, Gate, Loop)
- **Crew-as-component** node type (subcircuit pattern for reusable crews)
- **Drill-in navigation** for crew components with breadcrumb trail
- **Projects page** and **Service Accounts page** in admin section
- **Guardrail playground** for testing guardrails before deployment
- **Execution comparison** side-by-side view
- **Chat playground** with real SSE streaming and stop button
- **gRPC API** on port 50051 with auth interceptor
- **Python, TypeScript, React SDKs** in `sdks/`
- **Marketplace** with 8 built-in example crews and git import
- **Command palette** (Cmd+K) with fuzzy search
- **Keyboard shortcuts** (Cmd+Shift+S/E/N, Cmd+., ?)
- **Onboarding wizard** with 5-step welcome and guided tour
- **btn-press** feedback on all primary action buttons
- **Node selection glow** effect in Studio canvas
- **Toast exit animations** and **sidebar section transitions**
- **Breadcrumbs** on detail pages
- **Loading skeletons** on Dashboard, Chat, Knowledge, Models pages
- **Presence indicators** for live collaboration
- **Bulk operations** (multi-select delete, clipboard YAML import)
- **Rate limit badges** on model cards
- **Run history** tab on crew detail pages

### Fixes
- Fixed all 36 ESLint warnings (unnecessary conditions, unstable deps, dead branches)
- Fixed SDK kind maps (Namespace to Project, added ServiceAccount)
- Fixed SDK rollback field (`to_version` to `version`)
- Fixed Automations page spec structure (flat to nested)
- Fixed logger.info `name` collision with LogRecord in credentials API
- Fixed agency import cache not clearing between tests
- Fixed gRPC proto fields renamed from namespace to project
- Bumped uv to 0.11.15 in Docker image (GHSA-4gg8-gxpx-9rph)
- Renamed `copilot` to `assistant` across entire codebase
- Renamed `namespace` to `project` across entire codebase (API, DB, UI, CLI, SDKs, gRPC, Helm)

### Testing
- 2975 backend tests (pytest + hypothesis property-based testing)
- 343 frontend unit tests (vitest + fast-check fuzzing)
- 230 CUJ E2E test specs (Playwright)
- 47 additional E2E test specs
- Function-level test coverage for every backend function
- Fuzz testing for every API surface

### Documentation
- `docs/quickstart.md` (12-step walkthrough)
- `docs/studio-guide.md` (17 node types, collaboration, keyboard shortcuts)
- `docs/features.md` (agency import, tools library, credentials, A2A, versioning, SDKs, gRPC)
- `docs/architecture.md` (system overview, execution flow, middleware stack)
- `docs/yaml-reference.md` (all 14 resource kinds with field tables)
- `docs/critical-user-journeys.md` (22 CUJs)
- `docs/event-storming.md` (11 bounded contexts)
- `docs/firecracker-setup.md` (MicroVM sandbox)
- `outputs/prds/` (14 PRDs, all up to date)

### Infrastructure
- Docker Compose with 5 services (API, UI, PostgreSQL 18, Valkey 9, LiteLLM)
- Helm chart for Kubernetes deployment
- GitHub Actions CI with 9 jobs
- Multi-stage Docker builds with cache mounts
- Non-root containers with capability drops
- `.dockerignore` excluding tests, docs, env files
- OpenTelemetry trace export (optional via OTEL_ENDPOINT)

## 0.1.0 (Initial)

- Core platform: FastAPI backend, React frontend, CLI
- 14 resource kinds with JSONB spec storage and JSON schema validation
- Visual graph editor (React Flow) with undo/redo, auto-layout, YAML sync
- JWT authentication with RBAC enforcement
- CrewAI execution engine with budget enforcement via LiteLLM virtual keys
- LiteLLM proxy integration with dynamic model sync
- WebSocket collaboration with Valkey pub/sub
- Webhook delivery with HMAC-SHA256 signing
- Audit logging for all mutations
