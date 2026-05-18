# PRD 03 — RBAC & Identity

## 1. Purpose

Implement a Kubernetes-inspired Role-Based Access Control system for Blackbeard that governs **two distinct subject classes**:

1. **Human users** — people who build, deploy, and manage agents through the UI/API/CLI.
2. **Agents** — autonomous software entities that, at runtime, access tools, data, LLMs, other agents, the filesystem, and the network.

Both classes use the same primitives — Objects, Verbs, Roles, RoleBindings, Rules — but agents get an additional **AgentPolicy** resource that constrains what they can do inside the execution sandbox (PRD 05). This separation matters because a human "developer" might be allowed to *create* a web-scraping tool, but the agent they build should not be allowed to *invoke* it against internal URLs.

---

## 1.1 MVP Scope

**MVP implements:** Built-in email/password auth with JWT tokens (access 15min + refresh 7d), User and Group models, Role and RoleBinding resource kinds, predefined roles (owner/admin/developer/operator/viewer/policy-admin + agent-unrestricted/agent-standard/agent-read-only), authorization enforcement middleware (RBAC checks on API endpoints), AgentPolicy resource kind (tool allowlist/denylist + LLM budget limits), sandbox tier selection (none/wasm), and a visual RBAC editor in the UI (Roles tab, Users/Groups tab, AgentPolicy editor). Agents run as ServiceAccounts (configured via `spec.serviceAccount`, defaulting to `sa-<agent-name>`). Tools invoked by an agent execute under that agent's ServiceAccount context. Each execution records the principal chain: User (who kicked off) → Crew → Agent (ServiceAccount). CLI supports `login`/`logout`/`whoami` with credential storage in `~/.config/blackbeard/`.

**MVP does NOT implement (planned but not yet built):** Principal chain intersection (effective permissions = user role ∩ agent role), delegation constraints, network/filesystem/code-execution policy enforcement, audit logging, token budget hard enforcement (tracked advisorily only), predefined agent policy auto-seeding.

**Deferred to post-MVP:** SSO/OIDC integration (Ory Kratos/Hydra), SpiceDB for relationship-based access control, OPA for policy-as-code, entity-level fine-grained permissions (`metadata.access`), multi-organization support, ServiceAccount as a standalone resource kind.

---

## 2. RBAC Primitives

### 2.1 Subject Kinds

| Kind | Description | Identity Source |
|------|-------------|-----------------|
| `User` | A human operator | JWT / SSO / API key |
| `Group` | A set of users | Membership table / OIDC group claim |
| `ServiceAccount` | Machine identity for CI/CD, A2A | API key / mTLS cert |
| `Agent` | A running agent instance | Resolved from agent resource name at execution time |
| `Crew` | All agents within a crew | Resolved from crew resource at execution time |

Agents and Crews are subjects just like Users. Every authorization check carries a **principal chain**: `User (who kicked off) → Crew → Agent` — any link in the chain can be denied.

### 2.2 Objects (API Resources)

Every entity in the system is an **Object** with a `kind` and optional `name`:

| Object Kind | Examples | Accessible by Agents? |
|-------------|----------|-----------------------|
| `Agent` | `agents/researcher`, `agents/*` | Yes (delegation) |
| `Task` | `tasks/research-ai` | Yes (execution) |
| `Crew` | `crews/research-crew` | Yes (sub-crew invocation) |
| `Flow` | `flows/content-pipeline` | Yes (flow step) |
| `Tool` | `tools/serper-search` | **Yes — primary agent concern** |
| `LLMConnection` | `llm-connections/openai-prod` | **Yes — which models an agent may call** |
| `KnowledgeSource` | `knowledge/company-docs` | **Yes — which data an agent may read** |
| `EnvironmentVariable` | `env-vars/serper-api-key` | Yes (injected at runtime) |
| `Automation` | `automations/prod-deploy-001` | No (human only) |
| `Trace` | `traces/*` | No (human only) |
| `Role` | `roles/developer` | No |
| `RoleBinding` | `role-bindings/alice-developer` | No |
| `AgentPolicy` | `agent-policies/restricted` | No (governs agents, not used by them) |
| `Sandbox` | `sandboxes/high-isolation` | No (assigned to agents, not used by them) |
| `User` | `users/alice@example.com` | No |
| `Organization` | `organizations/acme-corp` | No |
| `Namespace` | `namespaces/production` | No |

