# PRD 11 — API & Extensibility

## 1. Purpose

Define the public API surface, webhook streaming protocol, plugin SDK, and extension points that allow Blackbeard to be embedded, extended, and integrated into arbitrary systems.

## 2. REST API

**Convention:** All API paths use lowercase plural resource names: `/api/v1/agents/{name}`, `/api/v1/tasks/{name}`, `/api/v1/crews/{name}`, etc. This follows REST conventions and Kubernetes API patterns.

### 2.1 Resource API (Uniform CRUD)

All resources (PRD 01) are exposed through a uniform REST API:

```
# Resources (replace 'agents' with any resource kind in lowercase plural)
GET    /api/v1/agents                          List resources
GET    /api/v1/agents/{name}                   Get one resource
POST   /api/v1/agents                          Create (YAML or JSON body)
PUT    /api/v1/agents/{name}                   Replace
PATCH  /api/v1/agents/{name}                   Partial update (JSON Merge Patch)
DELETE /api/v1/agents/{name}                   Delete
POST   /api/v1/agents/{name}/validate          Dry-run validation

# Execution
POST   /api/v1/automations/{name}/kickoff      Start execution
GET    /api/v1/executions/{id}                 Get execution status
GET    /api/v1/executions/{id}/stream          SSE stream of execution events
POST   /api/v1/executions/{id}/resume          Resume with human feedback
GET    /api/v1/executions/{id}/trace           Get full trace
POST   /api/v1/automations/{name}/rollback     Rollback to version

# Repository
GET    /api/v1/repo/agents                     Browse repository assets
GET    /api/v1/repo/agents/{name}              Get asset detail
POST   /api/v1/repo/agents                     Publish asset
GET    /api/v1/repo/agents/{name}/versions     List versions

# Identity
POST   /api/v1/auth/login                     Login (email/password)
POST   /api/v1/auth/token/refresh              Refresh JWT
GET    /api/v1/auth/me                         Current user info
POST   /api/v1/auth/sso/callback               SSO callback
```

### 2.2 Authentication

| Method | Use Case | Header |
|--------|----------|--------|
| JWT | Browser/SPA | `Authorization: Bearer <jwt>` |
| API Key | CI/CD, scripts | `X-API-Key: <key>` |
| mTLS | Service-to-service | Client certificate |
| OIDC | SSO redirect flow | Via `/auth/sso/*` endpoints |

### 2.3 Response Format

```json
{
  "apiVersion": "blackbeard/v1",
  "kind": "Agent",
  "metadata": {
    "name": "researcher",
    "namespace": "production",
    "labels": {"team": "data-science"},
    "createdAt": "2026-05-10T12:00:00Z",
    "updatedAt": "2026-05-10T12:00:00Z",
    "version": 3
  },
  "spec": { ... }
}
```

### 2.4 Error Format

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Agent 'researcher' has invalid tool reference",
    "details": [
      {
        "field": "spec.tools[0].ref",
        "value": "tools/nonexistent",
        "reason": "Referenced tool does not exist"
      }
    ]
  }
}
```

### 2.5 Pagination, Filtering, Sorting

```
GET /api/v1/agents?limit=20&offset=40
GET /api/v1/agents?label=team:data-science
GET /api/v1/agents?sort=-updatedAt
GET /api/v1/agents?filter=spec.llm:gpt-4o
```

### 2.6 Rate Limiting

All API endpoints are rate-limited per authentication principal:

| Principal | Default Limit | Configurable |
|-----------|--------------|-------------|
| JWT (user) | 120 req/min | Yes, via PlatformConfig |
| API Key | Per-key `rate_limit.requests_per_minute` | Yes, per APIKey resource |
| Unauthenticated | 10 req/min | Yes |

Rate limit headers are returned on every response:
```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1720000060
```

Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

## 3. gRPC API

A gRPC API mirrors the REST API for high-performance integrations:

```protobuf
service BlackbeardAPI {
  rpc GetResource(GetResourceRequest) returns (Resource);
  rpc ListResources(ListResourcesRequest) returns (ListResourcesResponse);
  rpc CreateResource(CreateResourceRequest) returns (Resource);
  rpc UpdateResource(UpdateResourceRequest) returns (Resource);
  rpc DeleteResource(DeleteResourceRequest) returns (Empty);
  
  rpc Kickoff(KickoffRequest) returns (KickoffResponse);
  rpc GetExecution(GetExecutionRequest) returns (Execution);
  rpc StreamExecution(StreamExecutionRequest) returns (stream ExecutionEvent);
  rpc ResumeExecution(ResumeRequest) returns (ResumeResponse);
}
```

*gRPC API is post-MVP. The proto definition above is a design target, not a v1 deliverable. `ExecutionEvent` message definition will be specified when gRPC implementation begins. MVP exposes REST API only.*

## 4. Webhook Streaming

Push events to external systems in real-time:

```
POST https://hooks.example.com/blackbeard-events
Content-Type: application/json
X-Blackbeard-Signature: sha256=<hmac>
X-Blackbeard-Timestamp: 1720000000
X-Blackbeard-Event: execution.task_completed

