# Blackbeard PRD Suite Review

## Executive Summary

This is an impressively thorough PRD suite for a product of this scope. The documentation demonstrates deep technical knowledge of both CrewAI and the surrounding infrastructure ecosystem. The "build the orchestration layer, delegate infrastructure to battle-tested OSS" philosophy is sound and well-articulated. The resource model is Kubernetes-inspired in a way that will feel natural to platform engineers, and the explicit delineation of what CrewAI provides versus what Blackbeard adds prevents the team from accidentally reimplementing existing functionality.

**Top 3 Strengths:**

1. **Clear separation of concerns.** The Overview (PRD 00) and Integration Map (PRD 00-integrations) do an excellent job defining the boundary between "inherit from CrewAI," "delegate to third-party OSS," and "custom Blackbeard code." This is the single most important architectural decision and it is well-defended throughout.

2. **The sandbox architecture is genuinely well-designed.** PRD 05 section 6 is one of the strongest sections in the entire suite -- the four-tier model with policy-floor promotion, the detailed explanation of why `none` is a valid tier, and the WASM-first default with WIT interface contract are all carefully reasoned. The sandbox selection pseudocode is implementable.

3. **The MVP plan is realistic and disciplined.** The scoping is aggressive in the right direction -- cutting OPA, SpiceDB, Temporal, Ory, Presidio, and MinIO from MVP while preserving the core value proposition (YAML + visual editor + LiteLLM + WASM sandbox + Langfuse traces). The phase dependency graph is accurate, and the parallelization opportunities are correctly identified.

**Top 3 Risks:**

1. **Infrastructure weight for self-hosted deployment.** The full-profile `docker-compose.yaml` runs 13 containers (API, Worker, UI, LiteLLM, Temporal, OPA, SpiceDB, Ory Kratos, Langfuse, Infisical, PostgreSQL, Valkey, MinIO). Even the MVP runs 6 containers. This is a substantial resource requirement for the stated target of "teams of 3-20." The `--profile minimal` fallback matrix is mentioned but never fully specified -- which combinations of swaps are tested and supported is undefined.

2. **WASM Component Model maturity risk.** The PRDs bet heavily on WASM Component Model support (WIT interfaces, componentize-py, WASI Preview 2). While the MVP plan acknowledges this risk and budgets extra time, the WIT contract is presented as settled when the Component Model ecosystem is still maturing rapidly. The `wasmtime-py` bindings for Component Model have known gaps. If this doesn't work cleanly, the entire WASM tool story degrades to "subprocess Wasmtime CLI," which changes the performance characteristics substantially.

3. **Cross-PRD API path inconsistency and under-specification of the Automation lifecycle.** The kickoff endpoint appears as both `/api/v1/automations/{id}/kickoff` (PRD 05, PRD 09) and `POST /executions/kickoff` (MVP plan task 2.8). PRD 09 introduces the Automation resource but its relationship to Crew/Flow is hand-waved -- the "deployment" concept (build pipeline, versioning, Git sync) is substantial custom code that is neither well-estimated nor clearly scoped for post-MVP phases.

---

## Per-PRD Findings

---

### PRD 00 -- Overview

**Rating**: Strong

**Issues:**

1. (Minor, Module Map) The description says "Each PRD that follows is self-contained and can be implemented as an independent work stream," but PRD 05 (Execution Engine) depends on PRD 01, 03, 04, 05, and 06. This claim is aspirational, not accurate. **Fix:** Reword to "Each PRD can be owned by an independent team, but cross-module dependencies exist and are documented in each PRD's dependencies section."

2. (Minor, Infrastructure Components) Temporal is listed in the infrastructure table but not in the docker-compose under PRD 00-integrations -- Temporal requires its own PostgreSQL or Cassandra backend for visibility, which is unmentioned. **Fix:** Add a note about Temporal's own persistence requirement and whether it shares the Blackbeard PostgreSQL instance.

**What's good:** The architecture diagram, design principles table, and persona definitions are crisp. The "What CrewAI already provides" table is the single most important artifact for preventing scope creep -- it should be posted on the wall.

---

### PRD 00 -- Integrations

**Rating**: Strong

**Issues:**

1. (Minor, docker-compose) The `presidio-analyzer` entry has a comment saying "runs as a library inside workers -- no separate service needed" but is still listed as a service entry. This will confuse engineers reading the compose file. **Fix:** Remove the `presidio-analyzer` service entry entirely and note it as a pip dependency in the worker image.