### 2.3 Verbs

| Verb | Description | Human | Agent |
|------|-------------|-------|-------|
| `get` | Read a single resource | ✓ | ✓ |
| `list` | List resources of a kind | ✓ | ✓ |
| `create` | Create a new resource | ✓ | — |
| `update` | Modify an existing resource | ✓ | — |
| `delete` | Remove a resource | ✓ | — |
| `run` | Execute (kick off a crew/flow/automation) | ✓ | ✓ (sub-crew) |
| `invoke` | Call a tool or LLM | — | **✓** |
| `delegate` | Hand work to another agent | — | **✓** |
| `read-data` | Read from a knowledge source | — | **✓** |
| `write-data` | Write to filesystem / external store | — | **✓** |
| `manage` | Full lifecycle (create+update+delete) | ✓ | — |
| `approve` | Respond to HITL requests | ✓ | — |
| `deploy` | Deploy an automation | ✓ | — |
| `rollback` | Rollback an automation | ✓ | — |
| `export` | Download / export a resource | ✓ | — |
| `import` | Upload / import a resource | ✓ | — |
| `bind` | Create role bindings | ✓ | — |

Note the agent-specific verbs: `invoke`, `delegate`, `read-data`, `write-data`. These are enforced by the Execution Engine (PRD 05) at every tool call, LLM dispatch, delegation attempt, and file write.

### 2.4 Rule

A single permission statement: "allow these verbs on these objects".

```yaml
apiVersion: blackbeard/v1
kind: Rule
spec:
  resources: ["agents", "tasks", "crews", "tools"]
  verbs: ["get", "list", "create", "update", "delete"]
  resourceNames: []                   # empty = all names
  namespaces: ["*"]                   # which namespaces this applies to
  conditions: []                      # optional: label selectors, field matchers
```

**Standalone vs. embedded**: Rules are always embedded within Roles — they are not independently addressable resources. The `Rule` entry in the resource catalogue (PRD 01, section 2.9) indicates that Rules follow the same schema validation, but they do not have their own CRUD endpoints or database rows. Rules are created, updated, and deleted as part of their parent Role resource. The `kind: Rule` in the YAML above is for schema documentation; in practice, rules appear as entries in `spec.rules` arrays within Role resources.

### 2.5 Role

A named collection of Rules. Works for both human and agent subjects.

```yaml
# roles/developer.yaml
apiVersion: blackbeard/v1
kind: Role
metadata:
  name: developer
  description: "Build and deploy agents, crews, and tools"
spec:
  subjectKinds: [User, Group]         # which subject kinds can be bound to this role
  rules:
    - resources: ["agents", "tasks", "crews", "flows", "tools", "knowledge-sources"]
      verbs: ["get", "list", "create", "update", "delete"]
    - resources: ["automations"]
      verbs: ["get", "list", "run", "deploy", "rollback"]
    - resources: ["traces"]
      verbs: ["get", "list"]
    - resources: ["llm-connections", "environment-variables"]
      verbs: ["get", "list", "create", "update"]
    - resources: ["roles", "role-bindings", "users", "organizations"]
      verbs: ["get", "list"]
```

### 2.6 RoleBinding

Associates a Role with any subject kind within a scope.

```yaml
# role-bindings/alice-developer.yaml
apiVersion: blackbeard/v1
kind: RoleBinding
metadata:
  name: alice-developer
spec:
  role: ref:roles/developer
  subjects:
    - kind: User
      name: alice@example.com
    - kind: Group
      name: engineering
  scope:
    namespace: production
```

```yaml
# role-bindings/researcher-agent-standard.yaml
apiVersion: blackbeard/v1
kind: RoleBinding
metadata:
  name: researcher-agent-standard
spec:
  role: ref:roles/agent-standard
  subjects:
    - kind: Agent
      name: agents/researcher
    - kind: Crew
      name: crews/research-crew       # all agents in this crew get this role
  scope:
    namespace: production
```

---

## 3. Agent Policies (Runtime Constraints)