{
  "event": "execution.task_completed",
  "timestamp": "2026-05-10T12:01:23Z",
  "data": {
    "execution_id": "exec-abc123",
    "task_name": "research-ai",
    "agent_name": "researcher",
    "status": "completed",
    "duration_ms": 12400,
    "token_usage": { ... }
  }
}
```

### 4.1 Webhook Configuration

```yaml
apiVersion: blackbeard/v1
kind: WebhookEndpoint
metadata:
  name: slack-notifications
spec:
  url: "https://hooks.slack.com/services/xxx"
  secret_env: WEBHOOK_SECRET
  events:
    - "execution.completed"
    - "execution.failed"
    - "agent.policy.denied"
  filters:
    automation: ["research-pipeline-prod"]
  retry:
    max_attempts: 5
    backoff: exponential
    initial_delay_ms: 1000
  timeout_ms: 10000
```

**Replay protection**: Each webhook delivery includes `X-Blackbeard-Timestamp` and `X-Blackbeard-Signature` (HMAC-SHA256 of `timestamp.body` using the webhook secret). Receivers should reject deliveries older than 5 minutes. Failed deliveries are retried with the same signature — receivers must be idempotent (use `execution_id` + `event` as dedup key).

**Webhook management:** Webhook subscriptions are configured as part of the Automation resource's `spec.triggers` array (PRD 09). For MVP (before Automations exist), webhooks are not available — SSE is the only real-time event mechanism. Post-MVP, webhooks are managed through the Automation CRUD API:
```
POST   /api/v1/automations/{name}                 # Create automation with webhook trigger
PATCH  /api/v1/automations/{name}                 # Update webhook config (hot-updatable)
GET    /api/v1/automations/{name}/webhooks/test   # Send a test webhook event
```

## 5. Plugin SDK

### 5.1 Plugin Types

| Plugin Type | Extension Point | Interface |
|-------------|-----------------|-----------|
| **Tool Plugin** | Add new tool types | `BaseTool` class or WASM WIT interface |
| **LLM Plugin** | Add new LLM providers | `BaseLLMProvider` class |
| **Auth Plugin** | Add auth methods | `BaseAuthProvider` class |
| **Storage Plugin** | Add persistence backends | `BaseStorageProvider` class |
| **Sandbox Plugin** | Add sandbox runtimes | `BaseSandboxProvider` class |
| **Guardrail Plugin** | Add guardrail types | `BaseGuardrail` class |
| **Trigger Plugin** | Add trigger types | `BaseTrigger` class |
| **Observer Plugin** | Add observability exporters | `BaseObserver` class |
| **UI Plugin** | Add UI micro-frontends | React component package |

### 5.2 Plugin Manifest

```yaml
apiVersion: blackbeard/v1
kind: Plugin
metadata:
  name: my-custom-llm
  version: 1.0.0
spec:
  type: llm_provider
  implementation: "mycompany.llm:CustomLLMProvider"
  config_schema:
    type: object
    properties:
      endpoint: { type: string, format: uri }
      model: { type: string }
    required: ["endpoint", "model"]
  description: "Custom LLM provider for internal models"
```

### 5.3 Core Plugin Interfaces

```python
# Tool plugin
class BaseToolPlugin:
    name: str
    description: str
    parameters: dict                    # JSON Schema for tool parameters
    
    def invoke(self, parameters: dict, context: dict) -> str:
        """Execute the tool and return a string result."""
        ...
    
    def validate_config(self, config: dict) -> list[str]:
        """Validate plugin configuration. Return list of errors (empty = valid)."""
        ...

# Sandbox plugin
class BaseSandboxPlugin:
    name: str
    tier: str                          # unique tier name (e.g., "firecracker", "kata")
    
    def create(self, profile: "SandboxProfile") -> "SandboxInstance":
        """Create a sandbox instance with the given profile."""
        ...
    
    def execute(self, instance: "SandboxInstance", tool_input: dict) -> dict:
        """Execute a tool invocation inside the sandbox."""
        ...
    
    def destroy(self, instance: "SandboxInstance") -> None:
        """Destroy the sandbox instance and free resources."""
        ...

