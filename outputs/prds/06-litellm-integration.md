# PRD 06 — LiteLLM Integration

## 1. Purpose

Instead of building a custom LLM dispatcher, Blackbeard routes **all** LLM traffic through a co-deployed **LiteLLM Proxy**. This gives us model routing, load balancing, fallbacks, spend tracking, per-agent budget enforcement, and 100+ provider support — all without writing or maintaining provider-specific code.

Blackbeard's job is to:
1. Generate and manage LiteLLM configuration from Blackbeard's resource model.
2. Map AgentPolicies (PRD 03) to LiteLLM virtual keys with budgets and model access controls.
3. Consume LiteLLM's spend data for Blackbeard's observability dashboards (PRD 07).
4. Expose a simplified LLM management UI that writes to LiteLLM's config.

### 1.1 MVP Scope

**Implemented:** Fully implemented. LiteLLM Proxy co-deployed as a sidecar container, automatic config generation from `LLMConnection` resources, per-execution virtual key lifecycle (create on kickoff, delete on completion), spend tracking per key/user/model, per-user LiteLLM registration on Blackbeard user creation, LiteLLM dashboard accessible at `:4000/ui`. All LLM calls route through the proxy with no direct provider calls.

**Deferred to post-MVP:** Advanced routing strategies (`LLMRoutingConfig` resource), standalone/external deployment topologies, tag-based routing, Blackbeard-side spend dashboards (LiteLLM dashboard serves this role for now).

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Blackbeard Execution Worker                │
│                                                              │
│  CrewAI Agent calls llm.completion(model="gpt-4o", ...)      │
│       │                                                      │
│       │  CrewAI's LLM class configured with:                 │
│       │    api_base = "http://litellm-proxy:4000"            │
│       │    api_key  = <agent's virtual key>                  │
│       │                                                      │
│       ▼                                                      │
│  ┌────────────────────────────────────────────┐              │
│  │           LiteLLM Proxy (:4000)            │              │
│  │                                            │              │
│  │  ┌──────────────┐  ┌──────────────────┐    │              │
│  │  │ Virtual Key   │  │ Router           │    │              │
│  │  │ Validation    │  │                  │    │              │
│  │  │               │  │ • Load balancing │    │              │
│  │  │ • Budget check│  │ • Fallbacks      │    │              │
│  │  │ • Rate limit  │  │ • Routing strat. │    │              │
│  │  │ • Model access│  │ • Health checks  │    │              │
│  │  └──────┬───────┘  └──────┬───────────┘    │              │
│  │         │                 │                │              │
│  │         ▼                 ▼                │              │
│  │  ┌──────────────────────────────────┐      │              │
│  │  │       Provider Dispatch          │      │              │
│  │  │                                  │      │              │
│  │  │  OpenAI │ Anthropic │ Gemini │   │      │              │
│  │  │  Azure  │ Bedrock   │ Groq   │   │      │              │
│  │  │  Ollama │ vLLM      │ 100+   │   │      │              │
│  │  └──────────────────────────────────┘      │              │
│  │                                            │              │
│  │  ┌──────────────────────────────────┐      │              │
│  │  │       Spend Tracking             │      │              │
│  │  │  Per key / user / team / model   │      │              │
│  │  └──────────────────────────────────┘      │              │
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
```

## 3. LLMConnection → LiteLLM Model Config

Blackbeard's `LLMConnection` resource (PRD 01) maps to entries in LiteLLM's `model_list`:

```yaml
# Blackbeard resource
apiVersion: blackbeard/v1
kind: LLMConnection
metadata:
  name: openai-gpt4o
  labels:
    provider: openai
    tier: production