An **AgentPolicy** is a resource that defines what an agent is allowed to do at runtime. It goes beyond the Role/RoleBinding model to add runtime-specific constraints: network access, filesystem scope, resource limits, and delegation topology.

```yaml
# agent-policies/restricted.yaml
apiVersion: blackbeard/v1
kind: AgentPolicy
metadata:
  name: restricted
  description: "Locked-down policy for agents handling sensitive data"
spec:
  # ── Tool access ──────────────────────────────────────────
  tools:
    mode: allowlist                    # allowlist | denylist | unrestricted
    allow:
      - ref: tools/serper-search
      - ref: tools/wikipedia
      - "tools/label:category=search"  # label selector: any tool with category=search
    deny: []
    max_invocations_per_task: 20       # prevent infinite tool loops
    max_invocations_per_execution: 100

  # ── LLM access ───────────────────────────────────────────
  llm:
    mode: allowlist
    allow:
      - ref: llm-connections/openai-prod
      - ref: llm-connections/anthropic-prod
    deny:
      - ref: llm-connections/expensive-o1  # never let this agent use o1
    max_tokens_per_task: 50000
    max_tokens_per_execution: 200000
    max_cost_per_execution_usd: 5.00   # hard cost ceiling

  # ── Delegation ───────────────────────────────────────────
  delegation:
    allowed: true
    allowed_targets:
      - ref: agents/analyst            # can only delegate to these agents
      - ref: agents/writer
    denied_targets:
      - ref: agents/admin-bot          # never delegate to admin-bot
    max_depth: 2                       # delegation chain depth limit

  # ── Knowledge / data access ──────────────────────────────
  data:
    knowledge_sources:
      mode: allowlist
      allow:
        - ref: knowledge/public-docs
      deny:
        - ref: knowledge/hr-records
    filesystem:
      read_paths:
        - "./data/public/**"
        - "./outputs/**"
      write_paths:
        - "./outputs/{execution_id}/**"
      denied_paths:
        - "/etc/**"
        - "~/**"
        - "../../**"                   # no path traversal
    environment_variables:
      expose:
        - SERPER_API_KEY
        - OPENAI_API_KEY
      deny:
        - DATABASE_URL
        - AWS_SECRET_ACCESS_KEY

  # ── Network ─────────────────────────────────────────────
  network:
    outbound:
      mode: allowlist                  # allowlist | denylist | unrestricted | none
      allow:
        - "*.google.com"
        - "api.openai.com"
        - "api.anthropic.com"
        - "serper.dev"
      deny:
        - "*.internal.company.com"     # never access internal services
        - "169.254.169.254"            # block cloud metadata endpoint
        - "10.0.0.0/8"                 # block private networks
    inbound:
      mode: none                       # agents don't accept inbound connections

**Wildcard matching semantics:** Network allow/deny patterns use suffix matching with these rules:
- `*.example.com` matches `sub.example.com` and `deep.sub.example.com` (all subdomains)
- `example.com` matches exactly `example.com` (no subdomains)
- Port is required when specified: `*.google.com:443` matches only HTTPS
- Without port: `*.google.com` matches all ports
- CIDR notation is supported for IP ranges: `10.0.0.0/8`
- The metadata endpoint `169.254.169.254` is always denied regardless of policy (hardcoded safety)

  # ── Sandbox ─────────────────────────────────────────────
  sandbox:
    minimum_tier: wasm                 # none | wasm | docker | microvm
                                       # floor: no tool may run below this tier
                                       # "none" = non-sandboxed allowed (for trusted tools)
    default_tier: wasm                 # tier used when a tool doesn't specify one
    remote_tools_bypass_floor: true    # default: true. Remote tools (mcp-http, rest) skip minimum_tier check
    profile: ref:sandboxes/standard    # default sandbox profile for resource limits/network

When `remote_tools_bypass_floor` is `true` (default), remote tools (types `mcp-http` and `rest`) that make outbound HTTP calls without executing local code bypass the `minimum_tier` floor. Set to `false` if your compliance posture requires all tool invocations, including remote API calls, to run inside a sandbox.

  # ── Code execution ──────────────────────────────────────
  code_execution:
    allowed: false                     # can this agent execute arbitrary code?
    sandbox_profile: ref:sandboxes/high-isolation   # if allowed, which sandbox profile?
    allowed_languages: ["python"]
    max_execution_time: 30             # seconds per code block
    max_memory_mb: 512

  # ── Resource limits ─────────────────────────────────────
  resource_limits:
    max_execution_time: 600            # total execution time for the agent, seconds
    max_memory_mb: 1024
    max_cpu_cores: 2
    max_concurrent_tool_calls: 3
```

