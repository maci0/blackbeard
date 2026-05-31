# Changelog

All notable changes to Blackbeard are documented here. Grouped by release, newest first.

## Unreleased

### Features
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
