# PRD 09 — Deployment & Automation

## 1. Purpose

Manage the full lifecycle of deployed crews and flows: build, deploy, version, rollback, trigger, and expose via external protocols (REST, webhooks, A2A). An **Automation** is a deployed instance of a Crew or Flow resource.

## 2. Automation Resource

```yaml
apiVersion: blackbeard/v1
kind: Automation
metadata:
  name: research-pipeline-prod
  labels:
    environment: production
spec:
  source:
    type: crew                        # crew | flow
    ref: crews/research-crew
  
  deployment:
    method: git                       # git | zip | studio | registry
    git:
      repository: "https://github.com/acme/research-crew"
      branch: main
      auto_deploy: true               # deploy on every push
    replicas: 2                       # concurrent execution capacity
    
  runtime:
    default_agent_policy: ref:agent-policies/standard
    default_sandbox: ref:sandboxes/standard
    environment_variables:
      - ref: env-vars/openai-key
      - ref: env-vars/serper-key
    llm_connections:
      - ref: llm-connections/openai-prod
  
  triggers:
    - type: api                       # always available
    - type: webhook
      config:
        secret_env: WEBHOOK_SECRET
    - type: schedule
      config:
        cron: "0 9 * * MON"          # every Monday at 9am
    # Slack, Gmail, and other app triggers available post-v1
        
  a2a:
    enabled: true
    auth: ref:auth/enterprise-token
    protocol_versions: ["0.2", "0.3"]
    transports: [json-rpc, grpc]
    
  versioning:
    strategy: rolling                 # rolling | blue-green | canary
    max_versions: 10                  # keep last N versions for rollback
    
  access:
    visibility: private
    allowedRoles: [ref:roles/developer, ref:roles/operator]
```

### 2.1 Automation Lifecycle

```
created → building → deploying → deployed → degraded → deleted
                │                    │           │
                └──→ build_failed    │           └──→ deployed (auto-recover)
                                     └──→ deploy_failed
```

| State | Description |
|-------|-------------|
| `created` | Automation resource saved but not yet built or deployed |
| `building` | Build pipeline running (validate, resolve deps, compile WASM, package) |
| `build_failed` | Build failed — error details in `status.error` |
| `deploying` | Deploying to runtime (registering API endpoints, scheduling triggers) |
| `deploy_failed` | Deployment failed — error details in `status.error` |
| `deployed` | Active and accepting executions |
| `degraded` | Deployed but health checks failing (e.g., LiteLLM unreachable, tool unavailable) |
| `deleted` | Soft-deleted — executions stopped, triggers unregistered |

The Automation resource is stored in the generic `resources` table (PRD 01, §6). Deployment-specific state is stored in a dedicated table:

```sql
automation_deployments
  id                UUID PK
  automation_name   VARCHAR(255)       -- FK to resources(name) where kind='Automation'
  namespace         VARCHAR(255)
  version           INTEGER            -- sequential deployment version
  status            VARCHAR(32)        -- lifecycle state
  error             TEXT               -- error details for failed states
  resource_snapshot JSONB              -- immutable snapshot of all resolved resources at deploy time
  artifact_url      TEXT               -- S3/MinIO URL of packaged artifact (if applicable)
  deployed_by       UUID FK → users
  deployed_at       TIMESTAMPTZ
  created_at        TIMESTAMPTZ

  UNIQUE(automation_name, namespace, version)

Indexes:
  idx_deploy_auto   ON automation_deployments(automation_name, namespace)
  idx_deploy_status ON automation_deployments(status)
```

## 3. Deployment Methods

| Method | Workflow |
|--------|----------|
| **Git** | Connect repo → auto-build on push → deploy. Supports branch-based environments. |
| **ZIP** | Upload packaged project → build → deploy. For quick iterations. |
| **Studio** | Build in visual editor → publish → deploy. No code required. |
| **Registry** | Pull from internal asset registry → deploy. For standardised, approved crews. |

## 4. Build Pipeline

```
Source (git/zip/studio)
    │
    ▼
┌────────────────────────┐
│  1. Validate           │  blackbeard validate on all YAML resources
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  2. Resolve deps       │  Install Python packages, pull WASM modules,
│                        │  verify tool availability
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  3. Compile WASM       │  Auto-compile Python tools → .wasm if sandbox tier requires it
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  4. Build image        │  Package into container image (for Docker/K8s deployment)
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  5. Test (optional)    │  Run integration tests if defined
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│  6. Deploy             │  Push to runtime, register API endpoints
└────────────────────────┘
```

### 4.1 Build Artifacts

| Deployment Method | Build Artifact | Storage |
|-------------------|---------------|---------|
| **Git / ZIP** | Resource bundle (validated YAML + compiled WASM tools + Python deps list) | MinIO: `s3://blackbeard-builds/{namespace}/{automation}/{version}/` |
| **Studio** | Same as above, generated from canvas state | Same |
| **Registry** | Pre-built bundle from asset repository | MinIO (already stored) |

**Resource snapshot**: At build time, all referenced resources (agents, tasks, tools, LLM connections, policies) are resolved and their current state is serialized into `resource_snapshot` (JSONB). This snapshot is immutable — the deployed version always uses these exact resource definitions, even if the source resources are later modified. This is what makes rollback instantaneous: restoring a previous version swaps the active snapshot pointer, not the resources.

**Python dependencies**: The build step generates a `requirements.txt` from all Python tool implementations and callback modules. Dependencies are installed into the worker's virtual environment. Workers use separate virtualenvs per automation to avoid dependency conflicts (post-MVP; MVP uses a shared environment).