2. (Minor, Swappable Components) The "Simpler Alternative" table says "PostgreSQL RBAC tables" replaces SpiceDB and "In-process Python policy evaluator" replaces OPA, but there is no specification for either fallback implementation. The MVP plan takes the right approach (skip SpiceDB and OPA entirely), but the post-MVP migration path from simple fallbacks to the full stack is unspecified. **Fix:** Add a note that the MVP implementations (in-process policy check, PostgreSQL-based RBAC) ARE the simple fallbacks, and document the migration path.

**What's good:** The "What Blackbeard Actually Builds" table at the bottom is excellent -- it forces the team to confront the fact that Blackbeard's custom code is primarily glue and UX, not infrastructure. This is the right architecture for a small team.

---

### PRD 01 -- Core Object Model

**Rating**: Strong

**Issues:**

1. (Major, Section 2.4 Flow) The Flow resource's `routing` section uses a separate top-level `routing` key with step-level routing configuration, but the `steps` array also has `trigger: listen: approved` (listening to a router label). The interaction between these two mechanisms is ambiguous. If I define a router step in `routing` but also set a `trigger.listen` on the downstream step, which takes precedence? Is the `routing` section required, or can it be inferred from `trigger.listen` values? **Fix:** Clarify whether `routing` is the source of truth (and `trigger.listen` is redundant) or whether both are required. Recommend making one canonical and the other derived.

2. (Major, Section 6) The database schema uses a single `resources` table for all 20+ resource kinds. This is a valid approach (generic resource storage), but the PRD doesn't address query performance when the table grows large. With JSONB `spec` columns, complex queries (e.g., "find all agents that reference tool X") will require JSONB path queries that don't use indexes well. **Fix:** Add a note about expected table size and query patterns. Consider whether the `resource_refs` table is sufficient for cross-reference queries, and whether kind-specific materialized views may be needed at scale.

3. (Minor, Section 3) The deletion behavior says force delete "marks all inbound references as broken," but there's no `status` or `broken` field in the `resource_refs` schema or the `resources` schema to track this. **Fix:** Add a `status` field to `resource_refs` (e.g., `active` / `broken`) or describe how broken refs are tracked.

4. (Minor, Section 7) The API surface uses `{kind}` in paths (e.g., `/api/v1/Agent/researcher`), but the case convention is inconsistent with REST norms (typically lowercase plural: `/api/v1/agents/researcher`). PRD 11 uses both patterns. **Fix:** Pick one convention and enforce it everywhere. K8s uses lowercase plural (`/apis/v1/agents`), which would be more natural.

**What's good:** The `ref:` resolution algorithm (topological sort with cycle detection) is well-specified. The namespace-scoped resolution with explicit cross-namespace syntax (`production/agents/researcher`) is clean. The resource catalogue table in 2.9 that maps every kind to its defining PRD is an excellent cross-reference.

---

### PRD 02 -- Visual Graph Editor (Studio)

**Rating**: Adequate

**Issues:**

1. (Major, Section 5) The Property Panel promises "auto-generated forms from the YAML spec schema" using React Hook Form + JSON Schema, but the resource schemas include complex constructs: `ref:` autocomplete, `callbacks.*` with Python dotted paths + "Test Import" button, inline LLM guardrails (free-text strings) mixed with `ref:` guardrails, and nested objects like `checkpoint` config. Auto-generation from JSON Schema alone won't handle these -- each needs custom form widgets. **Fix:** Identify which fields need custom widgets versus auto-generated inputs. Budget the custom widget work explicitly.

2. (Major, Section 7) The Execution View specifies SSE streaming from the backend and fallback polling, but doesn't define how the execution view maps to the canvas. If a crew has 3 agents and 5 tasks, how does the execution view know which canvas node corresponds to which running task? The mapping between resource names and node IDs is unspecified. **Fix:** Define the node ID convention (e.g., `{kind}-{name}`) and the mapping between execution events (which carry `task_name` and `agent_name`) and canvas nodes.

3. (Minor, Section 12) Canvas layout is stored in a `canvas_layouts` table with `(resource_kind, resource_name, layout JSONB, updated_at)`, but this table lacks a `namespace` column. If the same crew name exists in two namespaces, layouts would collide. **Fix:** Add `namespace` to the `canvas_layouts` table schema.

4. (Minor, Section 3.5) Crew Node uses React Flow's `Group` node type with `parentId`, but the PRD doesn't address what happens when a user drags an existing agent node into a crew bounding box (reparenting) or out of it. **Fix:** Define the interaction model for drag-into-crew and drag-out-of-crew.

