# YAML Resource Reference

All Blackbeard resources share a common envelope:

```yaml
apiVersion: blackbeard/v1
kind: <Kind>          # One of the kinds listed below
metadata:
  name: <string>      # Unique name within the namespace (required)
  namespace: default  # Logical grouping; defaults to "default"
  labels:             # Arbitrary key/value pairs for filtering (optional)
    key: value
spec:                 # Kind-specific fields documented below
  ...
```

Cross-resource references use the `ref:` prefix:

```yaml
llm: "ref:llm-connections/vertex-claude-sonnet"
tools:
  - "ref:tools/web-search"
```

---

## Agent

An Agent is an AI actor with a defined role, goal, and optional tools.

```yaml
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
  namespace: default
  labels:
    role: research
spec:
  # --- Required ---
  role: "Senior Research Analyst"          # The agent's job title / role description
  goal: "Conduct thorough research on a given topic"  # What the agent is trying to achieve
  backstory: >                             # Personality and background context fed to the LLM
    You are an experienced research analyst with a keen eye for detail.

  # --- Optional ---
  llm: "ref:llm-connections/vertex-claude-sonnet"  # LLMConnection to use (ref or model string)
  tools:                                   # Tools the agent can invoke
    - "ref:tools/web-search"
  allow_delegation: false                  # Allow the agent to delegate sub-tasks (default: false)
  verbose: true                            # Log agent reasoning steps (default: true)
  max_iter: 10                             # Maximum reasoning iterations before stopping
  max_rpm: 30                              # Maximum LLM requests per minute
  memory: true                             # Enable short-term memory between tasks
  cache: true                              # Cache tool results
  system_template: "You are {role}..."     # Override the system prompt template
  prompt_template: "Task: {task}..."       # Override the human prompt template
  response_template: "Output: {output}"   # Override the response format template
  serviceAccount: "sa-researcher"          # Service account identity for RBAC (default: sa-<name>)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | ✅ | Agent's job title used in prompts |
| `goal` | string | ✅ | What the agent strives to accomplish |
| `backstory` | string | ✅ | Personality/background context for the agent |
| `llm` | string | — | LLM to use; ref or literal model string |
| `tools` | string[] | — | List of `ref:` tool references |
| `allow_delegation` | boolean | — | Whether agent can delegate to others (default `false`) |
| `verbose` | boolean | — | Log chain-of-thought (default `true`) |
| `max_iter` | integer ≥ 1 | — | Max reasoning iterations |
| `max_rpm` | integer ≥ 1 | — | Rate limit for LLM calls |
| `memory` | boolean\|object | — | Enable cross-task memory; object form supports `enabled`, `recency_weight`, `semantic_weight`, `importance_weight` |
| `cache` | boolean | — | Cache tool results |
| `policy` | string | — | `ref:` to an AgentPolicy resource (stored but not yet enforced at runtime) |
| `tool_discovery` | boolean | — | Allow JIT tool discovery via meta-tools (default `true`) |
| `skills` | string[] | — | Directory paths with domain instruction files |
| `knowledge_sources` | string[] | — | `ref:` KnowledgeSource resources for RAG |
| `system_template` | string | — | Custom system prompt template (stored but not yet passed to CrewAI at runtime) |
| `prompt_template` | string | — | Custom task prompt template (stored but not yet passed to CrewAI at runtime) |
| `response_template` | string | — | Custom response format template (stored but not yet passed to CrewAI at runtime) |
| `serviceAccount` | string | — | Service account identity used for RBAC principal chain during execution (default `sa-<name>`); must match `^[a-z0-9][a-z0-9\-]*$` |

---

## Task

A Task is a unit of work assigned to a specific agent.

```yaml
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: research-topic
  namespace: default