spec:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
  rpm: 200                            # requests per minute
  tpm: 100000                         # tokens per minute
  timeout: 120
  
  # Routing & fallbacks
  fallback_to: 
    - ref: llm-connections/anthropic-claude-sonnet
  context_window_fallback: 
    - ref: llm-connections/openai-gpt4o-mini   # cheaper, larger context

  # Load balancing: multiple deployments of the same model
  deployments:
    - name: openai-primary
      api_key_env: OPENAI_API_KEY
      rpm: 200
    - name: openai-secondary
      api_key_env: OPENAI_API_KEY_2
      rpm: 200
```

**Blackbeard generates this LiteLLM config automatically:**

```yaml
# Auto-generated litellm config.yaml
model_list:
  - model_name: openai-gpt4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
      rpm: 200
      tpm: 100000
  - model_name: openai-gpt4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY_2
      rpm: 200
      tpm: 100000

litellm_settings:
  fallbacks: [{"openai-gpt4o": ["anthropic-claude-sonnet"]}]
  context_window_fallbacks: [{"openai-gpt4o": ["openai-gpt4o-mini"]}]
  num_retries: 3
  request_timeout: 120

router_settings:
  routing_strategy: usage-based-routing
  redis_host: "${VALKEY_HOST:-valkey}"   # LiteLLM uses Redis protocol; connects to Valkey
  redis_port: 6379
  redis_password: "${VALKEY_PASSWORD:-}"  # required if Valkey has auth enabled
```

**Users never edit LiteLLM config directly** — they manage `LLMConnection` resources in Blackbeard, and Blackbeard regenerates the LiteLLM config on every change.

### Config Lifecycle

1. **Generation**: On `LLMConnection` create/update/delete, regenerate `litellm_config.yaml` to a temporary file
2. **Validation**: Schema-validate the generated YAML against LiteLLM's config schema
3. **Concurrency**: Acquire a Valkey distributed lock (`blackbeard:litellm:config-lock`, TTL 30s) before generation. Prevents two concurrent `LLMConnection` updates from producing a corrupted config.
4. **Reload**: Call `POST /config/update` on LiteLLM Proxy with the new config
5. **Rollback**: If LiteLLM rejects the config (400 response), release the lock, preserve the old config, and return 422 to the user with LiteLLM's error message
6. **Startup ordering**: docker-compose `depends_on` with healthcheck ensures LiteLLM is ready before Blackbeard generates initial config. On first startup with no `LLMConnection` resources, generate a minimal valid config.
7. **In-flight requests**: LiteLLM handles config reload atomically, so in-flight requests complete with the old config and new requests use the new config.

## 4. AgentPolicy → LiteLLM Virtual Keys

The key integration: Blackbeard maps each agent's policy constraints to a **LiteLLM virtual key** with matching budgets, rate limits, and model access.

### 4.1 Key Lifecycle

```
Agent kickoff
    │
    ▼
