# PRD 01 — Core Object Model

## 1. Purpose

Define the canonical data model for every first-class resource in Blackbeard. All resources are YAML-serialisable, versionable, and exposed through a uniform CRUD API. Python code (callbacks, guardrails, tool implementations) is never inlined — it is referenced by a qualified import path and resolved at runtime.

## 1.1 MVP Scope

**MVP resource kinds:** Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail. These are the only kinds implemented for MVP. **Deferred to post-MVP:** Flow, KnowledgeSource, EnvironmentVariable, Namespace (beyond `default`), ServiceAccount, and all RBAC kinds (Role, RoleBinding, SSOConfig, APIKey). The schemas and YAML examples below cover the full v1 design; see the MVP Implementation Plan for what ships first.

---

## 2. Resource Catalogue

### 2.1 Agent

An autonomous unit that performs tasks using an LLM, tools, and a persona.

```yaml
# agents/researcher.yaml
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
  labels:
    team: data-science
    tier: senior
spec:
  role: "Senior Data Researcher"
  goal: "Uncover cutting-edge developments in {topic}"
  backstory: |
    You're a seasoned researcher with a knack for uncovering the latest
    developments in {topic}.
  llm: gpt-4o                          # string or LLMConfig ref
  function_calling_llm: gpt-4o-mini    # optional, cheaper model for tool calls
  tools:
    - "ref:tools/serper-search"
    - "ref:tools/wikipedia"
  knowledge_sources:
    - "ref:knowledge/company-docs"
  max_iter: 20
  max_rpm: 60
  max_execution_time: 300              # seconds
  max_retry_limit: 2
  allow_delegation: false
  allow_code_execution: false
  code_execution_mode: safe            # safe | unsafe
  multimodal: false
  reasoning: true
  max_reasoning_attempts: 3
  memory: true
  cache: true
  verbose: false
  respect_context_window: true
  inject_date: true
  date_format: "%Y-%m-%d"
  templates:
    system: "templates/system-default.j2"   # optional, Jinja2 path
    prompt: null
    response: null
  callbacks:
    step: "myproject.callbacks:on_agent_step"       # Python qualified name
    before_action: null
    after_action: null
  policy: null                         # set to "ref:agent-policies/<name>" to override crew/namespace default
  embedder:
    provider: openai
    config:
      model: text-embedding-3-small
```

**Key design decisions:**

- `ref:` syntax for cross-resource references (tools, knowledge, templates).
- `callbacks.*` fields take Python dotted paths (`module.submodule:function_name`).
- `llm` accepts either a model string or a reference to an `LLMConnection` resource.
- Labels enable RBAC selectors and filtering.

### 2.2 Task

A discrete unit of work assigned to an Agent.

```yaml
# tasks/research-ai.yaml
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: research-ai
spec:
  description: |
    Conduct thorough research about {topic}.
    Make sure you find any interesting and relevant information.
  expected_output: |
    A list with 10 bullet points of the most relevant information about {topic}.
  agent: "ref:agents/researcher"
  tools:
    - "ref:tools/serper-search"
  context:
    - "ref:tasks/gather-sources"       # depends on output of this task
  async_execution: false
  human_input: false
  markdown: true
  output_file: "outputs/research-{topic}.md"
  output_format: raw                   # raw | json | pydantic
  output_schema: null                  # JSON Schema or Pydantic model ref
  guardrails:
    - "ref:guardrails/word-count-limit"
    - "The output must contain at least 5 cited sources"   # LLM-based string
  guardrail_max_retries: 3
  callbacks:
    on_complete: "myproject.callbacks:on_task_done"
    on_fail: "myproject.callbacks:on_task_fail"
```

### 2.3 Crew

A group of agents and tasks with an execution strategy.

```yaml
# crews/research-crew.yaml
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: research-crew
spec:
  agents:
    - "ref:agents/researcher"
    - "ref:agents/analyst"
  tasks:
    - "ref:tasks/research-ai"
    - "ref:tasks/write-report"
  process: sequential                 # sequential | hierarchical
  manager_llm: gpt-4o                # required if hierarchical
  manager_agent: null                 # optional custom manager
  memory: true
  cache: true
  max_rpm: 100
  verbose: false
  planning: true
  planning_llm: gpt-4o-mini
  stream: false
  checkpoint:
    enabled: true
    location: ".checkpoints/"
    on_events: ["task_completed"]
    max_checkpoints: 10
  callbacks:
    before_kickoff: "myproject.hooks:prepare_inputs"
    after_kickoff: "myproject.hooks:process_output"
    step: null
    task: null
  default_guardrails:                  # applied to all tasks unless task overrides
    - "ref:guardrails/no-pii-in-output"
  default_agent_policy: "ref:agent-policies/standard"   # applied to all agents unless agent overrides
  knowledge_sources:
    - "ref:knowledge/company-docs"
  embedder:
    provider: openai
```