### 3.1 Policy Binding

Policies are bound to agents in three ways (highest priority wins):

```yaml
# 1. Directly on the Agent resource
# agents/researcher.yaml
spec:
  policy: ref:agent-policies/restricted

# 2. On a Crew (applies to all agents in that crew)
# crews/research-crew.yaml
spec:
  default_agent_policy: ref:agent-policies/standard

# 3. On a Namespace (applies to all agents in that namespace unless overridden)
# namespaces/production.yaml
spec:
  default_agent_policy: ref:agent-policies/production-baseline
```

**Resolution order**: Agent-level > Crew-level > Namespace-level > Organization default.

### 3.2 Predefined Agent Policies

| Policy | Minimum Sandbox Tier | Description |
|--------|---------------------|-------------|
| `unrestricted` | `none` | No constraints. Non-sandboxed tools allowed. All LLMs, delegation, network. For trusted internal deployments or development. |
| `standard` | `none` | All registered tools, all LLMs, no code execution, no private network access. Trusted first-party tools may run non-sandboxed; third-party defaults to WASM. |
| `sandboxed` | `wasm` | All tool execution goes through WASM minimum. No non-sandboxed tools. All LLMs, limited delegation. |
| `restricted` | `wasm` | Allowlisted tools/LLMs only, limited tokens/cost, no code execution. |
| `hardened` | `docker` | All tools run in Docker (gVisor). Strict network allowlist, restricted filesystem, no delegation. |
| `air-gapped` | `docker` | No outbound network, no code execution, read-only filesystem — LLM-only reasoning. |

### 3.3 Tool Visibility via RBAC

When using JIT tool discovery (PRD 04 §10), the agent's `search_tools` meta-tool filters results against its AgentPolicy. Denied tools are invisible — the agent cannot discover, inspect, or call them. This is enforced at the API level, not client-side.

| Policy Mode | `search_tools` returns | `get_tool` allows |
|-------------|----------------------|-------------------|
| `tools.mode: unrestricted` | All tools in namespace | Any tool |
| `tools.mode: allowlist` | Only `tools.allow[]` entries | Only allowed tools |
| `tools.mode: denylist` | All except `tools.deny[]` | All except denied tools |

### 3.4 Policy Enforcement Points

The Execution Engine (PRD 05) enforces policies at these points:

| Enforcement Point | Check |
|-------------------|-------|
| **Sandbox tier** | Is the tool's effective tier ≥ `sandbox.minimum_tier`? If tool requests `none` but policy floor is `wasm`, promote to `wasm`. |
| **Tool dispatch** | Is this tool in the agent's allow list? Invocation count < limit? |
| **LLM call** | Is this LLM connection allowed? Token budget remaining? Cost < ceiling? |
| **Delegation** | Is the target agent in `delegation.allowed_targets`? Depth < limit? |
| **Knowledge query** | Is this knowledge source in `data.knowledge_sources.allow`? |
| **File read** | Does the path match `data.filesystem.read_paths`? Not in `denied_paths`? (Enforced by sandbox mounts for wasm/docker/microvm; advisory for `none`.) |
| **File write** | Does the path match `data.filesystem.write_paths`? (Same enforcement as reads.) |
| **Network call** | Does the destination match `network.outbound.allow`? (Enforced by WASI capability grants for wasm; iptables for docker/microvm; advisory for `none`.) |
| **Code execution** | Is `code_execution.allowed: true`? Is the sandbox profile provisioned? |
| **Env var access** | Is this env var in `environment_variables.expose`? (Enforced by env filtering at sandbox creation.) |
| **Resource usage** | CPU / memory / time within `resource_limits`? (Enforced by fuel metering for wasm; cgroups for docker; hypervisor for microvm; timeouts-only for `none`.) |