spec:
  # --- Required ---
  description: >                           # What the agent must do; supports {input} variables
    Research the topic: {topic}
    Provide analysis including current state, key players, and future outlook.
  expected_output: >                       # Describes the format/content of a successful result
    A detailed research brief with data points and references.
  agent: "ref:agents/researcher"           # The agent responsible for this task

  # --- Optional ---
  context:                                 # Output of these tasks is injected as context
    - "ref:tasks/prior-research"
  tools:                                   # Override agent tools for this task only
    - "ref:tools/web-search"
  async_execution: false                   # Run task concurrently with others (default: false)
  human_input: false                       # Pause and wait for human review (default: false)
  output_file: "report.md"                 # Write task output to this file path
  output_pydantic: "crewai.models.Report"  # Parse output into this Pydantic model class path
  output_json:                             # JSON schema the output must conform to
    type: object
    properties:
      summary:
        type: string
  callback: "crewai.callbacks.on_complete"  # Python callable invoked after task finishes
  guardrails:                              # Guardrails applied to task output
    - "ref:guardrails/no-pii"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | ✅ | Task instructions; `{variable}` placeholders filled from crew inputs |
| `expected_output` | string | ✅ | Human-readable description of a correct result |
| `agent` | string | ✅ | `ref:` to the responsible agent |
| `context` | string[] | — | Tasks whose output is injected as additional context |
| `tools` | string[] | — | Tool refs that override the agent's default tools (stored but not yet passed to CrewAI at runtime) |
| `async_execution` | boolean | — | Run concurrently (default `false`) |
| `human_input` | boolean | — | Pause for human review (default `false`) |
| `output_file` | string | — | Write output to a file (flat filename, no path separators) |
| `output_pydantic` | string | — | Dotted class path to parse output into a Pydantic model (stored but not yet passed to CrewAI at runtime) |
| `output_json` | object | — | JSON Schema for structured output (stored but not yet passed to CrewAI at runtime) |
| `callback` | string | — | Dotted callable path invoked on completion (stored but not yet passed to CrewAI at runtime) |
| `guardrails` | string[] | — | `ref:` guardrail resources applied to output |

---

## Crew

A Crew orchestrates agents and tasks, defining execution order and shared configuration.

```yaml
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: research-crew
  namespace: default
  labels:
    type: research
spec:
  # --- Required ---
  process: sequential                      # Execution strategy: "sequential" or "hierarchical"
  agents:                                  # Ordered list of agent refs
    - "ref:agents/researcher"
    - "ref:agents/writer"
  tasks:                                   # Ordered list of task refs
    - "ref:tasks/research-topic"
    - "ref:tasks/write-report"

  # --- Optional ---
  description: "Researches a topic and produces a report"
  verbose: true                            # Enable verbose logging (default: true)
  memory: false                            # Shared memory across agents
  cache: true                              # Shared tool cache
  max_rpm: 60                              # Crew-wide LLM rate limit
  manager_llm: "ref:llm-connections/vertex-claude-sonnet"  # LLM for hierarchical manager
  manager_agent: "ref:agents/coordinator"  # Custom manager agent (hierarchical only)
  planning: false                          # Enable pre-execution planning step
  planning_llm: "ref:llm-connections/vertex-claude-sonnet"  # LLM used for planning
  default_agent_policy: "ref:agent-policies/standard"  # Policy applied to all agents
  inputs:                                  # Declare runtime inputs accepted by this crew
    - name: topic
      description: "The topic to research"
      required: true
    - name: language
      description: "Output language"
      required: false
      default: "English"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `process` | `sequential`\|`hierarchical` | ✅ | Execution strategy |
| `agents` | string[] (≥1) | ✅ | Ordered agent `ref:` list |
| `tasks` | string[] (≥1) | ✅ | Ordered task `ref:` list |
| `description` | string | — | Human-readable description |
| `verbose` | boolean | — | Verbose logging (default `true`) |
| `memory` | boolean\|object | — | Shared cross-agent memory; object form supports `enabled`, `provider` (`lancedb`\|`chromadb`\|`qdrant`), `config` |
| `embedder` | object | — | Embedder config for RAG (`provider`, `config`) |
| `cache` | boolean | — | Shared tool cache |
| `max_rpm` | integer ≥ 1 | — | Crew-wide LLM rate limit |
| `manager_llm` | string | — | LLM for the hierarchical manager |
| `manager_agent` | string | — | Custom manager agent (hierarchical; stored but not yet passed to CrewAI at runtime) |
| `planning` | boolean | — | Pre-execution planning step (stored but not yet passed to CrewAI at runtime) |
| `planning_llm` | string | — | LLM used during planning (stored but not yet passed to CrewAI at runtime) |
| `tool_loading` | `jit`\|`eager`\|`hybrid` | — | Tool loading strategy (default `hybrid`) |
| `default_agent_policy` | string | — | Default `AgentPolicy` ref for all agents |
| `inputs` | object[] | — | Runtime input declarations |
| `inputs[].name` | string | ✅ | Input variable name |
| `inputs[].description` | string | — | Description shown in UI |
| `inputs[].required` | boolean | — | Whether input is mandatory (default `true`) |
| `inputs[].default` | any | — | Default value when not provided |
| `inline` | object | — | Embed agents, tasks, and LLM connections directly in the crew YAML (see below) |
| `a2a` | object | — | Agent-to-Agent protocol configuration |
| `a2a.enabled` | boolean | — | Enable A2A protocol (default `false`) |
| `a2a.protocol_versions` | string[] | — | Supported protocol versions |
| `a2a.transports` | string[] | — | Supported transport protocols (`json-rpc`, `grpc`) |
| `a2a.auth` | string | — | Authentication configuration |
| `a2a.public` | boolean | — | Whether the crew is publicly discoverable (default `false`) |

### Inline Resources

> **Note:** For MVP, inline resources are accepted by the schema and stored, but are **not yet expanded at runtime**. You must still create agents, tasks, and LLM connections as separate resources and reference them via `ref:` strings in the `agents` and `tasks` lists.

For simple crews, you can embed agents, tasks, and LLM connections directly in the crew YAML using the `inline` field instead of separate resource files:

```yaml
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: simple-crew
spec:
  process: sequential
  inline:
    llm_connections:
      - name: default-llm
        provider: vertex_ai
        model: claude-sonnet-4-6
    agents:
      - name: researcher
        role: Researcher
        goal: Research topics thoroughly
        backstory: "A skilled researcher with deep expertise."
        llm: default-llm
    tasks:
      - name: research-task
        description: Research the given topic
        agent: researcher
        expected_output: A comprehensive report
  agents:
    - researcher
  tasks:
    - research-task