┌────────────────────────────────────────┐
│  Blackbeard Policy Resolver            │
│                                        │
│  1. Resolve agent's AgentPolicy        │
│  2. Determine allowed LLM connections  │
│  3. Calculate budget ceilings          │
│  4. Create or reuse LiteLLM virtual key│
└────────┬───────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  LiteLLM POST /key/generate            │
│                                        │
│  {                                     │
│    "models": ["openai-gpt4o",          │
│               "anthropic-claude-sonnet"],│
│    "max_budget": 5.00,                 │
│    "budget_duration": "1d",            │
│    "tpm_limit": 100000,               │
│    "rpm_limit": 60,                    │
│    "metadata": {                       │
│      "blackbeard_agent": "researcher", │
│      "blackbeard_execution": "exec-123",│
│      "blackbeard_user": "alice@..."    │
│    }                                   │
│  }                                     │
│                                        │
│  → key: "sk-agent-researcher-exec123"  │
└────────────────────────────────────────┘
```

### 4.2 Policy → Key Mapping

| AgentPolicy Field | LiteLLM Virtual Key Field |
|-------------------|--------------------------|
| `llm.allow` (list of LLMConnection refs) | `models` (list of model aliases) |
| `llm.deny` (blocked models) | Excluded from `models` |
| `llm.max_cost_per_execution_usd` | `max_budget` |
| `llm.max_tokens_per_execution` | `max_budget` (estimated from token pricing) |
| `llm.max_tokens_per_task` | Enforced by Blackbeard's policy enforcer (LiteLLM doesn't have per-call token budgets) |
| `resource_limits.max_rpm` | `rpm_limit` |
| Agent name, execution ID, user ID | `metadata` (for spend attribution) |

### 4.3 Key Scoping

| Scope | Strategy | Lifecycle |
|-------|----------|-----------|
| **Per-execution** | New key for each `kickoff()` | Deleted after execution completes |
| **Per-agent** | Reuse key across executions of the same agent | Long-lived, budget resets on duration |
| **Per-crew** | Shared key for all agents in a crew | Deleted after crew execution |
| **Per-user** | One key per human user, shared across their agent runs | Long-lived |

**Budget reset semantics by scope:**

| Scope | Budget Lifecycle | Reset Trigger |
|-------|-----------------|---------------|
| Per-execution | Key created at kickoff, deleted on completion. Budget = single execution ceiling. | Automatic on execution end |
| Per-agent | Key persists across executions. Budget resets based on `budget_duration`. | Timer-based (e.g., `1d` = midnight UTC reset) |
| Per-crew | Key shared by all agents in a crew across executions. | Timer-based |
| Per-user | Key shared by all executions initiated by a user. | Timer-based |

Per-agent with `budget_duration: 1d` means the agent can spend up to `max_budget` USD per 24-hour period across all executions. Budget enforcement is real-time via LiteLLM — the agent receives a 429 when exceeded.

**Key cleanup**: Per-execution keys are deleted via `DELETE /key/delete` when the execution completes (success or failure). A background sweeper runs every hour to garbage-collect orphaned keys (executions that crashed without cleanup). Keys older than 24h with no recent spend are candidates for GC.

Default: **per-execution** (strictest isolation). Configurable in AgentPolicy:

```yaml
spec:
  llm:
    key_scope: per-execution          # per-execution | per-agent | per-crew | per-user
```

### 4.4 What Happens When Budget is Exceeded

1. LiteLLM rejects the request with `BudgetExceededError`.
2. Blackbeard's CrewAI event listener catches the LLM error.
3. The error is mapped to `agent.policy.budget_exceeded` event.
4. The agent receives a system message: `"LLM budget exceeded ($5.00 limit reached). Execution stopped."`
5. The execution transitions to `failed` with a clear budget error.
6. The trace records the budget exceeded event with spend breakdown.

## 5. Routing Strategies

LiteLLM supports these out of the box — Blackbeard exposes them as configuration:

```yaml
apiVersion: blackbeard/v1
kind: LLMRoutingConfig
metadata:
  name: production-routing
spec:
  strategy: usage-based-routing        # simple-shuffle | least-busy | usage-based-routing | latency-based-routing
  
  # Model aliases: requests for "gpt-4" route to "gpt-4o" deployments
  model_aliases:
    "gpt-4": "openai-gpt4o"
    "claude": "anthropic-claude-sonnet"
  
  # Fallback chain
  fallbacks:
    - from: openai-gpt4o
      to: [anthropic-claude-sonnet, openai-gpt4o-mini]
    - from: anthropic-claude-sonnet
      to: [openai-gpt4o, openai-gpt4o-mini]
  
  # Context window fallbacks (auto-switch to larger context model)
  context_window_fallbacks:
    - from: openai-gpt4o
      to: openai-gpt4o-mini            # 128k context
  
  # Tag-based routing (e.g., route "fast" tagged requests to Groq)
  tag_routing:
    fast: [groq-llama, groq-mixtral]
    cheap: [openai-gpt4o-mini, anthropic-claude-haiku]
    reasoning: [openai-o1, anthropic-claude-sonnet]
  
  # Retries
  num_retries: 3
  request_timeout: 120
  
  # Health check driven routing
  health_check:
    enabled: true
    interval: 60                       # seconds
    unhealthy_threshold: 3             # failures before removing from pool