# Trigger plugin
class BaseTriggerPlugin:
    name: str
    config_schema: dict                # JSON Schema for trigger configuration
    
    def register(self, automation_name: str, config: dict) -> None:
        """Register the trigger for an automation."""
        ...
    
    def unregister(self, automation_name: str) -> None:
        """Unregister the trigger."""
        ...
    
    def handle_event(self, event: dict) -> dict | None:
        """Process an incoming event. Return kickoff inputs or None to skip."""
        ...
```

Full interface definitions for all plugin types are available in the `blackbeard.plugins` package. Post-MVP: these interfaces will be published as a separate `blackbeard-plugin-sdk` package.

### 5.4 Plugin Lifecycle

```bash
# Install a plugin
blackbeard plugin install ./my-plugin/

# List installed plugins
blackbeard plugin list

# Enable/disable per namespace
blackbeard plugin enable my-custom-llm --namespace production
blackbeard plugin disable my-custom-llm --namespace staging
```

## 6. CLI (`blackbeard`)

The Blackbeard CLI is built with **Click** for command structure and **Rich** for terminal output. All commands produce polished, human-readable output by default and structured JSON when `--json` is passed.

### 6.1 Technology

| Component | Library | Rationale |
|-----------|---------|-----------|
| Command framework | **Click** | Mature, composable, supports groups/context/envvar fallbacks |
| Terminal output | **Rich** | Tables, panels, progress spinners, syntax-highlighted JSON/YAML, clickable links |
| HTTP client | **httpx** | Async-capable, timeout support, connection pooling |

### 6.2 Global Options

All options live on the root `blackbeard` group and are available to every subcommand via `click.pass_context`:

| Flag | Env Var | Default | Description |
|------|---------|---------|-------------|
| `--server` | `BLACKBEARD_SERVER` | `http://localhost:8000` | API server URL |
| `--api-key` | `BLACKBEARD_API_KEY` | *(required for server commands)* | API authentication key |
| `-n, --namespace` | `BLACKBEARD_NAMESPACE` | `default` | Resource namespace |
| `--json` | — | `false` | Output structured JSON instead of Rich tables/panels |
| `--version` | — | — | Show version and exit |

### 6.3 Commands (MVP)

```bash
# Resource management
blackbeard validate -f resources/              # offline validation (no server needed)
blackbeard apply -f resources/                 # create or update (upsert)
blackbeard apply -f resources/ --dry-run       # validate + show what would be applied

# Execution
blackbeard kickoff research-crew --input topic="AI safety"
blackbeard status <execution-id>
blackbeard status <execution-id> --watch       # poll until terminal state
```

### 6.4 Commands (Post-MVP)

```bash
# Resource CRUD
blackbeard get agents/researcher               # single resource
blackbeard list agents                         # list by kind
blackbeard delete agents/researcher            # with confirmation
blackbeard cancel <execution-id>               # cancel running execution

# Repository (post-MVP)
blackbeard repo publish agents/researcher/ --version 1.0.0
blackbeard repo install tools/sentiment-analyzer@0.3.0

# Tools (post-MVP)
blackbeard tool compile --lang python --input tools/my_tool.py --output tools/my_tool.wasm
blackbeard tool test tools/my_tool.yaml --input '{"query": "test"}'

# Deployment (post-MVP)
blackbeard deploy research-pipeline-prod --from-git main
blackbeard rollback research-pipeline-prod --version 2

# RBAC (post-MVP)
blackbeard auth login
blackbeard auth whoami
```

### 6.5 Output Design

Every command supports two output modes:

| Mode | Trigger | Format | Use case |
|------|---------|--------|----------|
| **Rich** (default) | No flag | Tables, panels, progress spinners, colored status | Interactive terminal use |
| **JSON** | `--json` | Structured JSON to stdout | Scripting, CI/CD pipelines, `jq` |

#### Rich output components

| Component | Used by | Description |
|-----------|---------|-------------|
| `Table` | `validate`, `apply`, `status` (tasks) | Columnar data with headers, borders, and colored status cells |
| `Panel` | `kickoff`, `status` | Bordered box with title for execution details, errors, outputs |
| `Progress` (spinner) | `apply` | Animated spinner during resource application with per-resource description |
| `Syntax` | `status` (outputs) | Syntax-highlighted JSON for execution outputs (Monokai theme) |
| `console.status()` | `kickoff` | Spinner while submitting execution |
| `console.clear()` | `status --watch` | Full-screen repaint on each poll (like `watch(1)`) |