### 2.4 Flow

An event-driven workflow graph connecting tasks, crews, and arbitrary code steps.

```yaml
# flows/content-pipeline.yaml
apiVersion: blackbeard/v1
kind: Flow
metadata:
  name: content-pipeline
spec:
  state_schema: "myproject.models:ContentPipelineState"  # optional Pydantic model
  persistence:
    backend: sqlite                   # sqlite | postgres | custom
    location: ".flow-state/"
  steps:
    - name: generate-topic
      type: function                  # function | crew | agent
      entrypoint: "myproject.steps:generate_topic"
      trigger: start
    - name: research
      type: crew
      crew: "ref:crews/research-crew"
      trigger:
        listen: generate-topic
    - name: review
      type: function
      entrypoint: "myproject.steps:human_review"
      trigger:
        listen: research
      human_feedback:
        message: "Approve this research?"
        emit: [approved, rejected, needs-revision]
        default_outcome: needs-revision
    - name: publish
      type: function
      entrypoint: "myproject.steps:publish"
      trigger:
        listen: approved              # listens to router label
    - name: revise
      type: crew
      crew: "ref:crews/research-crew"
      trigger:
        listen: needs-revision
  routing:
    - step: review
      type: router
      routes:
        approved: publish
        rejected: null                # terminates
        needs-revision: revise
  stream: true
```

**Routing source of truth**: The `routing` section is the canonical definition of router behavior. The `trigger.listen` values on downstream steps must match route labels defined in `routing.routes`. If a step has `trigger.listen: approved` but no upstream router defines an `approved` route, validation fails. The `routing` section can be omitted — in that case, `trigger.listen` values match step names (the step fires when the named step completes), and there is no routing logic.

### 2.5 Tool

A capability an agent can invoke. Wraps a Python function, MCP server, or external API.

```yaml
# tools/serper-search.yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: serper-search
  labels:
    category: search
spec:
  type: python                        # python | wasm | mcp-stdio | mcp-http | rest | integration | composio | custom
  implementation: "crewai_tools:SerperDevTool"
  description: "Search the web using Serper.dev API"
  parameters:
    query:
      type: string
      required: true
      description: "Search query"
  env:
    - SERPER_API_KEY
  rate_limit:
    max_rpm: 100
  cache: true
```

### 2.6 LLMConnection

Named LLM provider configuration.

```yaml
# llm-connections/openai-prod.yaml
apiVersion: blackbeard/v1
kind: LLMConnection
metadata:
  name: openai-prod
spec:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
  base_url: null                      # for Azure or proxy endpoints
  temperature: 0.7
  max_tokens: 4096
  timeout: 120
  rpm: 200                            # requests per minute (used by LiteLLM routing)
  tpm: 100000                         # tokens per minute (used by LiteLLM routing)
  
  # Routing & fallbacks (PRD 06)
  fallback_to:
    - "ref:llm-connections/anthropic-claude-sonnet"
  context_window_fallback:
    - "ref:llm-connections/openai-gpt4o-mini"
  
  # Load balancing: multiple deployments of the same model (PRD 06)
  deployments:
    - name: openai-primary
      api_key_env: OPENAI_API_KEY
      rpm: 200
    - name: openai-secondary
      api_key_env: OPENAI_API_KEY_2
      rpm: 200
```

See PRD 06 for how `rpm`, `tpm`, `fallback_to`, `context_window_fallback`, and `deployments` fields map to LiteLLM Proxy configuration.

### 2.7 KnowledgeSource

A corpus or RAG data source available to agents.

```yaml
# knowledge/company-docs.yaml
apiVersion: blackbeard/v1
kind: KnowledgeSource
metadata:
  name: company-docs
spec:
  type: directory                     # directory | url | s3 | database
  path: "./knowledge/docs/"
  embedder:
    provider: openai
    config:
      model: text-embedding-3-small
  chunk_size: 1000
  chunk_overlap: 200
```

### 2.8 EnvironmentVariable

Scoped secrets and config values.

```yaml
apiVersion: blackbeard/v1
kind: EnvironmentVariable
metadata:
  name: serper-api-key
spec:
  key: SERPER_API_KEY
  value_from:
    secret: secret://serper-key           # resolves via configured secrets backend (Infisical by default)
  scope: organization                     # organization | crew | agent
```

### 2.9 Complete Resource Kind Catalogue