Every denial emits an `agent.policy.denied` event with full context for audit.

---

## 4. Human RBAC — Predefined Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| `owner` | Full access to everything | `*` verbs on `*` resources |
| `admin` | Manage platform settings, users, roles | All except billing/org deletion |
| `developer` | Build and deploy agents/crews | CRUD on agents, tasks, crews, tools; run/deploy automations |
| `operator` | Manage infrastructure and deployments | Deploy, rollback, manage LLM connections, env vars |
| `viewer` | Read-only access | `get`, `list` on most resources |
| `hitl-responder` | Respond to HITL requests only | `approve` on automations, `get`/`list` on executions, `get` on traces |
| `policy-admin` | Manage agent policies and sandboxes | CRUD on AgentPolicy, Sandbox; read on agents |

## 5. Predefined Agent Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| `agent-unrestricted` | Full runtime access (dev only) | `invoke` all tools, `delegate` to any agent, `read-data` all |
| `agent-standard` | Normal production agent | `invoke` registered tools, `delegate` if allowed, `read-data` allowed sources |
| `agent-read-only` | Reasoning-only, no side effects | `get`, `list`, `read-data` only — no `invoke`, no `write-data`, no `delegate` |

---

## 6. Entity-Level Permissions (Fine-Grained)

Beyond role-level access, individual resources can have **visibility settings**:

```yaml
metadata:
  name: sensitive-crew
  access:
    visibility: private               # public | private | restricted
    allowedSubjects:
      - kind: User
        name: alice@example.com
      - kind: Agent
        name: agents/trusted-analyst   # an agent can be given access to a specific crew
      - kind: Role
        ref: roles/developer
    permissions:
      - subject: alice@example.com
        verbs: [run, manage]
      - subject: ref:roles/viewer
        verbs: [get]
```

**Storage**: Entity-level access controls are stored in `metadata.access` (not `spec`). This means access controls are NOT version-controlled with the resource spec. They are administrative metadata managed separately from the resource's functional definition. In the database, `metadata` fields (name, namespace, labels, access) are stored in dedicated columns. The `access` field is stored as a JSONB column on the `resources` table, separate from the `spec` JSONB column. When a resource spec is updated (creating a new version), the `metadata.access` block is carried forward unchanged unless explicitly modified.

Two-layer evaluation:
1. **Role-level**: "Does this subject's role allow `{verb}` on `{resource kind}`?"
2. **Entity-level**: "Is this specific resource visible to this subject, and what verbs are allowed?"

Both must pass. For agents, an additional third layer is checked:
3. **Policy-level**: "Does the agent's AgentPolicy allow this action?"

---

## 7. Authorization Flow

```
Action requested (by human OR agent)
    │
    ▼
┌──────────────────────┐
│  1. Identify Subject │  Human: JWT/API key/mTLS → User
│                      │  Agent: execution context → Agent resource name
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│  2. Resolve Roles    │  Subject → RoleBindings → Roles → Rules
│     & Policies       │  Agent → AgentPolicy (from agent/crew/namespace)
└────────┬─────────────┘
         │
         ▼
┌──────────────────────────┐
│  3. Role-Level Check     │  Does any rule grant {verb} on {resource kind}?
│     (RBAC Rules)         │
└────────┬─────────────────┘
         │ DENY → 403 / policy violation event
         │ ALLOW ▼
┌──────────────────────────┐
│  4. Entity-Level Check   │  If resource has `access` metadata:
│     (Visibility)         │    Is subject in allowedSubjects?
└────────┬─────────────────┘
         │ DENY → 403
         │ ALLOW ▼
┌──────────────────────────┐
│  5. Policy Check         │  AGENTS ONLY: Does AgentPolicy allow this?
│     (AgentPolicy)        │    Tool in allowlist? Token budget? Network OK?
└────────┬─────────────────┘
         │ DENY → policy violation event, agent receives denial message
         │ ALLOW ▼
┌──────────────────┐
│  6. Admit        │  Execute the operation (in sandbox if required)
└──────────────────┘
```