```

### 5.1 Agent-Level Routing Hints

Agents can provide routing hints via metadata that LiteLLM uses:

```yaml
# In agent YAML
spec:
  llm: gpt-4o                         # model name resolved by LiteLLM
  llm_tags: [reasoning]               # routed to models tagged "reasoning"
  llm_metadata:
    priority: high                     # LiteLLM request prioritisation
```

## 6. Spend Tracking, Cost Attribution & LLM Observability

LiteLLM is the **sole observability layer for all LLM traffic**. There is no separate trace backend -- LiteLLM provides everything needed for LLM request inspection, cost tracking, and usage analytics.

### 6.1 Data Flow

```
LiteLLM Proxy
    │
    │  Every LLM call tracked:
    │    - model, tokens, cost, latency, success/failure
    │    - virtual key → agent/execution/user
    │    - full request/response logged
    │
    ▼
┌────────────────────────────────────────┐
│  Two data consumers:                   │
│                                        │
│  1. LiteLLM Dashboard (:4000/ui)       │
│     Real-time request inspection,      │
│     model analytics, spend tracking    │
│                                        │
│  2. Blackbeard Spend Sync              │
│     Periodic poll:                     │
│       GET /spend/logs                  │
│       GET /key/info?key=sk-agent-xxx   │
│       GET /user/info?user_id=alice     │
│       GET /team/info?team_id=prod      │
│                                        │
│     Maps LiteLLM spend data to:        │
│       - Execution records (PRD 07)     │
│       - Per-agent cost dashboards      │
│       - Per-user cost attribution      │
│       - Budget warning events          │
└────────────────────────────────────────┘
```

**Latency note:** The 60-second polling interval means dashboard cost data lags real-time by up to 60 seconds. Budget *enforcement* is real-time (via LiteLLM virtual key `max_budget`), but dashboard *visibility* is near-real-time. This is an acceptable trade-off -- enforcement prevents overspend regardless of dashboard lag.

### 6.2 LiteLLM as Sole LLM Observability Layer

LiteLLM provides all LLM-level observability out of the box. No additional trace backend is needed:

| Capability | LiteLLM Feature | Endpoint / Mechanism |
|------------|-----------------|---------------------|
| **Cost tracking** | Per-key, per-user, per-team spend logs | `GET /spend/logs`, `GET /global/spend/logs` |
| **Rate limiting** | Per-key RPM/TPM configuration | Virtual key `rpm_limit`, `tpm_limit` |
| **Budgets** | Per-key, per-user, per-team budget enforcement | Virtual key `max_budget`, `budget_duration` |
| **Request inspection** | Full request/response logging | LiteLLM Dashboard at `:4000/ui` |
| **Model analytics** | Token usage, latency, error rates per model | Dashboard and `/model/metrics` |
| **Provider health** | Health checks, failure tracking | `/health`, `/model/info` |

**LiteLLM Dashboard** (`http://litellm:4000/ui`): Provides a built-in UI for operators to inspect individual LLM requests, view model performance metrics, manage virtual keys, and monitor spend in real-time. Blackbeard links to this dashboard from its LLM management pages.

**No external trace backend.** LiteLLM handles all LLM-level observability. Crew/task/tool-level observability is handled by Blackbeard's `execution_events` table (see PRD 05, section 11.1 and PRD 07).

### 6.3 Cost Dashboard Data

| Dimension | Source |
|-----------|--------|
| Cost per execution | Sum of all LLM calls for that execution's virtual key |
| Cost per agent | Aggregated across executions |
| Cost per crew | Sum of all agent keys in the crew |
| Cost per user | LiteLLM user-level spend tracking |
| Cost per model | LiteLLM model-level spend tracking |
| Cost per provider | Aggregated from model-level data |
| Daily/weekly/monthly trends | Time-series from LiteLLM spend logs (`GET /spend/logs`) |