#### Console separation

Two `Console` instances ensure clean stream separation:

```python
console = Console(stderr=True)   # progress, errors, status — never pollutes stdout
out = Console()                  # data output (JSON mode) — goes to stdout
```

This means `blackbeard --json status <id> 2>/dev/null | jq .status` works correctly — progress/errors go to stderr, data goes to stdout.

#### Example: `validate` output

```
                         Validation Results
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Stat… ┃ Kind/Name             ┃ Source                       ┃ Issues ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ ✓     │ Agent/researcher      │ agents/researcher.yaml       │ OK     │
│ ✓     │ Task/research-topic   │ tasks/research-topic.yaml    │ OK     │
│ ✗     │ Crew/bad-crew         │ crews/bad-crew.yaml          │ • …    │
└───────┴───────────────────────┴──────────────────────────────┴────────┘

3 resources: 2 valid, 1 errors
```

#### Example: `--json validate` output

```json
{
  "valid": false,
  "total": 3,
  "errors": [
    {
      "kind": "Crew",
      "name": "bad-crew",
      "source": "crews/bad-crew.yaml",
      "issues": [{"field": "spec.agents", "message": "'agents' is a required property"}]
    }
  ],
  "cycles": []
}
```

#### Example: `status` output

```
╭──────────── Execution completed ─────────────╮
│  Execution ID  abc-123-def-456               │
│  Status        completed                     │
│  Crew          research-crew                 │
│  Tokens        12,450                        │
│  Cost          $0.0234                       │
│  Started       2026-05-12T10:30:00Z          │
│  Completed     2026-05-12T10:31:42Z          │
│  Trace         https://langfuse.local/trace/… │
╰──────────────────────────────────────────────╯
╭─ Outputs ────────────────────────────────────╮
│ {                                            │
│   "raw": "A comprehensive report on..."     │
│ }                                            │
╰──────────────────────────────────────────────╯
                    Tasks
┏━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ # ┃ Task           ┃ Agent      ┃ Status    ┃ Tokens ┃
┡━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ 0 │ research-topic │ researcher │ completed │  8,200 │
│ 1 │ write-report   │ writer     │ completed │  4,250 │
└───┴────────────────┴────────────┴───────────┴────────┘
```

### 6.6 Error Handling

| Scenario | Behavior |
|----------|----------|
| Missing API key | `console.print("[red bold]Error:[/] API key required...")` + exit 1 |
| Server unreachable | `"Cannot reach server at {url}. Check --server or BLACKBEARD_SERVER."` |
| HTTP error | Status code + detail from response body |
| Validation failure | Per-resource error table with field-level issues |
| No resources found | Warning to stderr + exit 1 |

All errors go to stderr via `Console(stderr=True)`. Exit codes: `0` = success, `1` = failure.

### 6.7 Special Behaviors

| Feature | Description |
|---------|-------------|
| **Dependency ordering** | `apply` topologically sorts resources using the ref graph before sending to the server. Falls back to file order with a warning if sorting fails. |
| **Multi-document YAML** | `validate` and `apply` support `---`-separated multi-document YAML files via `yaml.safe_load_all()`. |
| **JSON input coercion** | `--input count=5` auto-parses `5` as integer via `json.loads()`. Strings that aren't valid JSON are kept as strings. |
| **Watch mode** | `status --watch` clears the terminal and re-renders the full status panel every 2 seconds until a terminal state is reached. |
| **Dry run** | `apply --dry-run` validates locally and lists what would be applied without making API calls. |

### 6.8 Acceptance Criteria

1. `blackbeard validate -f dir/` produces a Rich table with per-resource status.
2. `blackbeard --json validate -f dir/` produces structured JSON to stdout.
3. `blackbeard apply -f dir/` shows a progress spinner during application and a results table after.
4. `blackbeard kickoff crew-name` shows a Rich panel with execution ID and a follow-up hint.
5. `blackbeard status <id>` shows a Rich panel with execution details, tasks table, and syntax-highlighted outputs.
6. `blackbeard status <id> --watch` clears and re-renders every 2 seconds.
7. All errors go to stderr; `--json` data goes to stdout.
8. Exit code 0 on success, 1 on any failure.
9. `--server`, `--api-key`, `--namespace` work via both flags and environment variables.