```

See `examples/simple-crew/crew.yaml` for a complete example.

---

## Tool

A Tool is a callable capability available to agents.

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: web-search
  namespace: default
  labels:
    category: search
spec:
  # --- Required ---
  type: python                             # "python", "wasm", "builtin", "mcp-stdio", or "mcp-http"

  # --- For type: python ---
  class_path: crewai_tools.SerperDevTool  # Dotted import path to a BaseTool subclass
  description: "Search the web for current information"
  sandbox: none                            # Sandbox level: "none" or "wasm" (default: "none")

  # --- For type: wasm ---
  # type: wasm
  # wasm_module: "tools/my_tool.wasm"     # Path to compiled WASM module
  # capabilities:                          # WASI capability grants
  #   - "http_fetch"
  #   - "env"

  # --- For type: mcp-stdio ---
  # type: mcp-stdio
  # command: "npx"                        # Command to launch the MCP server
  # args: ["-y", "@modelcontextprotocol/server-filesystem"]
  # env:                                  # Environment variables for the MCP server process
  #   HOME: /tmp

  # --- For type: mcp-http ---
  # type: mcp-http
  # url: "http://localhost:3001/mcp"      # URL of the running MCP HTTP server

  # --- Optional (all types) ---
  config:                                  # Arbitrary config passed to the tool constructor
    result_n: 5
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `python`\|`wasm`\|`builtin`\|`mcp-stdio`\|`mcp-http` | ✅ | Tool implementation type |
| `class_path` | string | — | Dotted path to Python `BaseTool` subclass (required for `python`; tool name for `builtin`) |
| `description` | string | — | Human-readable description of what the tool does |
| `sandbox` | `none`\|`wasm` | — | Sandbox enforcement level (default `none`) |
| `wasm_module` | string | — | Path to `.wasm` module file (required for `wasm`) |
| `capabilities` | string[] | — | WASI capability grants for WASM tools (e.g. `http_fetch`, `env`) |
| `command` | string | — | Command to launch the MCP server (required for `mcp-stdio`) |
| `args` | string[] | — | Arguments for the MCP server command (`mcp-stdio`) |
| `url` | string | — | URL of the MCP HTTP server (required for `mcp-http`) |
| `env` | object | — | Environment variables for the MCP server process (`mcp-stdio`) |
| `config` | object | — | Constructor kwargs passed to the tool |

> **Note:** The `env` capability passes a fixed set of safe environment variables (`LANG`, `LC_ALL`, `TZ`, `TERM`). Granular per-variable access is not supported.

---

## LLMConnection

An LLMConnection configures access to a language model via LiteLLM.

```yaml
apiVersion: blackbeard/v1
kind: LLMConnection
metadata:
  name: vertex-claude-sonnet
  namespace: default
  labels:
    provider: vertex-ai
    tier: standard