**What's good:** The YAML-to-canvas synchronization diagram in section 11 is clear. The conflict resolution strategy ("last-write-wins with undo history" for v1) is the right call -- CRDT-based collaboration would be a massive scope expansion. The accessibility section (keyboard navigation, screen reader, high-contrast) is good to include even if it's aspirational for MVP.

---

### PRD 03 -- RBAC & Identity

**Rating**: Strong

**Issues:**

1. (Critical, Section 8.5) The principal chain intersection algorithm specifies that user permissions AND agent permissions must both allow an action, but this creates an operational problem: if an automation runs on a cron schedule (PRD 09), who is the "kicking user"? Cron-triggered executions have no human user in the chain. The PRD doesn't define what happens when the principal chain has no User link. **Fix:** Define a `ServiceAccount` or `SystemPrincipal` that is used for scheduled/triggered executions. Specify which permissions it inherits and how it's configured per-automation.

2. (Major, Section 6) Entity-level permissions are stored "in the `spec` column of the `resources` table as part of the resource's metadata." But the examples show `metadata.access`, not `spec.access`. Which is it -- metadata or spec? This matters for schema validation and for whether entity-level permissions are version-controlled with the resource. **Fix:** Clarify that entity-level access is in `metadata.access` (not spec), and update the storage note accordingly.

3. (Major, Section 7) The authorization flow says steps 2-5 are "cached per-request" with <5ms for cached principals, but doesn't define the cache key or invalidation strategy beyond "invalidated on role/policy/binding changes via the internal event bus." In a multi-worker deployment, event bus propagation has latency. A user could be revoked on one worker and still authorized on another for the duration of the cache TTL. **Fix:** Specify the cache TTL (e.g., 30 seconds) and acknowledge the consistency window. For security-critical deployments, note that cache TTL can be set to 0 (always check).

4. (Minor, Section 2.4) The `Rule` resource has no `metadata.name` field in the example, but all other resources do. Rules appear to be embedded in Roles rather than standalone. Clarify whether Rules are standalone resources (with their own CRUD lifecycle) or always embedded. The resource catalogue (PRD 01, section 2.9) lists Rule as a standalone kind. **Fix:** Add `metadata.name` to the Rule example, or clarify that Rules are embedded in Roles and not independently addressable.

**What's good:** The AgentPolicy design is the crown jewel of the entire PRD suite. The separation of RBAC (authorization to resources) from AgentPolicy (runtime constraints) is exactly right. The policy enforcement points table in section 3.3 is comprehensive and implementable. The predefined agent policies (unrestricted through air-gapped) are a useful starting point.

---

### PRD 04 -- Tool & Integration Registry

**Rating**: Adequate

**Issues:**

1. (Major, Section 3) The Tool resource schema has a `type` field with values `python | wasm | mcp-stdio | mcp-http | rest | integration | composio | custom`, but the example in section 3 uses `type: integration`, which isn't listed in the header comment of the schema example (which says `python | mcp | rest | composio`). The section 2 table uses different type names (`MCP (stdio)`, `MCP (SSE/HTTP)`) than the schema (`mcp-stdio`, `mcp-http`). **Fix:** Settle on one canonical list of type values and use it consistently in every table, schema, and example.

2. (Major, Section 4.3) The OAuth connection flow says "tokens are stored encrypted in the database," but PRD 00-integrations says secrets are stored in Infisical, and PRD 03 says secrets are never in Blackbeard's DB. Where are OAuth tokens actually stored? **Fix:** Clarify that OAuth tokens are stored in Infisical (not the resources DB), and describe how the token retrieval works at execution time.

3. (Minor, Section 4.1) The v1 connectors list (GitHub, Slack, Gmail) overlaps with the "post-v1 community-driven" list that includes Microsoft Teams, Jira, etc. -- but the MVP plan explicitly excludes OAuth integrations entirely. The v1/post-v1 labeling in this PRD conflicts with the MVP plan. **Fix:** Align terminology: "v1" in this PRD should mean "first GA release" (which is post-MVP), not MVP. Add a note clarifying the relationship.

4. (Minor, Section 8) Rate limit enforcement uses Valkey sliding-window counters, which is good, but the `max_concurrent` field (default: 10) is mentioned in the security section but not in the Tool schema (section 3). **Fix:** Add `max_concurrent` to the Tool resource schema.