PRD 01 defines the core **workload resources** above. Additional resource kinds are introduced in their respective PRDs:

| Kind | Defining PRD | Category | Description |
|------|-------------|----------|-------------|
| Agent | PRD 01 | Workload | Autonomous unit with LLM, tools, persona |
| Task | PRD 01 | Workload | Discrete unit of work assigned to an agent |
| Crew | PRD 01 | Workload | Group of agents and tasks with execution strategy |
| Flow | PRD 01 | Workload | Event-driven workflow graph |
| Tool | PRD 01 | Workload | Capability an agent can invoke |
| LLMConnection | PRD 01 | Configuration | Named LLM provider configuration |
| KnowledgeSource | PRD 01 | Workload | RAG data source for agents |
| EnvironmentVariable | PRD 01 | Configuration | Scoped secrets and config values |
| Rule | PRD 03 | RBAC | Single permission statement (embedded in Roles, not independently addressable) |
| Role | PRD 03 | RBAC | Named collection of rules |
| RoleBinding | PRD 03 | RBAC | Associates a role with subjects |
| AgentPolicy | PRD 03 | RBAC | Runtime constraints for agents |
| SSOConfig | PRD 03 | Identity | SSO/OIDC provider configuration |
| APIKey | PRD 03 | Identity | Machine identity for CI/CD |
| Sandbox | PRD 05 | Execution | Sandbox profile with resource limits |
| IntegrationConnector | PRD 04 | Integration | OAuth-based external service connector |
| MCPServer | PRD 04 | Integration | MCP server registration |
| LLMRoutingConfig | PRD 06 | Configuration | LLM routing strategy and fallbacks |
| PlatformConfig | PRD 06 | Configuration | Platform-wide settings |
| ObservabilityConfig | PRD 07 | Configuration | Trace and observability settings |
| Guardrail | PRD 08 | Safety | Reusable output validation logic |
| PIIConfig | PRD 08 | Safety | PII detection and redaction rules |
| Automation | PRD 09 | Deployment | Deployed instance of a Crew or Flow |
| WebhookEndpoint | PRD 11 | Integration | External webhook subscription |
| Namespace | PRD 01 | Configuration | Logical subdivision with default policies |
| ServiceAccount | PRD 01 | Identity | Machine identity for CI/CD, triggers, A2A |
| Plugin | PRD 11 | Extensibility | Plugin manifest and configuration |

All resource kinds follow the same `apiVersion/kind/metadata/spec` envelope and are stored in the unified `resources` table (section 7). Each kind has its own JSON Schema for `spec` validation. The kind registry and URL plural mapping are defined in `blackbeard/kinds.py` (single source of truth).

### 2.10 Namespace

A logical isolation boundary for resources. Namespaces scope RBAC, policies, and guardrails.

```yaml
# namespaces/production.yaml
apiVersion: blackbeard/v1
kind: Namespace
metadata:
  name: production
spec:
  description: "Production environment"
  defaults:
    agent_policy: "ref:agent-policies/standard"
    sandbox_tier: wasm
    guardrails:
      - "ref:guardrails/no-pii-in-output"
  resource_quotas:
    max_agents: 50
    max_crews: 20
    max_concurrent_executions: 10
```

**Design notes:**
- Every resource belongs to exactly one namespace. The `default` namespace is implicit if not specified.
- Namespace defaults (`defaults.agent_policy`, `defaults.sandbox_tier`, `defaults.guardrails`) are inherited by all resources in the namespace unless overridden at the resource level.
- Namespace quotas are enforced at resource creation time.
- Namespace-scoped RoleBindings (PRD 03) use `scope.namespace` to target a specific namespace.

### 2.11 ServiceAccount

A machine identity for CI/CD pipelines, scheduled automations, and A2A protocol interactions.

```yaml
# service-accounts/automation-runner.yaml
apiVersion: blackbeard/v1
kind: ServiceAccount
metadata:
  name: automation-runner
  labels:
    purpose: scheduled-execution
spec:
  description: "Identity for scheduled and triggered automation executions"
  api_keys:
    - name: primary
      expires_at: "2027-01-01T00:00:00Z"   # optional, null = no expiry
  permissions:
    inherit_from: "ref:users/admin@example.com"   # optional; @ in name is post-MVP / illustrative
```

**Design notes:**
- ServiceAccounts are subjects in RBAC (PRD 03, section 2.1) — they can be bound to Roles via RoleBindings.
- Each Automation references a ServiceAccount via `spec.service_account` (PRD 09). When a scheduled trigger fires, the ServiceAccount is the initiating principal in the execution's principal chain.
- API keys associated with ServiceAccounts are stored encrypted. For MVP, encryption uses `BLACKBEARD_API_KEY` as the key derivation input. Post-MVP, keys are stored in Infisical.
- ServiceAccounts are namespace-scoped like all other resources.