spec:
  # --- Required ---
  provider: vertex_ai                      # LiteLLM provider string
  model: claude-sonnet-4-6                 # Model name within the provider

  # --- Optional ---
  parameters:
    temperature: 0.7                       # Sampling temperature (0–2)
    max_tokens: 4096                       # Maximum output tokens
    top_p: 0.95                            # Nucleus sampling probability (0–1)
    frequency_penalty: 0.0                 # Penalise repeated tokens
    presence_penalty: 0.0                  # Penalise tokens already present
    stop:                                  # Stop sequences
      - "\n\nHuman:"

  # Vertex AI-specific settings
  vertex:
    project: "${GOOGLE_CLOUD_PROJECT}"     # GCP project ID
    location: "${CLOUD_ML_REGION}"         # GCP region, e.g. "us-east5"

  # Generic provider settings
  api_key_env: "OPENAI_API_KEY"           # Env var containing the API key
  base_url: "https://api.openai.com/v1"  # Override the provider base URL
```

> **Note:** The `api_key_env` value is read by the LiteLLM proxy at runtime, not at resource creation time. The proxy must have the specified environment variable set.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | ✅ | LiteLLM provider identifier (e.g. `vertex_ai`, `openai`, `anthropic`) |
| `model` | string | ✅ | Model name within the provider |
| `parameters.temperature` | number 0–2 | — | Sampling temperature |
| `parameters.max_tokens` | integer ≥ 1 | — | Maximum response tokens |
| `parameters.top_p` | number 0–1 | — | Nucleus sampling |
| `parameters.frequency_penalty` | number | — | Frequency penalty |
| `parameters.presence_penalty` | number | — | Presence penalty |
| `parameters.stop` | string[] | — | Stop sequences |
| `vertex.project` | string | — | GCP project (Vertex AI only) |
| `vertex.location` | string | — | GCP region (Vertex AI only) |
| `api_key_env` | string | — | Env var name holding the API key (must be uppercase, ending in `_API_KEY`, `_KEY`, or `_SECRET`) |
| `base_url` | string | — | Custom API base URL |

> **Note:** The `vertex` section is optional. If `vertex.project` or `vertex.location` are omitted, they fall back to the global `GOOGLE_CLOUD_PROJECT` and `CLOUD_ML_REGION` environment variables.

---

## AgentPolicy

An AgentPolicy defines governance rules — tool access, spending budgets, and sandbox requirements — that are enforced at execution time.

```yaml
apiVersion: blackbeard/v1
kind: AgentPolicy
metadata:
  name: standard-policy
  namespace: default