**Performance**: Steps 2-5 are cached with a 30-second TTL, keyed by `(subject_kind, subject_name, namespace)`. The full authorization flow runs in <5ms for cached principals. Cache is invalidated proactively on role/policy/binding changes via the internal event bus, but in multi-worker deployments, propagation takes up to 2 seconds. This means a revoked user could remain authorized for up to 30 seconds on a worker that hasn't received the invalidation event.

**Cache configuration:** Default cache TTL is 30 seconds. For security-critical deployments, set `AUTHZ_CACHE_TTL=0` to disable caching (every request checks the database). In multi-worker deployments, cache invalidation propagates via the event bus with a worst-case consistency window equal to the cache TTL. When `AUTHZ_CACHE_TTL=0`, every request queries the database directly. The event bus propagation delay is irrelevant in this mode since no cache exists to invalidate. Prefer configuring via `PlatformConfig.spec.auth.cache_ttl_seconds` (PRD 11) over the env var.

For agents, policy denials are NOT silent 403s — they feed back into the agent's conversation as a system message: `"Policy violation: you are not allowed to invoke tool 'database-admin'. Available tools: [serper-search, wikipedia]."` This lets the agent adapt its approach rather than crash.

---

## 8. Identity Providers

### 8.1 Built-in Auth (MVP / Minimal Profile)

*Built-in auth is the MVP and `--profile minimal` authentication method. Post-MVP, authentication is delegated to Ory Kratos/Hydra (PRD 00-integrations). Built-in auth remains available as a simpler fallback for deployments that don't need SSO or advanced identity management.*

- Email + password with bcrypt.
- JWT access tokens (15 min) + refresh tokens (7 days).
- API keys for machine-to-machine (automations, CI/CD).

### 8.2 SSO / OIDC

```yaml
apiVersion: blackbeard/v1
kind: SSOConfig
metadata:
  name: okta-prod
spec:
  provider: oidc
  issuer: "https://acme.okta.com/oauth2/default"
  client_id_env: OKTA_CLIENT_ID
  client_secret_env: OKTA_CLIENT_SECRET
  scopes: ["openid", "profile", "email", "groups"]
  group_claim: "groups"
  group_mapping:
    "okta-engineering": "engineering"
    "okta-admins": "platform-admins"
  auto_provision: true
  default_role: ref:roles/viewer
```

### 8.3 mTLS
For service-to-service (A2A) communication. Certificate CN maps to a service identity.

### 8.4 API Keys

```yaml
apiVersion: blackbeard/v1
kind: APIKey
metadata:
  name: ci-deploy-key
spec:
  subject:
    kind: ServiceAccount
    name: ci-bot@acme.com
  scopes:
    - resources: ["automations"]
      verbs: ["deploy", "rollback"]
  expires_at: "2026-12-31T23:59:59Z"
  rate_limit:
    requests_per_minute: 60
```

### 8.5 Agent Identity

Agents don't authenticate in the traditional sense. Their identity is derived from the execution context:

```
Execution record
  ├── kicked_off_by: User "alice@example.com"
  ├── automation: "automations/prod-deploy-001"
  ├── crew: "crews/research-crew"
  └── current_agent: "agents/researcher"
       ├── role_bindings: [agent-standard]
       └── policy: agent-policies/restricted
```

The **principal chain** is carried through the entire execution. If Alice kicks off a crew, every agent in that crew acts under Alice's user permissions INTERSECTED with the agent's own policy. This means:
- Alice must have `run` permission on the automation.
- The agent must have `invoke` permission on each tool it tries to use.
- If Alice doesn't have access to a knowledge source, the agent running on her behalf can't access it either (even if the agent policy allows it).

**Principal chain intersection algorithm:**

The effective permission set for an agent action is computed as:

1. **User permissions**: Resolve the kicking user's roles → collect allowed `(verb, resource)` pairs.
2. **Agent role permissions**: Resolve the agent's role bindings → collect allowed `(verb, resource)` pairs.
3. **Intersection**: The agent may only perform actions that appear in **both** the user's and the agent's permission sets.
4. **AgentPolicy overlay**: After intersection, apply the agent's AgentPolicy constraints (tool allowlists, LLM budgets, network rules). Policy constraints are **additional restrictions**, never expansions.
5. **Entity-level check**: Finally, check entity-level visibility on the specific resource being accessed.