## 3. Reference Syntax

Resources reference each other using `ref:` syntax. This is the canonical specification for all reference forms.

### 3.1 Reference Forms

| Form | Syntax | Example | Used For |
|------|--------|---------|----------|
| **Local ref** | `ref:<kind-plural>/<name>` | `ref:agents/researcher` | Same-namespace reference |
| **Cross-namespace** | `ref:<namespace>/<kind-plural>/<name>` | `ref:production/agents/researcher` | Explicit namespace |
| **Repository** | `ref:repo:<kind-plural>/<name>@<version>` | `ref:repo:agents/market-researcher@2.0.0` | Asset from repository (PRD 10) |
| **Label selector** | `"<kind-plural>/label:<key>=<value>"` | `"tools/label:category=search"` | Match by label (quoted string, not a ref) |

**Canonical string:** No space after `ref:`. The runtime parser expects a single string (see `refs.py` in the backend).

### 3.2 Syntax Rules

1. Every cross-resource pointer uses the **`ref:<kind-plural>/<name>`** form (quoted in YAML), e.g. `- "ref:tools/serper-search"` or `agent: "ref:agents/researcher"`.
2. Do not split `ref` into a separate YAML mapping key for resource pointers — the stored value must be the full `ref:…` string so validation and loading match the JSON Schema (`items: { "type": "string" }` for `tools`, `agents`, etc.).
3. Label selectors are **quoted strings**, not refs. They are resolved at runtime, not at validation time.
4. Repository refs require explicit version pinning for v1 (`@2.0.0`). `@latest` resolves to a specific version at install time.
5. Cross-namespace refs require the referencing subject to have `get` permission on the target namespace.

### 3.3 Resolution

References are resolved via topological sort with cycle detection (section 4). Resolution order:
1. Parse the ref string → extract kind, name, optional namespace
2. Look up in `resource_refs` table
3. If cross-namespace, verify RBAC permission
4. If repository ref, check local install first, then repository
5. If label selector, query `resources` table with label filter

## 4. Reference Resolution

All `ref:` values are resolved at load time by the **Resource Loader**:

1. Parse YAML into typed resource objects.
2. Build a dependency graph of `ref:` edges.
3. Detect cycles (error) and missing refs (error with helpful message).
4. Topologically sort for load order.
5. Inject resolved objects into the runtime model.

### Deletion with active references

When a resource is deleted, the system checks for inbound references:

- **Block by default**: If other resources reference the target, deletion returns a `409 Conflict` with a list of dependents. The user must update or delete dependents first.
- **Force delete**: `DELETE /api/v1/agents/{name}?force=true` (replace `agents` with any resource kind in lowercase plural) deletes the resource and marks all inbound references as **broken**. Broken references are tracked via the `status` column in `resource_refs` (set to `broken` on force-delete of the target resource). Broken refs are surfaced in `blackbeard validate` and in the Studio UI as warning badges.
- **Cascade delete**: Not supported in v1 to prevent accidental data loss.

### Namespace-scoped resolution

References are resolved within the **current namespace** by default:

- `ref:agents/researcher` resolves to `agents/researcher` in the same namespace as the referencing resource.
- `ref:production/agents/researcher` explicitly targets the `production` namespace.
- `ref:repo:agents/researcher@1.0.0` resolves from the asset repository (PRD 10), which is namespace-independent.

If a reference is ambiguous (resource exists in multiple namespaces), the resolver returns an error requiring an explicit namespace prefix.

## 5. Versioning & Schema Evolution

- Each resource has `apiVersion: blackbeard/v1`.
- Breaking changes → new apiVersion (`blackbeard/v2`).
- The loader supports multiple apiVersions simultaneously and applies schema migrations. When a resource at `blackbeard/v1` is loaded alongside resources at `blackbeard/v2`, the loader applies schema migrations to normalize all resources to the latest version before building the runtime graph.
- Resources are stored in the database with their raw YAML plus a normalised relational projection for queries.

## 6. Validation

- JSON Schema derived from each resource kind's spec.
- Pre-save validation in the API layer.
- CLI command: `blackbeard validate ./path/to/resources/` for offline checking.
- Python callback paths are validated as importable at deployment time, not at definition time.

## 7. Database Schema (Relational Projection)

**Schema management (MVP):** Tables are created via `Base.metadata.create_all()` in the entrypoint script. This only creates new tables -- it cannot alter existing tables. Schema changes during MVP require dropping and recreating the database. Post-MVP will introduce a proper migration system.