**What's good:** The WASM tool packaging structure and WIT contract are well-specified and duplicate-consistent with PRD 05. The MCP tool discovery flow (connect, call `tools/list`, import as Tool resources) is a clean integration pattern.

---

### PRD 05 -- Execution Engine

**Rating**: Strong

**Issues:**

1. (Critical, Section 6.5, Last Row) The sandbox selection logic table shows `(unset, mcp-http) | wasm | wasm | none` with the note "Remote HTTP call -- no local code, no sandbox needed (floor doesn't apply to remote calls)." This is a policy bypass: if an agent's policy has `minimum_tier: wasm`, remote tools bypass that floor entirely. This is defensible but needs to be an explicit, documented exception in the AgentPolicy spec (PRD 03), not just a comment in a table. An auditor reviewing AgentPolicy YAML would expect `minimum_tier: wasm` to mean "everything runs in wasm or above." **Fix:** Add an explicit `remote_tools_bypass_floor: true | false` field to AgentPolicy.sandbox spec with a default of `true`. Document the rationale in both PRD 03 and PRD 05.

2. (Major, Section 3.1) The kickoff endpoint is `POST /api/v1/automations/{id}/kickoff`, but this requires an Automation resource to exist before you can run a crew. For MVP, there is no Automation resource (it's in PRD 09). The MVP plan task 2.8 says `POST /executions/kickoff`. These are different endpoints with different resource models. **Fix:** Define the MVP kickoff endpoint clearly (probably `POST /api/v1/crews/{name}/kickoff`), and specify that the Automation-based kickoff is post-MVP.

3. (Major, Section 15) The `executions` table has `automation_id UUID FK -> resources (kind=Automation)` but the MVP doesn't have Automation resources. For MVP, this should FK to the crew/flow resource directly, or be nullable. **Fix:** Make `automation_id` nullable, and add a `resource_kind` + `resource_name` pair for direct crew/flow reference in MVP.

4. (Minor, Section 12) The `WorkflowBackend` interface is mentioned but not defined. Engineers implementing the in-process backend need to know the method signatures. **Fix:** Define the `WorkflowBackend` protocol/interface: at minimum `start_execution()`, `get_status()`, `cancel()`, `resume()`.

**What's good:** The tool dispatch pipeline (section 8) is the best-specified flow in the suite -- eight clear steps, each with defined inputs, outputs, and error handling. The sandbox tier comparison table with startup times, isolation levels, and use cases is immediately useful for operators deciding which tier to use.

---

### PRD 06 -- LiteLLM Integration

**Rating**: Strong

**Issues:**

1. (Major, Section 4.3) Four key scoping strategies are listed (per-execution, per-agent, per-crew, per-user), but only per-execution is used in MVP. The per-agent and per-crew strategies have lifecycle implications: when is the budget reset? The `budget_duration` field (from LiteLLM) is mentioned in the key generation example as `"1d"`, but how this maps to the different scoping strategies is unexplained. **Fix:** Define budget reset semantics for each scoping strategy. Per-execution is clear (key deleted on completion). Per-agent with `budget_duration: 1d` means the agent can spend $X per day across all executions -- is this correct?

2. (Minor, Section 3) The LLMConnection resource adds `rpm`, `tpm`, `fallback_to`, `context_window_fallback`, and `deployments` fields that are not present in the PRD 01 LLMConnection schema. PRD 01 shows a simpler schema (`provider`, `model`, `api_key_env`, `base_url`, `temperature`, `max_tokens`, `timeout`). **Fix:** Update PRD 01's LLMConnection schema to include the full field set, or note that PRD 06 extends the base schema.

3. (Minor, Section 9.1) The docker-compose snippet references `redis` as the service name for Valkey, and uses `REDIS_HOST: redis`. The rest of the PRD suite uses "Valkey" consistently. **Fix:** Use `valkey` as the service name for consistency.

**What's good:** The architecture diagram showing how CrewAI's LLM class is configured to point at LiteLLM Proxy is exactly what an engineer needs to understand the integration seam. The "what happens when budget is exceeded" flow (section 4.4) is crisp and testable. The circuit breaker design for LiteLLM unavailability (section 9.4) is a mature production concern that most PRDs at this stage would miss.

---

### PRD 07 -- Observability & Traces

**Rating**: Adequate

**Issues:**

1. (Major, Section 5.4) The dashboard implementation section says Blackbeard-specific dashboards query Blackbeard's `executions` and `execution_tool_calls` tables, "and optionally query Langfuse's API for token/cost aggregations." But there's no specification of which Langfuse API endpoints are used, what the data model looks like, or how the two data sources are joined. If the execution_id is the join key between Blackbeard's DB and Langfuse's traces, this needs to be explicit. **Fix:** Specify the join key (execution_id maps to Langfuse trace ID), the Langfuse API endpoints used for aggregation, and whether dashboard data is cached.

2. (Major, Section 7) Trace sampling is per-execution, but "policy denial events are always traced regardless of sampling rate." This means a sampled-out execution that has a policy denial will create an orphaned trace with only policy events and no parent execution context. **Fix:** Clarify: does "always traced" mean the policy denial creates its own mini-trace, or does it upgrade the execution from sampled-out to sampled-in? The latter is cleaner but changes the effective sampling rate.

3. (Minor, Section 4) The Trace UI section describes a rich visualization (Gantt chart, agent thoughts, tool call inspector), but the PRD also says Blackbeard "links to Langfuse UI" rather than embedding it. Are the visualizations in section 4 Langfuse's built-in UI, or custom Blackbeard UI? The MVP plan doesn't include building custom trace visualizations. **Fix:** Clarify which parts of the Trace UI are Langfuse's native views (linked to) versus custom Blackbeard views (built in-house). For MVP, make clear that all trace visualization is via Langfuse links.

**What's good:** The decision to use Langfuse as the trace backend rather than building custom trace storage is exactly right. The CrewAI event bus to Langfuse mapping (section 6 "Integration Configuration") is well-specified. The sampling strategy (per-execution, not per-event) prevents confusing partial traces.

---

### PRD 08 -- Guardrails & Safety

**Rating**: Adequate

**Issues:**

1. (Major, Section 2.4) Guardrails can be assigned at namespace, crew, and task levels, but the namespace-level assignment syntax uses `namespaces: production: required_guardrails:`, which implies a Namespace resource kind -- but Namespace is never defined as a resource kind in PRD 01's catalogue (section 2.9). There's no Namespace YAML schema anywhere in the PRD suite. **Fix:** Either define a Namespace resource kind in PRD 01, or specify that namespace-level guardrails are configured in PlatformConfig (PRD 06) or some other existing resource.

2. (Major, Section 2.5) The conflict resolution note says contradictory guardrails will "always fail" and "the system does not detect these conflicts automatically." For a safety-critical feature, this is a problem. If a namespace admin adds a >=500 word requirement and a developer adds a <=200 word limit, deployments will silently fail at runtime with confusing errors. **Fix:** Add conflict detection to `blackbeard validate` that checks for obviously contradictory guardrails (e.g., min/max word count conflicts across levels). This doesn't need to be comprehensive -- even basic checks would help.

3. (Minor, Section 3.2) The hallucination detection evaluation prompt is not specified. The quality of hallucination detection depends entirely on this prompt. **Fix:** Include the default evaluation prompt template, or at least describe its structure (e.g., "Given the following reference context and agent output, score the factual faithfulness on a 0-10 scale...").

4. (Minor, Section 4.3) The Presidio integration code shows `language="en"` hardcoded. Multi-language support is mentioned as a Presidio feature but not exposed in the `PIIConfig` schema. **Fix:** Add a `language` field to `PIIConfig.spec` (default: `"en"`, options: list of ISO 639-1 codes).

**What's good:** The decision to use Presidio as a library rather than a service is correct for the deployment model. The explicit rationale for not redacting tool inputs (section 4.5) is well-reasoned and prevents a common footgun. The performance impact note in section 2.1 (LLM-based guardrails add N*M additional LLM calls) is the kind of practical guidance engineers need.

---

### PRD 09 -- Deployment & Automation

**Rating**: Needs Work

**Issues:**

1. (Critical, Section 2) The Automation resource is the most complex resource in the suite (it references crews, policies, sandboxes, env vars, LLM connections, triggers, A2A config, versioning strategy, and access control), but it has no JSON Schema, no database schema, and no clear mapping to the generic `resources` table. Does an Automation go in the same `resources` table as Agents and Tasks? It has fundamentally different lifecycle concerns (deployment state, active version pointer, trigger registration). **Fix:** Define the Automation-specific database schema or explicitly state it uses the generic resources table. Define the state machine for Automation lifecycle (created -> deploying -> deployed -> degraded -> deleted).

2. (Critical, Section 4) The build pipeline is described at a high level but has zero implementation detail. "Compile WASM" -- using what build system? "Build image" -- which Dockerfile, what base image, what goes in it? "Install Python packages" -- from where, into what environment? For a deployment-focused PRD, this is unusually vague. **Fix:** This needs a separate technical design document. At minimum, define: (a) what the build artifact is (container image? zip file? resource bundle?), (b) where build artifacts are stored (MinIO? container registry?), (c) what the relationship is between a "build" and a "version."

3. (Major, Section 7) Version immutability ("versions are immutable snapshots of the resource graph + dependencies") implies the system takes a snapshot of all referenced resources at deploy time. This is architecturally significant -- it means the `resources` table needs to support immutable versioned snapshots, not just mutable resources with optimistic locking. This capability is not described in PRD 01. **Fix:** Specify the snapshot mechanism. Options: (a) copy all referenced resources into a version-specific snapshot table, (b) version the resources table itself with Git-like commits, (c) store the full resolved YAML bundle in MinIO. Pick one and detail it.

4. (Major, Section 6) A2A protocol support says "per-agent endpoints extend CrewAI's standard A2A protocol," but does not specify how external A2A requests are authenticated, how they map to the RBAC system, or how the principal chain is constructed for an externally-initiated A2A request. **Fix:** Define how an external A2A caller is authenticated (API key? OIDC?) and what principal is used in the execution's principal chain.

5. (Minor, Section 5) The "Custom" trigger type is described as "webhook + filter logic" but no filter DSL or configuration schema is provided. **Fix:** Define the filter configuration schema or defer custom triggers to post-v1 explicitly.

**What's good:** The trigger taxonomy (API, webhook, schedule, app-based) is well-organized. The health check specification for deployed automations (section 7) covers the right checks (LiteLLM reachability, tool availability, LLM connection validity, sandbox readiness). The webhook streaming configuration (section 8) with retry and HMAC signatures is production-ready.

---

### PRD 10 -- Agent & Asset Repository

**Rating**: Adequate

**Issues:**

1. (Major, Section 5.3) The override mechanism (`overrides: goal: "..."`) is powerful but the merge semantics are undefined. If a repository agent has `tools: [A, B, C]` and the override says `tools: [D]`, does D replace the list or extend it? What about nested objects like `checkpoint` config? **Fix:** Define the merge strategy explicitly: shallow merge (override replaces top-level keys) or deep merge (override patches at any depth). Document behavior for lists (replace vs. append).

2. (Major, Section 7) Dependency resolution for repository assets ("installing the crew also installs the latest compatible agent version") implies a package manager. This is substantial engineering work: dependency resolution with semver ranges, conflict detection, lockfile generation. None of this is estimated in the MVP plan (and shouldn't be for MVP). **Fix:** Mark transitive dependency resolution as post-v1 explicitly. For v1, require all dependencies to be pinned to exact versions.

3. (Minor, Section 3) The repository structure shows filesystem paths, but the actual storage backend (MinIO per PRD 00) is never referenced. How does `blackbeard repo publish` upload to MinIO? What's the MinIO bucket structure? **Fix:** Specify the MinIO bucket layout (e.g., `s3://blackbeard-repo/{kind}/{name}/{version}/`) and the metadata index storage (PostgreSQL? Sidecar file in MinIO?).

**What's good:** The approval workflow (Open / Review / Locked) is appropriately simple for v1. The fork-vs-override distinction (section 5.4) with clear guidance ("use ref + overrides to track upstream, fork for full customization") is good product design.

---

### PRD 11 -- API & Extensibility

**Rating**: Adequate

**Issues:**

1. (Major, Section 2.1) The REST API uses `{kind}` in paths with PascalCase (e.g., `/api/v1/Agent/researcher`), but earlier in the same section, automation endpoints use lowercase (`/api/v1/automations/{id}/kickoff`). This inconsistency will confuse API consumers. **Fix:** Pick one convention. Recommendation: lowercase plural for all paths (`/api/v1/agents/{name}`, `/api/v1/automations/{name}/kickoff`). If PascalCase is preferred for K8s consistency, use it everywhere.

2. (Major, Section 5) The Plugin SDK defines 9 plugin types with base classes (`BaseTool`, `BaseLLMProvider`, `BaseAuthProvider`, etc.) but none of these interfaces are specified. An engineer cannot implement a plugin without knowing the method signatures. **Fix:** Define at minimum the `BaseTool`, `BaseSandboxProvider`, and `BaseTrigger` interfaces with method signatures and expected behavior. The others can be deferred, but tool plugins are core.

3. (Minor, Section 3) The gRPC API is specified as a proto definition but the actual `.proto` file is not included. The `StreamExecution` RPC returns `stream ExecutionEvent` but `ExecutionEvent` is not defined. **Fix:** Either include a complete `.proto` file or defer gRPC to post-MVP (which the MVP plan already does). Don't leave a partial proto that can't be compiled.

4. (Minor, Section 9) Python and TypeScript SDKs are promised but neither is in the MVP scope. They should be explicitly marked as post-MVP. **Fix:** Add a "Post-MVP" marker to sections 9.1 and 9.2.

**What's good:** The webhook streaming protocol (section 4) with HMAC signatures, replay protection, and idempotency guidance is well-specified. The CLI command taxonomy (section 6) covers the right operations and follows a consistent `blackbeard {noun} {verb}` pattern.

---

## Cross-Cutting Issues

1. **API Path Convention Inconsistency (Critical)**. The API path format varies across PRDs:
   - PRD 01: `/api/v1/{kind}/{name}` (PascalCase kind)
   - PRD 05: `/api/v1/automations/{id}/kickoff` (lowercase plural)
   - PRD 09: `/api/v1/Automation/{name}/kickoff` (PascalCase singular)
   - PRD 11: mixes all three
   - MVP Plan: `POST /executions/kickoff` (no `/api/v1` prefix)

   **Fix:** Create an API design guide document. Define one convention. Apply it to every PRD.

2. **Namespace Resource Not Defined (Major)**. Multiple PRDs reference namespace-level configuration (PRD 03: namespace-scoped RoleBindings, PRD 08: namespace-level required guardrails, PRD 03: namespace default AgentPolicy), but there is no Namespace resource kind defined anywhere. PRD 01's resource catalogue (section 2.9) does not include Namespace. PRD 03 section 11 mentions it conceptually but provides no schema.

   **Fix:** Define a Namespace resource kind in PRD 01 with its schema, including fields for `default_agent_policy`, `required_guardrails`, and `default_sandbox_tier` that other PRDs reference.

3. **Event Bus Transport Undefined (Major)**. Every PRD emits events, but the event bus implementation is never specified. Is it Valkey pub/sub? An in-process Python event emitter? CrewAI's `crewai_event_bus`? For MVP (single process), in-process is fine, but the event naming conventions, payload schemas, and subscriber registration mechanism need to be defined. Currently, event payloads are described in English but not as structured schemas.

   **Fix:** Define the event bus interface (publish, subscribe, event envelope format) and specify that MVP uses in-process pub/sub, with Valkey pub/sub for multi-worker deployments.

4. **LLMConnection Schema Divergence (Minor)**. PRD 01 defines a simple LLMConnection with 7 fields. PRD 06 extends it with `rpm`, `tpm`, `fallback_to`, `context_window_fallback`, and `deployments`. These need to be reconciled into one schema.

   **Fix:** Update PRD 01 to include the full LLMConnection schema from PRD 06, or explicitly note that PRD 06 extends the base schema.

5. **Auth Model Mismatch Between MVP and Full Product (Minor)**. MVP uses a single `BLACKBEARD_API_KEY` env var. Full product uses Ory Kratos/Hydra + SpiceDB + OPA. The migration path is not described. How does the single-user MVP evolve to multi-user without breaking existing deployments?

   **Fix:** Add a section to PRD 03 or the MVP plan describing the migration path: what happens to API key-based auth when Ory Kratos is introduced? Are both supported simultaneously during transition?

---

## MVP Plan Assessment

**Timeline Realism:**

The 12-week timeline for a solo developer is optimistic but not unreasonable, with two major risks:

1. **Phase 4 (WASM Sandbox):** The plan allocates 5-7 days but acknowledges the Component Model risk with "budget 2x time." If componentize-py integration doesn't work cleanly, this phase could easily take 3 weeks instead of 1.5-2. The fallback (subprocess-based Wasmtime CLI) changes the performance story and requires a different integration pattern.

2. **Phase 6 (Studio):** 15 days for a full visual graph editor with bidirectional YAML sync, property panel, undo/redo, and execution view is tight. The bidirectional YAML sync (task 6.7) alone is a notorious source of bugs. If this slips, it impacts Phase 7 and 8.

For a team of 2 (the "~7 weeks" estimate), the plan is feasible. For a team of 4 ("~5 weeks"), the parallelization works but coordination overhead between the execution engine developer, the WASM developer, and the frontend developer is non-trivial.

**Missing Tasks:**

1. **Database migrations for canvas_layouts table** (PRD 02 section 12) -- not in any phase.
2. **Guardrail execution** (PRD 08 section 2.3) -- not in MVP scope, but Task-level guardrails should be MVP. CrewAI already supports them; Blackbeard just needs to wire them up during resource loading. This is a low-cost, high-value addition.
3. **Error handling and graceful degradation** -- Phase 2 doesn't include any error handling tasks, but PRD 05 section 14 defines 7 error categories. At least the basic ones (LLM timeout, tool error, callback failure) should be explicitly tasked.
4. **CORS configuration** -- mentioned in Phase 0 but not detailed. This is often a source of day-1 bugs.
5. **API key authentication middleware** -- the MVP uses `BLACKBEARD_API_KEY` but no task creates the middleware that validates it.

**Dependency Risks:**

1. The dependency graph correctly shows Phases 2, 4, and 6 as parallelizable after Phase 1. However, Phase 5 (Agent Policies) depends on both Phase 2 (execution engine) and Phase 4 (WASM sandbox -- for tier promotion testing). This dependency is not shown in the graph.
2. Phase 3 (Langfuse) depends on Phase 2 being functionally complete (it needs execution events to map). The timeline shows them overlapping in Week 5, which is aggressive.

**Team Sizing:**

The "solo developer" assumption is realistic for this scope. For a team of 2, the optimal split is: Person A does Phases 0, 1, 2, 3, 5, and 8. Person B does Phases 4, 6, 7, and joins 8. Person B can start Phase 6 tasks 6.1-6.11 in parallel with Phase 1 (using mock data), then integrate with the real API after Phase 1 completes.

---

## Recommendations

Prioritized by impact on implementation success:

1. **(Fix Before Implementation)** Standardize API path convention across all PRDs. Create a one-page API design guide: path format, casing, pluralization, versioning. Apply it to every endpoint reference in every PRD.

2. **(Fix Before Implementation)** Define the Namespace resource kind. Multiple PRDs reference namespace-level configuration that doesn't exist yet. This is a 1-page addition to PRD 01 but unblocks PRD 03 (RBAC), PRD 05 (policy resolution), and PRD 08 (guardrails).

3. **(Fix Before Implementation)** Reconcile the kickoff endpoint. The MVP needs one clear kickoff path. Recommendation: `POST /api/v1/crews/{name}/kickoff` for MVP, with `POST /api/v1/automations/{name}/kickoff` added when Automation resources ship. Update PRD 05 section 3.1 and the MVP plan task 2.8 to match.

4. **(Fix Before Phase 2)** Define the `WorkflowBackend` interface. Engineers implementing the in-process execution backend need method signatures. Even a 10-line Python protocol class is sufficient.

5. **(Fix Before Phase 4)** Build a WASM proof-of-concept spike before committing to the Phase 4 timeline. Allocate 2-3 days in Week 1-2 to: compile a simple Python tool to WASM via componentize-py, load it in wasmtime-py with Component Model support, invoke it, and measure startup time. If this spike fails, the fallback plan needs to be executed immediately, not discovered in Week 6.

6. **(Fix Before Phase 5)** Resolve the cron/scheduled execution principal chain problem. Define what identity is used when no human initiates the execution. This is a design decision, not a bug fix -- but it needs to be made before policy enforcement is built.

7. **(Address Before GA, Not MVP)** Flesh out PRD 09 (Deployment & Automation). This is the weakest PRD in the suite. The build pipeline, version snapshot mechanism, and A2A authentication all need technical design documents before implementation begins. This is correctly excluded from MVP, but the post-MVP team needs substantially more detail.

8. **(Address Before GA)** Add conflict detection for multi-level guardrails to `blackbeard validate`. Even a basic check ("namespace requires >= X words, task limits <= Y words where Y < X") would prevent confusing runtime failures.

9. **(Consider for MVP)** Add basic CrewAI guardrail wiring to MVP scope. CrewAI already supports task-level guardrails. Blackbeard just needs to resolve `guardrails: [ref:guardrails/foo]` to CrewAI guardrail objects during resource loading. This is 1-2 days of work for meaningful safety value.

10. **(Track)** Monitor the `wasmtime-py` Component Model and `componentize-py` ecosystems weekly during development. If either project makes breaking changes or reveals immaturity, trigger the fallback plan (subprocess-based Wasmtime CLI) early rather than late.
