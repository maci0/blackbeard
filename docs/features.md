# Features Reference

This document covers features not included in the quickstart or YAML reference. For resource definitions see [yaml-reference.md](yaml-reference.md), for first-run setup see [quickstart.md](quickstart.md).

---

## Agency Agents Import

Import pre-built agent personas from the [Agency Agents](https://github.com/msitarzewski/agency-agents) library. The library contains 15 divisions (academic, design, engineering, finance, game-development, marketing, paid-media, product, project-management, sales, spatial-computing, specialized, strategy, support, testing) with dozens of personas each.

### From the UI

1. Navigate to the **Resources** page
2. Use the import function to browse Agency Agents divisions
3. Select agents to import, they become Blackbeard Agent resources in your project

### From the API

```bash
# List available agents (optionally filter by division)
curl -H "X-API-Key: $KEY" \
  "http://localhost:8000/api/v1/import/agency-agents?division=engineering"

# Import specific agents by slug
curl -X POST -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"slugs": ["full-stack-developer", "devops-engineer"]}' \
  http://localhost:8000/api/v1/import/agency-agents
```

Imported agents get the label `source: agency-agents` and their division label for filtering. The API caches GitHub responses for 5 minutes to avoid rate limits.

---

## Tools Library

A bundled catalog of tools ready to install with one click. The library includes builtin tools (file operations, web search, shell commands), MCP tools (stdio and HTTP transports), and Python tools.

### From the UI

Navigate to **Tool Library** in the sidebar (under Resources). Browse the catalog, click **Install** on any tool to create it as a Tool resource.

### From the API

```bash
# Browse the catalog
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/tools/library

# Install a tool
curl -X POST -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "web-search"}' \
  http://localhost:8000/api/v1/tools/library/install
```

---

## Credentials Manager

Centralized secret storage for API keys, tokens, and connection strings used by tools and integrations.

### From the UI

Navigate to **Credentials** in the sidebar (under Admin). Add credentials with a name, type, and value. Values are masked in the UI after creation.

### From the API

```bash
# Store a credential
curl -X POST -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "openai-key", "type": "api_key", "value": "sk-..."}' \
  http://localhost:8000/api/v1/credentials

# List credentials (values masked)
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/credentials

# Delete a credential
curl -X DELETE -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/credentials/openai-key
```

---

## A2A Protocol (Agent-to-Agent)

Blackbeard implements the A2A protocol for inter-agent discovery. Crews with `spec.a2a.enabled: true` automatically generate agent cards.

### Agent Card Endpoint

```bash
# Public endpoint, no auth required
curl http://localhost:8000/.well-known/agent-card.json
```

Returns a JSON array of agent cards with skills (derived from task refs), authentication schemes, and capabilities. Cached for 60 seconds.

### Enabling A2A on a Crew

```yaml
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: research-crew
spec:
  process: sequential
  agents:
    - "ref:agents/researcher"
  tasks:
    - "ref:tasks/research"
  a2a:
    enabled: true
```

---

## MCP tools

Tool resources with `type: mcp-stdio` or `type: mcp-http` attach to agents as CrewAI MCP server configs (`mcps`), not in-process Python tools. Stdio servers need `command`/`args`/`env`; HTTP servers need `url` (SSRF-checked). See `examples/tools/mcp-*.yaml`.

## Tool sandbox tiers

Tools can run under isolation tiers (`none`, `wasm`, `docker`/`podman`, `gvisor`, `microvm`). See [tool-sandboxes.md](tool-sandboxes.md) for declaration patterns, `image` overrides, and network capabilities.

## Resource Versioning

Every resource create or update creates a version snapshot. You can list versions, view past snapshots, and roll back to any previous version.

### From the API

```bash
# List versions for a resource
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/agents/researcher/versions

# View a specific version snapshot
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/agents/researcher/versions/3

# Roll back to a previous version
curl -X POST -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"version": 3}' \
  http://localhost:8000/api/v1/agents/researcher/rollback
```

### From the UI

On any resource detail page, the **Version History** tab shows all past mutations with timestamps and diffs.

---

## PII Detection and Compliance Presets

The PII system supports four compliance presets that define which entity types to detect and redact:

| Preset | Entities |
|--------|----------|
| `hipaa` | PERSON, PHONE_NUMBER, EMAIL_ADDRESS, DATE_TIME, LOCATION, US_SSN, MEDICAL_LICENSE, US_DRIVER_LICENSE, IP_ADDRESS |
| `gdpr` | PERSON, PHONE_NUMBER, EMAIL_ADDRESS, LOCATION, DATE_TIME, IP_ADDRESS, IBAN_CODE, CREDIT_CARD |
| `pci-dss` | CREDIT_CARD, IBAN_CODE, US_BANK_NUMBER, US_SSN |
| `ccpa` | PERSON, PHONE_NUMBER, EMAIL_ADDRESS, LOCATION, DATE_TIME, IP_ADDRESS, US_SSN, US_DRIVER_LICENSE |

Use presets in PII Studio nodes or guardrail configurations to automatically detect and redact sensitive data before it reaches LLM providers.

---

## Guardrail Playground

Test guardrails with sample input before deploying them to production tasks.

Navigate to **Guardrails** in the sidebar (under Operations). Enter sample text, select a guardrail type (function, LLM, schema, PII), and run a test to see what would be flagged or modified.

---

## Execution Comparison

Compare two executions side by side to understand performance differences.

Navigate to **Executions**, select two executions, and click **Compare**. The comparison page shows:

- Duration diff
- Token usage diff
- Cost diff
- Per-task status comparison
- Output diff

Direct URL: `/executions/compare?a=<id1>&b=<id2>`

---

## Chat Playground

Interactive LLM conversation interface at `/chat`. Select any configured LLMConnection and chat directly with the model. Supports real-time SSE streaming with a stop button for in-flight cancellation.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+K` / `Ctrl+K` | Command palette |
| `Cmd+Shift+S` | Go to Studio |
| `Cmd+Shift+E` | Go to Executions |
| `Cmd+Shift+N` | Go to Resources |
| `Cmd+.` | Go to Settings |
| `?` | Shortcuts dialog |

Studio-specific shortcuts are documented in the [Studio guide](studio-guide.md).

---

## SDKs

### Python

```bash
pip install blackbeard-sdk
# or from source
cd sdks/python && pip install -e .
```

```python
from blackbeard import BlackbeardClient

client = BlackbeardClient("http://localhost:8000", api_key="your-key")

# List agents
agents = client.list("agents")

# Kick off a crew
execution = client.kickoff("research-crew", inputs={"topic": "AI agents"})

# Wait for completion
result = client.wait(execution["id"])
```

### TypeScript

```bash
npm install @blackbeard/sdk
# or from source
cd sdks/typescript && npm install && npm run build
```

```typescript
import { BlackbeardClient } from "@blackbeard/sdk";

const client = new BlackbeardClient("http://localhost:8000", { apiKey: "your-key" });

const agents = await client.list("agents");
const execution = await client.kickoff("research-crew", { topic: "AI agents" });
```

### React

```bash
npm install @blackbeard/react
```

```tsx
import { BlackbeardProvider, CrewRunner, ExecutionStatus } from "@blackbeard/react";

function App() {
  return (
    <BlackbeardProvider baseUrl="http://localhost:8000" apiKey="your-key">
      <CrewRunner crew="research-crew" />
      <ExecutionStatus id="exec-123" />
    </BlackbeardProvider>
  );
}
```

---

## Bulk Operations

### Multi-select delete

On the Resources page, check multiple resources and click **Delete Selected** for batch deletion.

### YAML import

Paste multi-document YAML (separated by `---`) into the import dialog on the Resources page to create multiple resources at once. Also available from the CLI:

```bash
uv run blackbeard apply -f resources/
```

### Bulk export

```bash
# Export all resources as a single YAML stream
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/resources/export > backup.yaml

# CLI equivalent
uv run blackbeard export --all > backup.yaml
```

---

## Plugin SDK

Extend Blackbeard with custom functionality through 4 plugin extension types:

| Extension Type | Purpose |
|----------------|---------|
| `tool` | Custom tool implementations for agents |
| `guardrail` | Custom validation logic for task outputs |
| `auth_provider` | External authentication provider integration |
| `execution_hook` | Pre/post execution callbacks for logging, metrics, or side effects |

Plugins are registered via Python entry points or the plugin API. Each plugin type has a base class to implement:

```python
from blackbeard.plugins import ToolPlugin

class MyCustomTool(ToolPlugin):
    name = "my-tool"
    description = "Does something useful"

    def run(self, input_data: str) -> str:
        return f"Processed: {input_data}"
```

---

## Interactive TUI Shell

The CLI includes an interactive REPL for exploratory resource management. Launch it with:

```bash
uv run blackbeard shell
```

The shell supports tab completion, command history, and inline help. All standard CLI commands are available without the `blackbeard` prefix:

```
blackbeard> list Agent
blackbeard> get Crew research-crew
blackbeard> kickoff research-crew --input topic="AI"
blackbeard> status <execution-id>
```

---

## Temporal Workflow Integration

Blackbeard supports [Temporal](https://temporal.io/) as an optional durable workflow engine. When configured, crew executions run as Temporal workflows instead of ThreadPoolExecutor threads, providing automatic retries, visibility, and crash recovery.

### Configuration

Set the `TEMPORAL_HOST` environment variable to enable Temporal:

```bash
TEMPORAL_HOST=localhost:7233
```

When `TEMPORAL_HOST` is not set, Blackbeard falls back to ThreadPoolExecutor (the default behavior). No code changes are needed to switch between the two.

### What changes with Temporal

- Executions survive API server restarts
- Automatic retry on transient failures
- Temporal UI provides execution visibility and debugging
- Workflow history is retained for auditing

---

## MCP tools

Tool resources with `type: mcp-stdio` or `type: mcp-http` attach to agents as CrewAI MCP server configs (`mcps`), not in-process Python tools. Stdio servers need `command`/`args`/`env`; HTTP servers need `url` (SSRF-checked). See `examples/tools/mcp-*.yaml`.

## Tool sandbox tiers

Tools can run under isolation tiers (`none`, `wasm`, `docker`/`podman`, `gvisor`, `microvm`). See [tool-sandboxes.md](tool-sandboxes.md) for declaration patterns, `image` overrides, and network capabilities.

## Resource Versioning

Every resource create or update is snapshotted in the database. List versions, inspect a snapshot, and roll back via the REST API:

```bash
# List versions for a resource
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/agents/researcher/versions

# Get a specific version
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/agents/researcher/versions/3

# Roll back to a previous version
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"version": 3}' \
  http://localhost:8000/api/v1/agents/researcher/rollback