## 7. LLM Management UI

### 7.1 Models Tab

- **Table**: All configured LLM connections with provider, model, deployment count, RPM, TPM, status (healthy/unhealthy).
- **Add Model**: Form to create an `LLMConnection` resource → auto-generates LiteLLM config.
- **Health status**: Real-time health from LiteLLM's health check API.
- **Spend**: Per-model cost in the last 24h / 7d / 30d.

### 7.2 Routing Tab

- **Visual routing diagram**: Shows model → fallback → fallback chain.
- **Strategy selector**: Dropdown for routing strategy.
- **Tag routing editor**: Assign models to tags.
- **Test route**: "If agent X requests model Y, which deployment handles it?" — instant answer.

### 7.3 Spend & Budgets Tab

- **Per-agent spend**: Table of agents with cost in current period.
- **Per-user spend**: Cost attributed to each human user.
- **Budget utilisation**: Bar charts showing budget consumed vs. limit per AgentPolicy.
- **Alerts**: Configure Slack/email alerts for budget thresholds (80%, 90%, 100%).

### 7.4 Keys Tab (Advanced)

- **Virtual keys**: List of active LiteLLM keys with their agent/execution mapping.
- **Audit**: Which key was used for which execution.
- **Manual key creation**: For advanced use cases (external consumers, testing).

### 7.5 LiteLLM Dashboard Link

- **Direct link** to the LiteLLM Dashboard at `:4000/ui` for advanced request inspection.
- Operators can drill into individual LLM requests, view full prompts/completions, latency breakdowns, and error details.
- This replaces any need for a separate trace backend like Langfuse for LLM-level observability.

## 8. CrewAI Integration Point

At execution time, Blackbeard configures CrewAI's `LLM` class to route through LiteLLM:

```python
from crewai import LLM, Agent

# Blackbeard sets this up at execution start, per-agent
agent_llm = LLM(
    model="openai-gpt4o",                    # LiteLLM model alias
    base_url="http://litellm-proxy:4000",    # LiteLLM Proxy endpoint
    api_key=agent_virtual_key,               # per-agent virtual key with budget
)

# CrewAI agent uses this LLM — all calls go through LiteLLM
agent = Agent(
    config=loaded_agent_config,
    llm=agent_llm,
    function_calling_llm=LLM(
        model="openai-gpt4o-mini",
        base_url="http://litellm-proxy:4000",
        api_key=agent_virtual_key,           # same key → same budget
    ),
)
```

CrewAI doesn't know or care that it's talking to LiteLLM. It sees an OpenAI-compatible API. LiteLLM handles the rest.

## 9. Deployment Topology

### 9.1 Sidecar (Default)

LiteLLM Proxy runs as a sidecar container alongside Blackbeard workers:

```yaml
# docker-compose.yaml
services:
  blackbeard-worker:
    image: blackbeard/worker:latest
    depends_on: [litellm, postgres, valkey]
    
  litellm:
    image: litellm/litellm:<pinned-stable-version>
    environment:
      DATABASE_URL: postgresql://...
      VALKEY_HOST: valkey
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
    volumes:
      - ./litellm-config.yaml:/app/config.yaml   # auto-generated by Blackbeard
    ports:
      - "4000:4000"
```

### 9.2 Standalone (Scale)

For high-volume deployments, LiteLLM runs as a separate service with its own scaling:

```
Blackbeard Workers (N) ──→ LiteLLM Proxy (M instances behind LB) ──→ LLM Providers
```

### 9.3 External (BYO)

Users can point Blackbeard at an existing LiteLLM Proxy they already operate:

```yaml
apiVersion: blackbeard/v1
kind: PlatformConfig
spec:
  litellm:
    mode: external                     # sidecar | standalone | external
    base_url: "https://litellm.internal.company.com"
    master_key_env: LITELLM_MASTER_KEY
```