## 5. Triggers

### v1 Triggers

| Trigger | Description |
|---------|-------------|
| **API** | `POST /api/v1/automations/{name}/kickoff` — always available |
| **Webhook** | Receive HTTP POST from external systems (Zapier, Make, custom) |
| **Schedule** | Cron-based recurring execution |
| **Custom** | Webhook receiver with a CEL (Common Expression Language) filter that decides whether to kick off |

**Custom trigger filter**: Custom triggers use a [CEL expression](https://cel.dev/) to evaluate the incoming webhook payload. The expression must return `true` to trigger execution.

```yaml
triggers:
  - type: custom
    config:
      secret_env: WEBHOOK_SECRET
      filter: 'body.action == "opened" && body.repository.name == "my-repo"'
      input_mapping:
        title: "body.pull_request.title"
        url: "body.pull_request.html_url"
```

### Roadmap Triggers (post-v1)

| Trigger | Description |
|---------|-------------|
| **Slack** | Slash command or message event |
| **Gmail** | New email with matching label/filter |
| **GitHub** | Issue created, PR merged, etc. |
| **Calendar** | Google Calendar / Outlook event created/updated |
| **HubSpot** | CRM record created/updated |
| **Salesforce** | Object trigger via Salesforce Flows |

## 6. Agent-to-Agent (A2A) Protocol

Deployed automations can expose A2A endpoints for inter-agent communication:

- **Agent Cards**: Auto-generated from crew/agent metadata at `/.well-known/agent-card.json`.
- **Per-agent endpoints**: `/a2a/agents/{role}/` for direct agent targeting.

**Note**: Per-agent endpoints extend CrewAI's standard A2A protocol (which operates at the crew level). These endpoints internally route to the specific agent within the crew, allowing external systems to target a specific agent's capabilities rather than the crew as a whole.
- **Authentication**: Configurable per-deployment (bearer, OIDC, OAuth2, API key, mTLS).
- **Transports**: JSON-RPC (default), gRPC (optional).
- **Protocol versions**: 0.2 and 0.3 supported.
- **Push notifications**: HMAC-SHA256 signed webhooks with replay protection.

### 6.1 A2A Authentication & Principal Chain

External A2A callers authenticate using one of:

| Method | Configuration | Principal |
|--------|--------------|-----------|
| **Bearer token** | `auth.type: bearer`, token validated against API key registry | The `ServiceAccount` associated with the API key |
| **OIDC** | `auth.type: oidc`, token validated against configured OIDC provider | The `User` from the OIDC token's `sub` claim |
| **API key** | `auth.type: api_key`, key in `X-API-Key` header | The `ServiceAccount` associated with the key |
| **mTLS** | `auth.type: mtls`, certificate CN maps to ServiceAccount | The `ServiceAccount` matching the CN |

The principal chain for an A2A-initiated execution: `External ServiceAccount/User → Automation → Crew → Agent`. RBAC and AgentPolicy enforcement apply identically to human-initiated executions.

## 7. Versioning & Rollback

- Every deployment creates a new **version** with a sequential number.
- Versions are immutable snapshots of the resource graph + dependencies.
- `POST /api/v1/automations/{name}/rollback?version=3` rolls back to version 3.
- `GET /api/v1/automations/{name}/versions` lists all versions with status and metadata.
- Rollback is instantaneous (swap the active version pointer).
- **v1 strategy**: Simple version swap (deploy new, rollback to old). Blue-green and canary deployment strategies are deferred to post-v1.
- **Health checks**: Deployed automations expose a health endpoint at `/api/v1/automations/{name}/health` returning `{status: "healthy"|"degraded"|"unhealthy", checks: {litellm: "ok", tools: "ok", ...}}`. Health checks verify: LiteLLM Proxy reachability, required tool availability, required LLM connection validity, and sandbox runtime readiness.

## 8. Webhook Streaming

Push execution events to external webhooks in real-time:

```yaml
spec:
  webhook_streaming:
    enabled: true
    url: "https://hooks.example.com/crew-events"
    secret_env: WEBHOOK_STREAMING_SECRET
    events:
      - execution.started
      - execution.task_completed
      - execution.completed
      - execution.failed
    retry:
      max_attempts: 3
      backoff: exponential
```

## 9. React Component Export

Automations can be exported as embeddable React components:

```
POST /api/v1/automations/{name}/export/react
→ { component_url, embed_code, api_key }
```

The component provides a pre-built UI for kicking off the crew, viewing progress, and displaying results — embeddable in any React application.

## 10. Automations Dashboard (UI)

- **Table view**: All automations with status (Online / Failed / Deploying), source, URL, last execution.
- **Filters**: By status, source method, trigger type.
- **Actions**: Deploy, re-deploy, rollback, delete, view traces.
- **Detail view**: Configuration, environment variables, trigger settings, version history, execution history.

## 11. Acceptance Criteria

1. A crew deployed from Git auto-deploys on push and is accessible via API.
2. ZIP deployment works for quick iterations without Git.
3. Studio-published crews are deployed as automations.
4. Scheduled triggers fire at the correct cron time.
5. Webhook triggers accept external POST requests and kick off executions.
6. Custom triggers work: a webhook with filter logic correctly decides whether to kick off execution.
7. A2A agent cards are auto-generated and discoverable.
8. Rollback to a previous version is instantaneous and the old version runs correctly.
9. Webhook streaming delivers events to configured endpoints with retry on failure.
10. React component export produces a working embeddable component.
