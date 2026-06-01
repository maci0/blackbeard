# PRD 04  -- Tool & Integration Registry

## 1. Purpose

Provide a centralised catalogue for all tools, integrations, and MCP servers that agents can use. Tools are defined as YAML resources, discoverable through a searchable registry UI, installable per-agent or per-crew, and governed by RBAC.

### 1.1 MVP Scope

**Implemented:** Python tools (`BaseTool`), WASM tools (compiled and executed in Wasmtime sandbox), MCP tools (both stdio and HTTP transports), and builtin tool types are all supported. Tool discovery and the marketplace import from git (`blackbeard apply` from a git-cloned directory) are working. Tools are governed by AgentPolicy allowlist/denylist enforcement.

**Implemented (post-MVP):** Agency Agents integration  -- import agent persona definitions from the [Agency Agents](https://github.com/msitarzewski/agency-agents) markdown library (144+ personas across 12 divisions). Backend parser converts markdown persona files into Blackbeard Agent resources by extracting role, goal, backstory, and tool suggestions from structured markdown sections. Import via API endpoint or Studio UI "Browse Templates" button.

**Implemented (post-MVP):** Skills & Tools Library  -- a curated browsable library of tools and skills accessible from the `/tools/library` page and Studio palette. Categories: Web (search, scrape, HTTP), Data (CSV, JSON, database), Code (interpreter, linter, formatter), Communication (email, Slack, webhook), File (read, write, convert), AI (summarize, translate, classify). Each library entry includes name, description, type (python/mcp/wasm), category, install command, and preview. One-click install creates the Tool resource in Blackbeard. Backend serves the library index from a bundled YAML catalog (`tools/library.yaml`) with support for custom catalogs via URL. API: `GET /api/v1/tools/library` (browse), `POST /api/v1/tools/library/install` (install by slug).

**Implemented (post-MVP):** Tool versioning fields added to the Tool schema (`tool_version`, `deprecated`, `deprecated_message`).

**Deferred to post-MVP:** Composio integration, OAuth connectors (`IntegrationConnector` resource), tool compilation CLI (`blackbeard tool compile`), JIT tool discovery meta-tools, approval workflows.

**Note:** A Tools page (`/tools`) is implemented in the frontend with a filterable table of all registered tools, type badges (Python, WASM, builtin), sandbox tier display, and links to tool resource details.

## 2. Tool Types

| Type | Description | Default Sandbox | Example |
|------|-------------|-----------------|---------|
| **Python** | A Python class/function implementing `BaseTool` | `none` if `trusted: true`, else `wasm` (auto-compiled via componentize-py) | `crewai_tools:SerperDevTool` |
| **WASM** | A pre-compiled `.wasm` module implementing the `blackbeard:tool` WIT interface | `wasm` (always) | `tools/sentiment.wasm` |
| **MCP (stdio)** (`mcp-stdio`) | Local MCP server launched as a subprocess | `docker` | `npx @modelcontextprotocol/server-filesystem` (or `bunx`) |
| **MCP (SSE/HTTP)** (`mcp-http`) | Remote MCP server accessed over HTTP | `none` (remote call, no local code) | `https://mcp.example.com/sse` |
| **REST** | Generic HTTP API wrapped as a tool | `none` (remote call) | Any OpenAPI-described endpoint |
| **Composio** | Composio-managed integration | `none` (remote call) | Pre-built OAuth connectors |
| **Custom** | User-defined tool with arbitrary implementation | Configurable | Plugin SDK |

All sandbox tiers (`none`, `wasm`, `docker`, `microvm`) are production-valid. The default shown above is a starting point  -- it can be overridden by the tool's `sandbox` field, the agent's AgentPolicy (PRD 03), or the org default. See PRD 05, section 6 for full sandbox architecture.

**Auto-compilation note**: Python to WASM auto-compilation via componentize-py is best-effort. Not all Python packages are WASM-compatible (e.g., those with C extensions). If compilation fails, the tool falls back to its declared sandbox tier or the agent's policy default. The build log surfaces the failure with a clear message.

### WASM Tools

WASM tools are first-class citizens  -- pre-compiled to `.wasm` and executed in the WASM sandbox tier (PRD 05, section 6). They provide strong isolation with near-zero overhead and are the **recommended format for distributing third-party tools**.

**Supported source languages**: Rust, Go, C/C++, Python (via componentize-py), JavaScript/TypeScript (via javy or ComponentizeJS), Zig, Swift.

**Tool package structure**:
```
my-tool/
├── tool.wasm              # compiled WASM Component
├── tool.yaml              # Tool resource definition
└── wit/
    └── tool.wit           # WIT interface (implements blackbeard:tool)
```

**WIT contract** (all WASM tools implement this):
```wit
package blackbeard:tool@0.1.0;

interface tool {
    record tool-input {
        parameters: list<tuple<string, string>>,
        context: option<string>,
    }
    
    record tool-output {
        result: string,
        metadata: option<list<tuple<string, string>>>,
        error: option<string>,
    }
    
    invoke: func(input: tool-input) -> tool-output;
}

world blackbeard-tool {
    export tool;
    
    // Imported capabilities  -- granted by sandbox policy at instantiation
    import wasi:http/outgoing-handler@0.2.0;
    import wasi:filesystem/preopens@0.2.0;
    import wasi:io/streams@0.2.0;
    import wasi:clocks/monotonic-clock@0.2.0;
}
```

**Python → WASM compilation**: For Python tools that need sandboxing, the platform can auto-compile:
```bash
blackbeard tool compile --lang python --input tools/my_tool.py --output tools/my_tool.wasm
```

**Known limitations:** `blackbeard tool compile --lang python` uses componentize-py, which supports pure Python packages only. Packages with C extensions (numpy, pandas, lxml, etc.) are not WASM-compatible and will fail compilation with a clear error message. For tools that require these packages, use `sandbox: docker` instead of `sandbox: wasm`.

**Why distribute as WASM**:
- Runs identically on any OS/arch without dependency hell.
- Cannot access host memory, network, or filesystem unless capabilities are explicitly granted.
- Deterministic execution with fuel metering  -- no infinite loops.
- ~5ms startup vs ~500ms for Docker.
- Cacheable: compiled module is cached; instantiation is cheap.

### 2.1 CrewAI Built-in Tools

CrewAI ships with **50+ built-in tools** covering common agent tasks. Blackbeard's tool registry should integrate with these, not reimplement them:

| Category | CrewAI Built-in Examples | Blackbeard Approach |
|----------|------------------------|---------------------|
| **Search** | SerperDevTool, ScrapeWebsiteTool, WebsiteSearchTool | Use CrewAI's tools directly; register in Blackbeard's registry for discoverability |
| **File I/O** | FileReadTool, FileWriteTool, DirectoryReadTool, DirectorySearchTool | Use CrewAI's tools; sandbox via AgentPolicy |
| **Code** | CodeInterpreterTool, CodeDocsSearchTool | Use CrewAI's tools; apply Blackbeard's sandbox tier |
| **RAG** | PDFSearchTool, DOCXSearchTool, TXTSearchTool, JSONSearchTool, CSVSearchTool | Use CrewAI's tools with knowledge sources |
| **Browser** | BrowserbaseLoadTool, SeleniumScrapingTool | Use CrewAI's tools |
| **Database** | PGSearchTool, MySQLSearchTool | Use CrewAI's tools; control access via AgentPolicy |
| **AI/ML** | DallETool, VisionTool | Use CrewAI's tools |
| **Communication** | SlackTool, GmailTool | Use CrewAI's tools; Blackbeard adds OAuth management |

**Principle:** Blackbeard's tool registry is a management and governance layer over CrewAI's tool ecosystem. Our registry adds:
- **Discoverability**: Browse, search, and filter all available tools (CrewAI built-in + custom)
- **Governance**: RBAC, rate limiting, audit logging, sandbox enforcement
- **WASM tools**: Our extension -- tools compiled to WASM for capability-based isolation (unique to Blackbeard)
- **MCP integration**: Register and manage MCP servers as tool sources

Do not reimplement search, scrape, file I/O, or other capabilities that CrewAI already provides as built-in tools.

---

## 2.2 Feature Ownership

| Capability | Owner | Blackbeard's Role |
|------------|-------|-------------------|
| Tool base class (`BaseTool`, `@tool`) | **CrewAI** | Use as-is -- do not reimplement |
| 50+ built-in tools (search, file I/O, RAG, etc.) | **CrewAI / crewai_tools** | Register in Blackbeard's catalogue for discoverability; do not fork |
| MCP integration (`crewai.mcp`) | **CrewAI** | Register MCP servers as resources; CrewAI handles the protocol |
| WASM tool format + WIT interface | **Blackbeard** | Build and maintain -- unique to Blackbeard |
| Tool registry UI (browse, search, install) | **Blackbeard** | Build and maintain |
| Tool governance (RBAC, rate limits, audit) | **Blackbeard** | Build and maintain |
| OAuth connector management | **Blackbeard** | Build and maintain (post-MVP) |

---

## 3. Tool Resource Schema

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: gmail-send
  labels:
    category: communication
    provider: google
  description: "Send emails via Gmail API"
spec:
  type: integration                   # python | wasm | mcp-stdio | mcp-http | rest | integration | composio | custom
  
  # ── Sandbox tier (optional, all tiers production-valid) ────
  sandbox: null                       # none | wasm | docker | microvm (null = use default for type)
  trusted: false                      # informational: is this first-party reviewed code?
  
  # ── Parameters (optional for Python tools  -- inferred from BaseTool.args_schema) ──
  parameters:                            # required for WASM tools (WIT interface is untyped)
    query:
      type: string
      required: true
      description: "Search query"
  
  # For type: python
  implementation: "crewai_tools:SerperDevTool"
  
  # For type: wasm
  wasm_module: "tools/sentiment.wasm" # path to compiled .wasm Component
  wasi_capabilities:                  # WASI capabilities this tool needs
    - "wasi:http/outgoing-handler"    # required for tools that make HTTP calls
    # - "wasi:filesystem/preopens"    # only if the tool reads/writes files
  fuel_limit: 1000000000              # instruction budget (wasmtime fuel)
  
  # For type: mcp-stdio
  command: "npx"
  args: ["@modelcontextprotocol/server-filesystem", "--root", "/data"]
  
  # For type: mcp-http
  url: "https://mcp.example.com/sse"
  transport: sse                      # sse | streamable-http
  
  # For type: rest
  openapi_spec: "specs/gmail-openapi.yaml"
  base_url: "https://gmail.googleapis.com"
  
  # For type: integration (OAuth-based)
  provider: gmail
  actions:
    - name: send_email
      description: "Send an email"
      parameters:
        to: { type: string, required: true }
        subject: { type: string, required: true }
        body: { type: string, required: true }
    - name: fetch_emails
      description: "Fetch recent emails"
      parameters:
        max_results: { type: integer, default: 10 }
  
  # Common fields
  auth:
    type: oauth2                      # none | api_key | oauth2 | bearer
    oauth_config:
      provider: google
      scopes: ["https://www.googleapis.com/auth/gmail.send"]
  env:
    - GMAIL_API_KEY
  rate_limit:
    max_rpm: 60
  max_concurrent: 10                  # max simultaneous invocations (default: 10)
  cache: true
  timeout: 30                         # seconds
```

For Python tools, `parameters` is optional. If omitted, parameters are inferred from the tool's `BaseTool.args_schema` Pydantic model at load time. For WASM tools, `parameters` is required because the WIT interface uses untyped `list<tuple<string, string>>`. Parameters are used for: PropertyPanel form generation, `blackbeard validate` input checking, and API documentation.

## 4. Integration Connectors (OAuth Apps)

Enterprise integrations that agents can use to interact with external services:

### 4.1 Supported Connectors

**v1 connectors** (shipped with initial release):

| Category | Connectors |
|----------|------------|
| **Developer** | GitHub |
| **Communication** | Slack, Gmail |

**Terminology note**: "v1" in this PRD refers to the first GA release (post-MVP). The MVP does not include OAuth integrations. See the MVP Implementation Plan for MVP scope.

**Roadmap connectors** (post-v1, community-driven):

| Category | Connectors |
|----------|------------|
| **Communication** | Microsoft Teams, Microsoft Outlook |
| **Project Management** | Jira, ClickUp, Asana, Linear, Notion |
| **CRM** | Salesforce, HubSpot, Zendesk |
| **Storage** | Google Drive, OneDrive, Box, SharePoint |
| **Productivity** | Google Sheets, Google Docs, Google Calendar, Microsoft Excel |
| **Commerce** | Shopify, Stripe |

### 4.2 Connector Configuration

```yaml
apiVersion: blackbeard/v1
kind: IntegrationConnector
metadata:
  name: gmail
spec:
  provider: google
  oauth:
    auth_url: "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: "https://oauth2.googleapis.com/token"
    client_id_env: GOOGLE_CLIENT_ID
    client_secret_env: GOOGLE_CLIENT_SECRET
    scopes:
      - "https://www.googleapis.com/auth/gmail.readonly"
      - "https://www.googleapis.com/auth/gmail.send"
  user_scoping: true                  # each user connects their own account
  actions:
    - name: send_email
      method: POST
      path: "/gmail/v1/users/me/messages/send"
    - name: fetch_emails
      method: GET
      path: "/gmail/v1/users/me/messages"
```

### 4.3 OAuth Connection Flow (UI)

1. User navigates to **Settings → Integrations**.
2. Clicks **Connect** on the desired connector.
3. Redirected to provider's OAuth consent screen.
4. On success, OAuth tokens are stored in Infisical (not Blackbeard's database). At execution time, the Execution Engine retrieves the OAuth token from Infisical using the tool's `auth.oauth_config.token_secret_path` field. Token refresh is handled by the Infisical SDK.
5. An **Integration Token** is generated for the user.
6. Agents reference integrations via the `apps` field or tool refs.

**`IntegrationConnector` is deferred to post-MVP.** The full OAuth flow above applies to v1 GA. See the MVP Implementation Plan for MVP scope.

**Token storage (MVP fallback):** The full product stores OAuth tokens in Infisical (PRD 00-integrations). MVP defers Infisical. For MVP, OAuth tokens are stored in an encrypted column in the `resources` table's `metadata` JSONB field under `metadata.oauth_state`. Encryption uses AES-256-GCM with a key derived from `BLACKBEARD_SECRET_KEY` env var. This is NOT the resource's `spec` ... OAuth state is mutable runtime data, not declarative configuration. Post-MVP migration: `blackbeard migrate-secrets` moves tokens from DB to Infisical.

## 5. MCP Server Management

### 5.1 Custom MCP Servers

Users can register their own MCP servers:

```yaml
apiVersion: blackbeard/v1
kind: MCPServer
metadata:
  name: internal-docs-server
spec:
  transport: stdio                    # stdio | sse | streamable-http
  command: "python"
  args: ["-m", "mycompany.mcp_server"]
  env:
    - DOCS_API_KEY
  auth:
    type: api_key
    header: "X-API-Key"
    key_env: MCP_SERVER_KEY
  health_check:
    enabled: true
    interval: 60                      # seconds
```

### 5.2 MCP Tool Discovery

When an MCP server is registered:
1. The system connects and calls `tools/list`.
2. Discovered tools are imported as `Tool` resources with `type: mcp-*`.
3. Tools are displayed in the registry with the MCP server as their source.
4. Users can selectively enable/disable discovered tools.

**MCP tool lifecycle:** When an MCP server's tool list changes (tools added, removed, or renamed), the changes are not automatically detected. Users must manually re-import tools via `blackbeard tools discover --mcp-server <name>`. Re-import is additive: new tools are created, existing tools are updated, but tools removed from the MCP server are NOT automatically deleted from Blackbeard (they are marked as `status: unavailable`). Automatic periodic re-sync is a post-v1 feature.

## 6. Registry UI (Post-MVP)

### 6.1 Browse & Search

- **Grid/List view** of all available tools.
- **Category filters**: Communication, Search, Storage, AI/ML, Database, etc.
- **Type filters**: Python, MCP, REST, Integration.
- **Search**: Fuzzy search by name, description, provider.
- **Sorting**: By name, popularity (usage count), date added.

### 6.2 Tool Detail Page

- Name, description, type badge, category.
- **Parameters**: Table of accepted parameters with types, defaults, descriptions.
- **Authentication**: What auth is required (OAuth, API key, none).
- **Usage examples**: Code snippets showing how to use in agent YAML.
- **Agent usage**: List of agents currently using this tool.
- **Metrics**: Invocation count, avg latency, error rate, cache hit rate.
- **Health status**: For MCP and REST tools  -- last health check result, uptime, error rate.

### 6.3 Install / Enable

- **One-click install** for marketplace tools (downloads Python package or registers MCP).
- **Enable per-crew**: Toggle which tools are available in each crew's runtime.
- **Configure**: Set required env vars, API keys, OAuth scopes.

## 7. Tool Repository (Post-MVP)

Users can publish tools to an internal repository:

- **Publish**: `blackbeard tool publish ./my-tool/` packages and registers the tool.
- **Versioning**: Tools are versioned (semver). Crews can pin specific versions.
- **Approval workflow**: Optional: tools require admin approval before being available org-wide.

```yaml
# Tool with version pinning in an agent
spec:
  tools:
    - ref: tools/serper-search@1.2.0
    - ref: tools/custom-db-query@latest
```

## 8. Security & Governance

- **RBAC**: Tools are resources governed by the RBAC system (PRD 03). Users need `tools` + `manage` to create/edit; `get`/`list` to view.
- **Scope isolation**: OAuth tokens are scoped per-user. An agent using Gmail uses the invoking user's token, not a shared one.
- **Secrets management**: API keys and tokens are stored encrypted (AES-256). Never exposed in YAML exports or traces.
- **Audit trail**: Every tool invocation is logged with caller, parameters (PII-redacted per PRD 07), and result status.
- **Rate limiting**: Per-tool rate limits enforced at the registry level.
- **Rate limit enforcement**: Tool rate limits are tracked in Valkey using a sliding-window counter keyed by `tool:{name}:rpm`. Counters are shared across all workers. When the limit is exceeded, the tool call returns a `429 Too Many Requests` error to the agent, which can retry after the window resets.
- **Concurrent invocation limits**: Per-tool concurrent execution is capped by `max_concurrent` (default: 10). This prevents a single tool from consuming all sandbox resources. Tracked in Valkey alongside RPM counters.

## 9. Events Emitted

| Event | Payload |
|-------|---------|
| `tool.registered` | `{name, type, version}` |
| `tool.invoked` | `{name, agent, parameters_hash, duration, status}` |
| `tool.error` | `{name, agent, error_type, message}` |
| `integration.connected` | `{provider, user}` |
| `integration.disconnected` | `{provider, user}` |
| `mcp.server.registered` | `{name, transport, tools_discovered}` |
| `mcp.server.health_failed` | `{name, error}` |

## 10. JIT Tool Discovery (Lazy Loading) (Post-MVP)

### Problem

The standard approach  -- passing all tool schemas into every LLM prompt  -- wastes context window and degrades model performance. An agent with access to 20 tools pays ~2,000 tokens of tool schema overhead on every call, even when it only needs 1-2 tools for the current step.

### Solution: Registry-as-a-Tool

Instead of injecting all tool schemas into the prompt, give the agent a single meta-tool: `search_tools`. The agent explores the registry on demand and selects tools JIT (just-in-time).

**Two built-in meta-tools provided to every agent:**

| Meta-Tool | Description | Returns |
|-----------|-------------|---------|
| `search_tools(query)` | Search the tool registry by keyword/capability | List of `{name, description, tags}` (no full schema) |
| `get_tool(name)` | Retrieve full schema + usage instructions for one tool | `{name, description, parameters, examples, constraints}` |

**Flow:**
1. Agent receives task: "Find the latest stock price for AAPL"
2. Agent calls `search_tools("stock price lookup")` → returns `[{name: "finance-api", description: "Query stock prices..."}]`
3. Agent calls `get_tool("finance-api")` → returns full parameter schema + examples
4. Agent calls `finance-api(symbol="AAPL")` → gets result
5. Next task: agent may use a completely different tool, discovered the same way

**RBAC filtering:** `search_tools` and `get_tool` only return tools the agent's policy allows. If an AgentPolicy restricts tools via `tools.mode: allowlist`, only allowed tools appear in search results. Denied tools are invisible  -- the agent doesn't know they exist.

### Context Window Impact

| Approach | Tokens per call | With 20 tools |
|----------|----------------|---------------|
| **All tools in prompt** | ~100 tokens/tool | ~2,000 tokens overhead on every call |
| **JIT discovery** | ~50 tokens (meta-tool schema) | ~50 tokens + ~150 when agent looks up a specific tool |

### Configuration

```yaml
kind: Crew
spec:
  tool_loading: jit          # jit | eager | hybrid
  # jit: only search_tools + get_tool in prompt (default)
  # eager: all agent tools in prompt (legacy behavior)
  # hybrid: core tools in prompt + search_tools for the rest
```

Per-agent override:
```yaml
kind: Agent
spec:
  tools:
    - ref:tools/web-search      # always in prompt (eager)
  tool_discovery: true          # also gets search_tools for additional tools
```

### Hybrid Mode

For agents that have a few "core" tools they always need (e.g., web search) plus access to a larger registry:
- Core tools: loaded eagerly into prompt
- Additional tools: discoverable via `search_tools`
- Best of both: fast access to common tools + lazy access to long tail

### Implementation Notes

- `search_tools` queries the Blackbeard resource API (`GET /api/v1/tools?search=...&namespace=...`) filtered by the agent's policy
- `get_tool` fetches the full tool spec (`GET /api/v1/tools/{name}`) and formats it as a tool schema
- Both meta-tools are registered as CrewAI tools that call back into the Blackbeard API
- Search is lightweight (~5ms)  -- no performance concern from repeated calls
- Tool schemas are cached per-execution to avoid redundant API calls within the same crew run

## 11. Acceptance Criteria

### MVP
1. Python tools can be registered via YAML and invoked by agents.
2. WASM tools can be compiled, registered, and invoked in the Wasmtime sandbox.
3. Secrets (API keys) are never exposed in API responses or YAML exports.

### Post-MVP
4. MCP servers (stdio and SSE) can be registered; their tools are auto-discovered and appear in the registry.
5. OAuth integrations (Gmail, Slack, GitHub) can be connected via the UI; agents can use connected integrations.
6. Registry UI shows all tools with search, filter, and detail views.
7. Tool rate limits are enforced; exceeding the limit returns a 429.
8. Tool versioning works: pinning `@1.2.0` uses that version even when `latest` is `2.0.0`.
9. RBAC controls who can register/edit/delete tools vs. who can only view and use them.