```
resources
  id            UUID PK
  kind          VARCHAR(64)    -- Agent, Task, Crew, Flow, Tool, ...
  api_version   VARCHAR(32)
  name          VARCHAR(255)
  namespace     VARCHAR(255)   -- org or project scope
  labels        JSONB
  spec          JSONB          -- full spec, queryable
  raw_yaml      TEXT           -- original source
  created_at    TIMESTAMPTZ
  updated_at    TIMESTAMPTZ
  created_by    UUID FK → users
  version       INTEGER        -- optimistic locking

resource_refs
  id            UUID PK
  source_id     UUID FK → resources
  target_kind   VARCHAR(64)
  target_namespace VARCHAR(255)
  target_name   VARCHAR(255)
  ref_field     VARCHAR(255)   -- e.g. "spec.agent"
  status        VARCHAR(16) DEFAULT 'active'  -- active | broken

Constraints:
  UNIQUE(kind, name, namespace)

Indexes:
  idx_resources_kind          ON resources(kind)
  idx_resources_namespace     ON resources(namespace)
  idx_resources_labels        ON resources USING GIN(labels)
  idx_resources_kind_ns       ON resources(kind, namespace)
  idx_refs_source             ON resource_refs(source_id)
  idx_refs_target             ON resource_refs(target_kind, target_name)
```

**Query performance**: The single-table design scales to ~100K resources without materialized views. The `resource_refs` table handles cross-reference queries (e.g., "find all agents that reference tool X") efficiently via indexed joins. For JSONB spec queries (e.g., filtering by `spec.llm`), use GIN indexes on frequently-queried paths. If a specific resource kind exceeds 10K rows and JSONB queries become slow, add kind-specific partial indexes: `CREATE INDEX idx_agents_llm ON resources((spec->>'llm')) WHERE kind = 'Agent'`.

**Scalability note:** The single `resources` table works well for small-to-medium deployments (< 10,000 resources). For larger deployments, consider kind-specific materialized views or composite indexes on `(kind, namespace, name)` for frequently-queried kinds. The `resource_refs` table is the primary mechanism for cross-reference queries and should be indexed on both `(source_id)` and `(target_kind, target_name)`.

## 8. API Surface

```
GET    /api/v1/agents                     # list resources of a kind
GET    /api/v1/agents/{name}              # get one resource
POST   /api/v1/agents                     # create (accepts YAML or JSON body)
PUT    /api/v1/agents/{name}              # replace
PATCH  /api/v1/agents/{name}              # partial update
DELETE /api/v1/agents/{name}              # delete
POST   /api/v1/agents/{name}/validate     # dry-run validation
GET    /api/v1/agents/{name}/refs         # list inbound/outbound references
```

Replace `agents` with any resource kind in lowercase plural form: `tasks`, `crews`, `flows`, `tools`, `llm-connections`, `knowledge-sources`, `environment-variables`, `roles`, `role-bindings`, `agent-policies`, etc.

**Convention**: All API paths use lowercase plural kind names: `/api/v1/agents/{name}`, `/api/v1/tasks/{name}`, `/api/v1/crews/{name}`, etc.

Namespace-scoped variant:
```
GET    /api/v1/namespaces/{ns}/agents              # list resources in namespace
GET    /api/v1/namespaces/{ns}/agents/{name}        # get resource in namespace
```

The unscoped URLs default to the user's active namespace.

All endpoints honour RBAC (PRD 03).

## 9. Events Emitted

| Event | Payload |
|-------|---------|
| `resource.created` | `{kind, name, spec}` |
| `resource.updated` | `{kind, name, diff}` |
| `resource.deleted` | `{kind, name}` |
| `resource.validation_failed` | `{kind, name, errors}` |

## 10. Non-Goals (v1)

- Multi-tenancy with full org hierarchy (single org for v1; multi-org deferred). Namespaces exist within the org for logical separation.
- Git-based GitOps sync (planned for v2, not required for v1 launch).
- Automatic Python code generation from YAML (YAML references code, never generates it).

## 11. Acceptance Criteria

1. All workload resource kinds defined in this PRD (sections 2.1–2.8) can be created via YAML file upload and API. Other resource kinds (section 2.9) are validated and created by their respective modules.
2. `ref:` cross-references resolve correctly; cycles produce a clear error.
3. Resources are persisted in PostgreSQL and queryable by kind, name, label.
4. `blackbeard validate` CLI passes on valid resources and fails with actionable errors on invalid ones.
5. Every mutation emits the correct event on the internal bus.
6. Python callback paths in `callbacks.*` are syntax-validated (dotted name with colon) at save time.