In practice, for most deployments the user has broad permissions and the agent's policy is the binding constraint. The intersection matters primarily when a restricted user kicks off a crew containing a broadly-permissioned agent.

**Scheduled and triggered executions**: When an automation runs on a cron schedule, webhook trigger, or other non-human trigger, there is no human user in the principal chain. In this case:

1. The automation's configured `ServiceAccount` is used as the principal (see PRD 09, `spec.runtime.service_account`).
2. If no ServiceAccount is configured, the automation uses the **deploying user's** identity — the user who last deployed the automation. This means the automation inherits the deployer's permissions.
3. The principal chain becomes: `ServiceAccount (or deploying user) → Crew → Agent`.
4. AgentPolicy constraints still apply in full — the ServiceAccount identity only affects the RBAC layer (steps 1-4), not the policy layer (step 5).

```yaml
# Example: ServiceAccount for a scheduled automation
apiVersion: blackbeard/v1
kind: ServiceAccount
metadata:
  name: cron-runner
spec:
  roles:
    - ref: roles/operator
  description: "Identity used for scheduled automation executions"
```

This ensures scheduled executions have a well-defined, auditable identity rather than running with ambient permissions.

---

## 9. GUI RBAC Editor (MVP)

### 9.1 Roles Tab (Human Roles)
- **Table view**: All roles (built-in + custom) with rule count, bound users, description.
- **Create Role**: Rule Builder form — select resources (multi-select chips), verbs (checkboxes), optional resource names, optional namespace.
- **YAML Preview**: Side panel shows live YAML as the form is edited.
- **Impact Preview**: Before saving, show "N users affected by this change".

### 9.2 Agent Policies Tab
- **Table view**: All policies with bound agent count, key constraints summary.
- **Create/Edit Policy**:
  - **Tools section**: Allowlist/denylist builder with tool search and label selectors.
  - **LLM section**: Select allowed LLM connections, set token/cost budgets.
  - **Delegation section**: Visual picker — show all agents, draw allowed delegation arrows.
  - **Data section**: File path pattern editor, knowledge source picker, env var selector.
  - **Network section**: Domain/CIDR allowlist editor with "Test URL" button.
  - **Code Execution section**: Toggle on/off, select sandbox profile, set limits.
  - **Resource Limits section**: Sliders for CPU, memory, time, concurrency.
- **Dry-Run Simulator**: "What would happen if agent X tried to call tool Y?" — instant pass/deny answer with the rule that matched.
- **YAML tab**: Full YAML editor with bidirectional sync.

### 9.3 Users & Groups Tab
- User list: Email, display name, assigned roles, last login, status.
- Invite user, assign roles, manage groups.

### 9.4 Subjects Overview
- Unified view of all subjects (Users, Groups, ServiceAccounts, Agents, Crews) with their bindings.
- Click an agent → see its effective permissions: human role (inherited from kicker) + agent role + agent policy, merged and resolved.

### 9.5 Role Bindings Tab
- Table: Subject (any kind) → Role → Scope.
- Create/bulk-create bindings.

### 9.6 Entity Permissions Tab
- Accessible from any resource's settings.
- Visibility toggle, subject whitelist with per-verb checkboxes.
- Works for both human and agent subjects.

### 9.7 Audit Log
- Every RBAC and policy change logged: who/what, when, old → new.
- Every policy denial logged: which agent, what action, which rule denied it.
- Filterable by subject kind, action type, resource, time range.
- Exportable as CSV/JSON.

---

## 10. YAML-Based RBAC Management (Post-MVP)

All RBAC resources (Role, RoleBinding, AgentPolicy, SSOConfig, APIKey, Sandbox) follow the same `apiVersion/kind/metadata/spec` pattern:

- Version-controlled in Git alongside agent/crew definitions.
- Applied via CLI: `blackbeard apply -f agent-policies/restricted.yaml`.
- Managed via API: `POST /api/v1/agent-policies`.
- Managed via GUI (section 9).

GitOps workflows for access control are first-class.

---

## 11. Namespace Scoping

