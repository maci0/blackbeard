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
| `memory` | boolean | — | Enable cross-task memory |
| `cache` | boolean | — | Cache tool results |
| `system_template` | string | — | Custom system prompt template |
| `prompt_template` | string | — | Custom task prompt template |
| `response_template` | string | — | Custom response format template |

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
  output_pydantic: "myapp.models.Report"  # Parse output into this Pydantic model class path
  output_json:                             # JSON schema the output must conform to
    type: object
    properties:
      summary:
        type: string
  callback: "myapp.callbacks.on_complete"  # Python callable invoked after task finishes
  guardrails:                              # Guardrails applied to task output
    - "ref:guardrails/no-pii"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | ✅ | Task instructions; `{variable}` placeholders filled from crew inputs |
| `expected_output` | string | ✅ | Human-readable description of a correct result |
| `agent` | string | ✅ | `ref:` to the responsible agent |
| `context` | string[] | — | Tasks whose output is injected as additional context |
| `tools` | string[] | — | Tool refs that override the agent's default tools |
| `async_execution` | boolean | — | Run concurrently (default `false`) |
| `human_input` | boolean | — | Pause for human review (default `false`) |
| `output_file` | string | — | Write output to a file (flat filename, no path separators) |
| `output_pydantic` | string | — | Dotted class path to parse output into a Pydantic model |
| `output_json` | object | — | JSON Schema for structured output |
| `callback` | string | — | Dotted callable path invoked on completion |
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
| `memory` | boolean | — | Shared cross-agent memory |
| `cache` | boolean | — | Shared tool cache |
| `max_rpm` | integer ≥ 1 | — | Crew-wide LLM rate limit |
| `manager_llm` | string | — | LLM for the hierarchical manager |
| `manager_agent` | string | — | Custom manager agent (hierarchical) |
| `planning` | boolean | — | Pre-execution planning step |
| `planning_llm` | string | — | LLM used during planning |
| `default_agent_policy` | string | — | Default `AgentPolicy` ref for all agents |
| `inputs` | object[] | — | Runtime input declarations |
| `inputs[].name` | string | ✅ | Input variable name |
| `inputs[].description` | string | — | Description shown in UI |
| `inputs[].required` | boolean | — | Whether input is mandatory (default `true`) |
| `inputs[].default` | any | — | Default value when not provided |

### Inline Resources

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
  type: python                             # "python" or "wasm"

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

  # --- Optional (both types) ---
  config:                                  # Arbitrary config passed to the tool constructor
    result_n: 5
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `python`\|`wasm` | ✅ | Tool implementation type |
| `class_path` | string | — | Dotted path to Python `BaseTool` subclass (required for `python`) |
| `description` | string | — | Human-readable description of what the tool does |
| `sandbox` | `none`\|`wasm` | — | Sandbox enforcement level (default `none`) |
| `wasm_module` | string | — | Path to `.wasm` module file (required for `wasm`) |
| `capabilities` | string[] | — | WASI capability grants for WASM tools (e.g. `http_fetch`, `env`) |
| `config` | object | — | Constructor kwargs passed to the tool |

> **Note:** The `env` capability passes a safe default set of environment variables (PATH, HOME, USER, etc.). Granular per-variable access (`env:VAR_NAME`) is planned but not yet implemented.

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
| `api_key_env` | string | — | Env var name holding the API key |
| `base_url` | string | — | Custom API base URL |

> **Note:** Vertex AI project and region are configured in the LiteLLM proxy config (`deploy/litellm/config.yaml`), not in LLMConnection resources. The `vertex` section is optional — if omitted, the proxy's configuration is used.

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
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tools.mode` | `all`\|`allowlist`\|`denylist` | — | Tool access strategy |
| `tools.allow` | string[] | — | Allowed tool refs (used with `allowlist`) |
| `tools.deny` | string[] | — | Denied tool refs (used with `denylist`) |
| `budget.max_usd` | number ≥ 0 | — | Max spend in USD per execution |
| `budget.max_tokens` | integer ≥ 1 | — | Max total tokens per execution |
| `sandbox.minimum_tier` | `none`\|`wasm`\|`docker`\|`microvm` | — | Minimum sandbox isolation required |

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
  type: function                           # "function" (Python) or "llm" (LLM judge)

  # --- Optional ---
  description: "Reject outputs containing personally identifiable information"
  on_fail: reject                          # "reject", "warn", or "log" (default: "reject")

  # For type: function
  function_path: "myapp.guardrails.check_pii"  # Dotted path; receives output str, returns bool

  # For type: llm
  # type: llm
  # llm_prompt: >
  #   Does the following text contain PII? Answer YES or NO only.
  #   Text: {output}
  # llm: "ref:llm-connections/vertex-claude-sonnet"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `function`\|`llm` | ✅ | Guardrail implementation strategy |
| `description` | string | — | Human-readable description of what is being checked |
| `on_fail` | `reject`\|`warn`\|`log` | — | Action on validation failure (default `reject`) |
| `function_path` | string | — | Dotted path to Python callable `(output: str) -> bool` (required for `function`) |
| `llm_prompt` | string | — | Prompt template with `{output}` placeholder (required for `llm`) |
| `llm` | string | — | LLMConnection ref used for the LLM judge |