spec:
  # Tool access control
  tools:
    mode: allowlist                        # "all", "allowlist", or "denylist"
    allow:                                 # Permitted tools (for mode: allowlist)
      - "ref:tools/web-search"
      - "ref:tools/calculator"
    deny:                                  # Blocked tools (for mode: denylist)
      - "ref:tools/shell-exec"

  # Spending limits (approximate; enforced via LiteLLM cost tracking)
  budget:
    max_usd: 1.00                          # Maximum spend in USD per execution
    max_tokens: 100000                     # Maximum total tokens per execution

  # Sandbox enforcement
  sandbox:
    minimum_tier: wasm                     # "none", "wasm", "docker", or "microvm"

  # Delegation control
  delegation:
    allowed: true                          # Whether agent-to-agent delegation is permitted
    targets:                               # Restrict which agents can be delegated to (optional)
      - "ref:agents/researcher"
      - "ref:agents/writer"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tools.mode` | `all`\|`allowlist`\|`denylist` | — | Tool access strategy |
| `tools.allow` | string[] | — | Allowed tool refs (used with `allowlist`) |
| `tools.deny` | string[] | — | Denied tool refs (used with `denylist`) |
| `budget.max_usd` | number ≥ 0 | — | Max spend in USD per execution |
| `budget.max_tokens` | integer ≥ 1 | — | Max total tokens per execution |
| `sandbox.minimum_tier` | `none`\|`wasm`\|`docker`\|`microvm` | — | Minimum sandbox isolation required |
| `delegation.allowed` | boolean | — | Whether agent-to-agent delegation is permitted |
| `delegation.targets` | string[] | — | Restrict which agents can receive delegated work (refs) |

> **Note:** For MVP, only `none` and `wasm` sandbox tiers are implemented. `docker` and `microvm` are accepted by the schema but fall back to `wasm` at runtime.

---

## Guardrail

A Guardrail validates or filters task output. Attach guardrails to tasks to enforce output safety, format, or content policies.

```yaml
apiVersion: blackbeard/v1
kind: Guardrail
metadata:
  name: no-pii
  namespace: default
spec:
  # --- Required ---
  type: function                           # "function", "llm", or "schema"

  # --- Optional ---
  description: "Reject outputs containing personally identifiable information"
  on_fail: reject                          # "reject", "warn", or "log" (default: "reject")

  # For type: function
  function_path: "blackbeard.guardrails.check_pii"  # Dotted path; receives output str, returns bool

  # For type: llm
  # type: llm
  # llm_prompt: >
  #   Does the following text contain PII? Answer YES or NO only.
  #   Text: {output}
  # llm: "ref:llm-connections/vertex-claude-sonnet"

  # For type: schema
  # type: schema
  # json_schema:                           # JSON Schema the output must conform to
  #   type: object
  #   required: [summary, confidence]
  #   properties:
  #     summary:
  #       type: string
  #     confidence:
  #       type: number
  #       minimum: 0
  #       maximum: 1
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `function`\|`llm`\|`schema` | ✅ | Guardrail implementation strategy |
| `description` | string | — | Human-readable description of what is being checked |
| `on_fail` | `reject`\|`warn`\|`log` | — | Action on validation failure (default `reject`) |
| `function_path` | string | — | Dotted path to Python callable `(output: str) -> bool` (required for `function`) |
| `llm_prompt` | string | — | Prompt template with `{output}` placeholder (required for `llm`) |
| `llm` | string | — | LLMConnection ref used for the LLM judge |
| `json_schema` | object | — | JSON Schema to validate output against (required for `schema`) |

---

## Flow

A Flow orchestrates multiple crews and functions into a multi-step pipeline with state passing.

```yaml
apiVersion: blackbeard/v1
kind: Flow
metadata:
  name: research-pipeline
  namespace: default
spec:
  # --- Required ---
  steps:
    - name: research
      type: crew
      crew: "ref:crews/research-crew"
    - name: summarize
      type: crew
      crew: "ref:crews/summary-crew"
      listen_to: [research]
    - name: route-output
      type: router
      listen_to: [summarize]
      routes:
        short: next-step-a
        long: next-step-b

  # --- Optional ---
  description: "End-to-end research and summary pipeline"
  state_schema:                            # JSON Schema for the shared flow state
    type: object
    properties:
      topic: { type: string }
  memory: false                            # Enable flow-level memory (default: false)
  verbose: true                            # Verbose logging (default: true)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `steps` | object[] (≥1) | ✅ | Ordered list of flow steps |
| `steps[].name` | string | ✅ | Step identifier |
| `steps[].type` | `crew`\|`function`\|`router`\|`condition` | ✅ | Step type |
| `steps[].crew` | string | — | Crew ref (required for `crew` steps) |
| `steps[].function_path` | string | — | `module:function` path (required for `function` steps) |
| `steps[].listen_to` | string[] | — | Steps whose completion triggers this step |
| `steps[].condition` | string | — | Condition expression (for `condition` steps) |
| `steps[].routes` | object | — | Named routes mapping to step names (for `router` steps) |
| `description` | string | — | Human-readable description |
| `state_schema` | object | — | JSON Schema for shared flow state |
| `memory` | boolean | — | Flow-level memory (default `false`) |
| `verbose` | boolean | — | Verbose logging (default `true`) |

---

## KnowledgeSource

A KnowledgeSource provides RAG-accessible content to agents. Attach knowledge sources to agents via the `knowledge_sources` field.

```yaml
apiVersion: blackbeard/v1
kind: KnowledgeSource
metadata:
  name: product-docs
  namespace: default