## 7. React Component Export

Any automation can be exported as an embeddable React component:

```typescript
import { BlackbeardWidget } from '@blackbeard/react';

function App() {
  return (
    <BlackbeardWidget
      automationId="research-pipeline-prod"
      apiUrl="https://blackbeard.sh/api/v1"
      apiKey="ck_..."
      onComplete={(result) => console.log(result)}
      theme="light"
    />
  );
}
```

The widget provides:
- Input form (auto-generated from crew inputs schema).
- Execution progress (task timeline, agent activity).
- Output display (rendered markdown, JSON, or custom template).
- HITL feedback UI (when human-in-the-loop is triggered).

*This feature is post-v1 and requires a separate technical design document. The specification above is a design target describing the intended user experience. Implementation details (component props, auth handling, bundle strategy, SSR support) will be specified before work begins.*

## 8. OpenAPI / AsyncAPI

- **OpenAPI 3.1** spec auto-generated from the API routes and resource schemas.
- Available at `/api/v1/openapi.json` and `/api/v1/docs` (Swagger UI).
- **AsyncAPI** spec for webhook streaming events.
- Available at `/api/v1/asyncapi.json`.

## 9. SDKs

*Python and TypeScript SDKs are post-MVP. The examples below show the target developer experience.*

### 9.1 Python SDK

*Post-MVP. SDKs will be auto-generated from the OpenAPI specification.*

```python
from blackbeard import BlackbeardClient

client = BlackbeardClient(url="https://blackbeard.sh", api_key="ck_...")

# Create an agent
agent = client.agents.create_from_yaml("agents/researcher.yaml")

# Kickoff
execution = client.automations.kickoff("research-pipeline-prod", inputs={"topic": "AI"})

# Stream results
for event in execution.stream():
    print(event.type, event.data)

# Get result
result = execution.wait()
print(result.outputs)
```

### 9.2 TypeScript SDK

*Post-MVP. SDKs will be auto-generated from the OpenAPI specification.*

```typescript
import { BlackbeardClient } from '@blackbeard/sdk';

const client = new BlackbeardClient({ url: '...', apiKey: '...' });

const execution = await client.automations.kickoff('research-pipeline-prod', {
  inputs: { topic: 'AI' }
});

for await (const event of execution.stream()) {
  console.log(event.type, event.data);
}
```

## 10. Acceptance Criteria

1. All resource kinds are CRUD-accessible via REST API with proper auth.
2. API returns consistent error format with field-level detail.
3. gRPC API mirrors REST API functionality.
4. Webhook streaming delivers signed events with retry on failure.
5. Plugin SDK allows registering a custom tool, LLM provider, and sandbox provider.
6. CLI `blackbeard apply` creates resources from YAML files.
7. CLI `blackbeard kickoff` starts an execution and `blackbeard status` shows progress.
8. React component export produces a working embeddable widget.
9. OpenAPI spec is auto-generated and valid; Swagger UI renders correctly.
10. Python and TypeScript SDKs can create resources, kickoff executions, and stream results.

## Error Code Taxonomy

All API errors use the error format defined in §2.4. Error codes are namespaced by subsystem:

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_FAILED` | 400 | Resource YAML/JSON failed schema validation |
| `REF_NOT_FOUND` | 400 | A `ref:` target does not exist |
| `CYCLE_DETECTED` | 400 | Circular reference detected in resource graph |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource does not exist |
| `RESOURCE_CONFLICT` | 409 | Optimistic locking conflict (resource modified since last read) |
| `POLICY_DENIED` | 403 | AgentPolicy denied the requested action |
| `BUDGET_EXCEEDED` | 429 | LLM budget exceeded for this agent/execution |
| `SANDBOX_ERROR` | 500 | Tool execution failed inside sandbox |
| `SANDBOX_INFRA_ERROR` | 503 | Sandbox infrastructure failure (runtime crash, Docker unreachable) |
| `LLM_TIMEOUT` | 504 | LLM call timed out |
| `LLM_UNAVAILABLE` | 503 | LiteLLM Proxy unreachable |
| `GUARDRAIL_FAILED` | 422 | Output guardrail validation failed after max retries |
| `EXECUTION_FAILED` | 500 | Execution failed with an unrecoverable error |
| `AUTH_REQUIRED` | 401 | Missing or invalid authentication |
| `FORBIDDEN` | 403 | Authenticated but insufficient permissions |
| `RATE_LIMITED` | 429 | API rate limit exceeded |