### 9.4 Health & Circuit Breaking

If the LiteLLM Proxy is unreachable:

1. **Health check**: Blackbeard workers ping `GET /health` on the proxy every 30s.
2. **Circuit breaker**: After 3 consecutive failures, the worker marks LiteLLM as unhealthy and emits `litellm.proxy.unhealthy`.
3. **Impact**: All `kickoff()` requests are rejected with `503 Service Unavailable` — the system does not attempt to call LLM providers directly (that would bypass budget enforcement).
4. **Recovery**: When health checks pass again, the circuit closes and kickoffs resume. The `litellm.proxy.recovered` event is emitted.

## 10. Configuration Hot-Reload

When a `LLMConnection` or `LLMRoutingConfig` resource is created, updated, or deleted:

1. Blackbeard regenerates the LiteLLM config YAML.
2. Blackbeard calls `POST /config/update` on the LiteLLM Proxy API with the new config.
3. LiteLLM applies the change without restart — new models, routing rules, and fallbacks take effect immediately.
4. If the reload fails (e.g., invalid config), Blackbeard logs the error and emits a `litellm.config.reload_failed` event. The previous config remains active.
5. As a last resort, the worker can restart the LiteLLM sidecar container.

**Config reload safety:** Before applying a generated LiteLLM config, the system validates it:
1. Generate `litellm_config.yaml` from LLMConnection resources
2. Schema-validate the generated YAML against LiteLLM's config schema
3. Call `POST /config/update` on LiteLLM Proxy with the new config
4. If LiteLLM rejects the config (400 response), roll back the LLMConnection change at the API level and return 422 to the user with LiteLLM's error message
5. If validation passes and reload succeeds, the new config is active immediately

This prevents a malformed LLMConnection resource from breaking the LLM routing layer.

## 11. Events Emitted

| Event | Payload |
|-------|---------|
| `litellm.key.created` | `{key_alias, agent, execution_id, models, budget}` |
| `litellm.key.deleted` | `{key_alias, agent, execution_id, spend_total}` |
| `litellm.key.budget_warning` | `{key_alias, agent, used, limit, percentage}` |
| `litellm.key.budget_exceeded` | `{key_alias, agent, limit, execution_id}` |
| `litellm.model.unhealthy` | `{model_name, deployment, error}` |
| `litellm.model.recovered` | `{model_name, deployment}` |
| `litellm.config.regenerated` | `{reason, model_count}` |
| `litellm.fallback.triggered` | `{from_model, to_model, reason}` |

## 12. Acceptance Criteria

1. All LLM calls from CrewAI agents go through LiteLLM Proxy — no direct provider calls.
2. Creating a `LLMConnection` resource auto-generates valid LiteLLM config and the proxy picks it up.
3. An agent with `llm.allow: [openai-gpt4o]` can only use that model; requests for other models are rejected by LiteLLM's virtual key model restrictions.
4. An agent with `max_cost_per_execution_usd: 5.00` is stopped when the LiteLLM virtual key budget is exhausted.
5. Fallback works: if `openai-gpt4o` returns a 500, LiteLLM automatically retries with `anthropic-claude-sonnet`.
6. Context window fallback works: if a prompt exceeds `gpt-4o`'s context, LiteLLM routes to the configured fallback model.
7. Load balancing distributes requests across multiple deployments of the same model.
8. Spend data is accurate: per-execution cost in the execution record matches LiteLLM's key spend.
9. Spend dashboard shows cost breakdowns by agent, user, model, and time period.
10. LiteLLM Proxy can be deployed as sidecar, standalone, or external -- all three modes work.
11. Routing strategy changes (e.g., `least-busy` to `latency-based-routing`) take effect without restart.
12. LiteLLM Dashboard at `:4000/ui` is accessible and shows individual LLM request details.
13. No external trace backend -- LiteLLM provides all LLM-level observability (cost, tokens, latency, request/response inspection).