| Scope | Meaning |
|-------|---------|
| **Organization** | Top-level tenant boundary |
| **Namespace** | Subdivision within org (e.g., `production`, `staging`, `team-alpha`) |
| **Resource** | Individual resource within a namespace |

Role bindings and agent policies specify their scope. A binding in namespace `production` applies only to that namespace. `namespace: "*"` is org-wide.

---

## 12. Events Emitted

| Event | Payload |
|-------|---------|
| `auth.login` | `{user, method, ip, timestamp}` |
| `auth.login_failed` | `{email, reason, ip}` |
| `rbac.role.created` | `{role_name, rules}` |
| `rbac.role.updated` | `{role_name, diff}` |
| `rbac.binding.created` | `{subject_kind, subject_name, role, scope}` |
| `rbac.binding.deleted` | `{subject_kind, subject_name, role, scope}` |
| `rbac.access.denied` | `{subject_kind, subject_name, verb, resource, reason}` |
| `agent.policy.created` | `{policy_name, spec_summary}` |
| `agent.policy.updated` | `{policy_name, diff}` |
| `agent.policy.denied` | `{agent, action, resource, policy_name, rule_matched, execution_id}` |
| `agent.policy.budget_warning` | `{agent, budget_type, used, limit, execution_id}` |
| `agent.policy.budget_exceeded` | `{agent, budget_type, limit, execution_id}` |

---

## 13. Migration Path: MVP to Multi-User

The MVP uses a single `BLACKBEARD_API_KEY` environment variable for all API authentication (no users, no sessions, no SSO). The migration to the full auth stack proceeds in phases:

| Phase | Auth Model | What Changes |
|-------|------------|--------------|
| **MVP** | Single API key in `X-API-Key` header | No user identity. All actions attributed to "system." |
| **v1.1: Built-in auth** | Email/password + JWT + API keys | User table added. Existing API key continues to work as a "legacy key" with `owner` role. RBAC roles/bindings created for new users. |
| **v1.2: Ory Kratos/Hydra** | SSO/OIDC + MFA + account recovery | Ory replaces built-in auth for human users. JWT tokens are now issued by Ory Hydra. API keys remain unchanged. `SSOConfig` resources become active. |
| **v1.3: SpiceDB** | Fine-grained entity permissions | SpiceDB replaces PostgreSQL-based entity visibility checks. Existing `metadata.access` blocks are migrated to SpiceDB relationships. |

**Backward compatibility**: Each phase preserves existing authentication methods. API keys created in MVP continue to work in all subsequent phases. The `BLACKBEARD_API_KEY` env var is deprecated in v1.1 but remains functional until v2.0.

---

## 14. Acceptance Criteria

### Human RBAC
1. K8s-style Role with multiple Rules can be created via YAML, API, and GUI.
2. RoleBinding associates a user/group with a role in a namespace scope.
3. A user with only `viewer` role cannot create, update, or delete any resource (403).
4. A user with `developer` role can create agents but cannot modify roles or invite users.
5. Entity-level `access.visibility: private` hides a resource from users not in the whitelist.
6. SSO login via OIDC works; OIDC groups map to Blackbeard groups and inherit role-bindings.
7. API keys with scoped permissions work for CI/CD deployment.

### Agent RBAC
8. An agent with policy `tools.mode: allowlist` cannot invoke a tool not in the allow list; the denial is fed back as a system message and the agent adapts.
9. An agent hitting `llm.max_tokens_per_execution` is stopped with a budget-exceeded error.
10. An agent with `delegation.allowed: true` can delegate to listed targets; delegation to unlisted targets is denied.
11. An agent with `network.outbound.mode: allowlist` cannot make HTTP calls to unlisted domains (enforced by sandbox — PRD 05).
12. An agent with `code_execution.allowed: false` cannot run arbitrary code even if the tool supports it.
13. Principal chain intersection works: if the kicking user lacks access to a knowledge source, the agent inherits that denial.

### GUI & Audit
14. GUI Policy Editor produces valid YAML matching the API-created policy.
15. Dry-Run Simulator correctly predicts pass/deny for agent+action+resource combinations.
16. Audit log records every policy denial with agent name, action, rule matched, and execution ID.
17. `blackbeard validate` accepts all RBAC and AgentPolicy YAML resources.