spec:
  # --- Required ---
  type: text                               # "text", "pdf", "csv", "json", "excel", "string", or "url"

  # --- For file-based types (text, pdf, csv, json, excel) ---
  file_paths:
    - "docs/product-manual.txt"
    - "docs/faq.txt"

  # --- For type: string ---
  # content: "Inline knowledge content goes here..."

  # --- Optional ---
  description: "Product documentation for RAG"
  chunk_size: 4000                         # Chunk size for text splitting (default: 4000)
  chunk_overlap: 200                       # Overlap between chunks (default: 200)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `text`\|`pdf`\|`csv`\|`json`\|`excel`\|`string`\|`url` | ✅ | Knowledge source format (see note below) |
| `description` | string | — | Human-readable description |
| `file_paths` | string[] | — | Paths to source files (required for file-based types) |
| `content` | string | — | Inline text content (required for `string` type) |
| `urls` | string[] | — | URLs to fetch content from (for `url` type) |
| `chunk_size` | integer 100–10000 | — | Text chunk size (default `4000`) |
| `chunk_overlap` | integer 0–1000 | — | Overlap between chunks (default `200`) |

> **Note:** For MVP, only `text`, `pdf`, `csv`, `json`, and `string` types are supported at runtime. `excel` and `url` are accepted by the schema but not yet handled by the resource loader.

---

## Role

A Role defines a set of permissions (resource/verb pairs) for RBAC. Bind roles to subjects via RoleBindings.

```yaml
apiVersion: blackbeard/v1
kind: Role
metadata:
  name: developer
  namespace: default
spec:
  description: "Create and manage agents, tasks, crews, and tools"
  rules:
    - resources: ["Agent", "Task", "Crew", "Tool", "LLMConnection"]
      verbs: ["get", "list", "create", "update", "delete"]
    - resources: ["Crew"]
      verbs: ["run"]
    - resources: ["AgentPolicy", "Guardrail"]
      verbs: ["get", "list"]
  subjectKinds: ["User"]                  # Restrict which subject types can use this role (optional)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | — | Human-readable description |
| `rules` | object[] (≥1) | ✅ | Permission rules |
| `rules[].resources` | string[] (≥1) | ✅ | Resource kind names (e.g. `"Agent"`, `"Crew"`) or `"*"` for all |
| `rules[].verbs` | string[] (≥1) | ✅ | Allowed operations: `get`, `list`, `create`, `update`, `delete`, `run`, `invoke`, `delegate`, or `*` |
| `rules[].resourceNames` | string[] | — | Restrict rule to specific resource names |
| `rules[].namespaces` | string[] | — | Restrict rule to specific namespaces |
| `subjectKinds` | string[] | — | Restrict which subject types can use this role: `User`, `Group`, `Agent`, `Crew` |

---

## RoleBinding

A RoleBinding binds a Role to one or more subjects (users, groups, agents, or crews), granting them the role's permissions.

```yaml
apiVersion: blackbeard/v1
kind: RoleBinding
metadata:
  name: dev-team-binding
  namespace: default
spec:
  role: "ref:roles/developer"
  subjects:
    - kind: User
      name: alice@example.com
    - kind: Group
      name: engineering
    - kind: Agent
      name: researcher
  scope:
    namespace: default                    # Limit permissions to this namespace (optional)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | ✅ | `ref:` to the Role resource to bind |
| `subjects` | object[] (≥1) | ✅ | Subjects receiving the role's permissions |
| `subjects[].kind` | `User`\|`Group`\|`Agent`\|`Crew` | ✅ | Subject type |
| `subjects[].name` | string | ✅ | Subject identifier (email for users, resource name for agents/crews) |
| `scope.namespace` | string | — | Limit the binding to a specific namespace |