```

### Monitoring Stack

Optional OpenTelemetry export via `OTEL_ENDPOINT`. The `deploy/monitoring/` directory includes Prometheus scrape configs, Grafana dashboard JSON, and alerting rules for production deployments.

---

## Nested Project Hierarchy

Projects support parent-child relationships for organizing resources into a hierarchy. Child projects can inherit policies from their parent, reducing duplication.

### Configuration

```yaml
apiVersion: blackbeard/v1
kind: Project
metadata:
  name: ml-team-prod
spec:
  description: "ML team production workloads"
  parent: "ref:projects/ml-team"
  inherit_policies: true
```

When `inherit_policies` is `true`, the child project inherits `default_agent_policy`, `guardrails`, and `resource_quota` from its parent. Child-level settings override parent settings where both are defined.

---

## Tool Versioning

Tools support semantic versioning and deprecation to manage lifecycle transitions.

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: web-search
spec:
  type: python
  class_path: crewai_tools.SerperDevTool
  tool_version: "2.1.0"
  deprecated: false
```

When a tool is marked `deprecated: true`, the UI shows a warning badge and the optional `deprecated_message` field is displayed to guide users toward the replacement.

---

## Composite Guardrail Chains

Combine multiple guardrails into a single chain using AND/OR logic:

```yaml
apiVersion: blackbeard/v1
kind: Guardrail
metadata:
  name: safety-chain
spec:
  type: composite
  operator: AND
  guardrails:
    - "ref:guardrails/no-pii"
    - "ref:guardrails/no-profanity"
    - "ref:guardrails/format-check"
  on_fail: reject
```

With `operator: AND`, all guardrails must pass. With `operator: OR`, at least one must pass. Composite guardrails can reference any other guardrail type (function, llm, schema, pii, hallucination).

---

## Canvas Export

The Studio toolbar includes export options for sharing or archiving crew designs:

- **PNG** -- raster image of the current canvas
- **SVG** -- vector image, suitable for documentation or printing
- **JSON** -- full canvas state (nodes, edges, positions) for re-importing

Use the **Export** dropdown in the Studio toolbar to select the format.
