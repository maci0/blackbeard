# PRD 07 — Observability & Traces

## 1. Purpose

Provide comprehensive visibility into every crew, flow, and agent execution. Instead of building a custom trace storage and visualization layer, Blackbeard delegates to **Langfuse** (self-hosted, fully open-source MIT) as the trace backend and ships a thin integration layer that maps CrewAI events + LiteLLM callbacks to Langfuse traces.

### What Langfuse provides (we don't build)

- Trace storage with span trees (generations, spans, events)
- Token usage and cost tracking per trace/span
- Trace UI with timeline, LLM call inspection, token counts
- Prompt management and versioning
- Evaluations and scoring
- OpenTelemetry backend (`/api/public/otel` endpoint)
- User/session tracking
- Dashboard with aggregated metrics
- Self-hosted Docker deployment

### What Blackbeard adds

- CrewAI event bus → Langfuse trace mapping
- LiteLLM → Langfuse callback (LiteLLM supports this natively)
- Sandbox-tier annotations on tool call spans
- Policy denial events as Langfuse spans
- Linked Langfuse UI from Blackbeard's execution detail pages (direct URL links to Langfuse traces; avoids iframe CORS/auth complexity)
- Blackbeard-specific dashboards (policy denials, sandbox usage, budget utilization)

## 2. Trace Model

Every `kickoff()` produces a **Trace** — a tree of spans:

```
Trace (execution-level)
├── Crew Span
│   ├── Task Span: "research-ai"
│   │   ├── Agent Span: "researcher"
│   │   │   ├── LLM Call Span (prompt → completion)
│   │   │   ├── Tool Call Span: "serper-search" [sandbox: wasm]
│   │   │   │   └── Network Span: GET serper.dev (340ms)
│   │   │   ├── LLM Call Span
│   │   │   ├── Policy Denial Span: tool "db-admin" denied
│   │   │   └── LLM Call Span (final answer)
│   │   └── Guardrail Span: word-count-check (pass)
│   ├── Task Span: "write-report"
│   │   └── ...
│   └── Callback Span: after_kickoff
└── Metadata: inputs, outputs, token_usage, cost, duration
```

## 3. Trace Data

### 3.1 Execution Summary

| Field | Description |
|-------|-------------|
| `execution_id` | Unique identifier |
| `automation_id` | Which crew/flow was run |
| `status` | completed / failed / timeout |
| `inputs` | User-provided inputs |
| `outputs` | Final crew output |
| `total_tokens` | Prompt + completion tokens |
| `estimated_cost_usd` | Based on model pricing tables |
| `duration_seconds` | Wall-clock time |
| `principal_chain` | User → Crew → Agent chain for audit |
| `sandbox_summary` | Count of tool calls per sandbox tier |

### 3.2 Per-Task Detail

- Task description and expected output.
- Assigned agent and LLM.
- Status, start/end time, duration.
- Token usage (prompt, completion, total).
- Input context (from prior tasks).
- Output (raw, JSON, or Pydantic).

### 3.3 Per-LLM-Call Detail

- Model name and provider.
- Messages (system, user, assistant, tool).
- Token counts.
- Latency (time-to-first-token, total).
- Response: raw text or tool calls.
- **PII redacted** (PRD 08) before storage.

### 3.4 Per-Tool-Call Detail

- Tool name and type.
- **Sandbox tier** used (`none` / `wasm` / `docker` / `microvm`).
- Sandbox instance ID.
- Input parameters (hash for sensitive data).
- Output (truncated if large).
- Duration, memory peak, network calls made.
- Status: success / error / timeout / policy_denied.

### 3.5 Policy Events

- Every `agent.policy.denied` event is recorded in the trace.
- Budget warnings and budget-exceeded events.
- Sandbox tier promotions (tool requested `none`, policy promoted to `wasm`).

## 4. Trace UI

**Implementation split**: Sections 4.1 (Traces List) and 4.4 (Execution Detail summary cards, task list, link to Langfuse) are built in Blackbeard's UI. Sections 4.2 (Trace Detail View with span tree and agent thoughts) and 4.3 (Execution Timeline Gantt chart) are provided by Langfuse's native UI, accessed via direct URL links from Blackbeard. For MVP, all trace visualization is via Langfuse links — only the Traces List and Execution Detail pages are custom-built.

**MVP scope:** For MVP, all trace visualization is via direct links to Langfuse's built-in UI. Blackbeard's Execution Detail page shows summary data (tokens, cost, duration, task list) from its own database and provides a 'View Trace in Langfuse' link. Custom trace visualizations (Gantt chart, agent thought inspector) described above are post-MVP features that would be built into Blackbeard's UI.

### 4.1 Traces List

- Table: execution ID, automation name, status, duration, cost, timestamp.
- Filters: status, automation, date range, user.
- Search: by execution ID, input content, agent name.

### 4.2 Trace Detail View

- **Summary cards**: Total tokens, cost, duration, task count.
- **Task timeline**: Gantt chart showing task start/end, parallel execution.
- **Task list**: Click to expand each task's agent reasoning, tool calls, LLM calls.
- **Agent thoughts**: Full chain-of-thought display per agent step.
- **Tool call inspector**: For each tool call — input, output, sandbox tier, duration, network activity.
- **Policy events**: Highlighted in orange/red — denials, budget warnings.
- **Final output**: Rendered markdown or JSON.

### 4.3 Execution Timeline

Visual Gantt chart:
- X-axis: wall-clock time.
- Y-axis: tasks (and within tasks, agent steps).
- Colour-coded: LLM calls (blue), tool calls (green), waiting (gray), errors (red).
- Hover: show duration, tokens, cost for that span.

## 5. Metrics & Dashboards

### 5.1 Usage Dashboard

- Total executions (by day/week/month).
- Token usage over time (by model, by crew).
- Cost over time (by model, by crew, by user).
- Error rate and common failure modes.
- Average execution duration by crew.
- Sandbox tier distribution over time (what % of tool calls in each tier).

### 5.2 Agent Performance

- Per-agent: avg tokens per task, avg duration, error rate.
- Tool usage frequency and latency distribution.
- Sandbox tier distribution (what % of tool calls run in each tier).
- Guardrail pass/fail rates.

### 5.3 Policy Dashboard

- Policy denial frequency by agent, tool, and rule.
- Budget utilisation (tokens/cost used vs. limits).
- Sandbox tier distribution across the org.

### 5.4 Dashboard Implementation

Blackbeard-specific dashboards (§5.2 Agent Performance, §5.3 Policy Dashboard) are built in **Blackbeard's own UI**, not in Langfuse. They query Blackbeard's `executions` and `execution_tool_calls` tables for sandbox and policy data, and optionally query Langfuse's API for token/cost aggregations. Langfuse's built-in dashboards remain available for LLM-focused analytics.

**Data join key:** The `execution_id` is used as Langfuse's `trace_id` (set via `langfuse_trace_id` parameter when creating the trace). This allows joining Blackbeard's `executions` table with Langfuse's trace data. Dashboard queries that need token/cost aggregations call Langfuse's `GET /api/public/traces/{trace_id}` endpoint. Dashboard data is cached in Valkey with a 60-second TTL.

## 6. Integration Configuration

```yaml
apiVersion: blackbeard/v1
kind: ObservabilityConfig
metadata:
  name: production-observability
spec:
  # Primary: Langfuse (self-hosted)
  langfuse:
    enabled: true
    base_url: "http://langfuse:3000"       # self-hosted Langfuse instance
    public_key_env: LANGFUSE_PUBLIC_KEY
    secret_key_env: LANGFUSE_SECRET_KEY
    # LiteLLM also sends to Langfuse directly (configured in LiteLLM's config)
    litellm_callback: true                 # enable litellm → langfuse callback

  # Optional: also export to OpenTelemetry collector for Datadog/Grafana/etc.
  opentelemetry:
    enabled: false
    endpoint: "https://otel-collector.internal:4317"
    protocol: grpc
    headers:
      Authorization: "Bearer ${OTEL_TOKEN}"
    resource_attributes:
      service.name: "blackbeard"
```

**Scoping:** One `ObservabilityConfig` per namespace. If absent, the org-level default applies. If no config exists at any level, Langfuse integration is enabled with default settings (sample rate 1.0, retention 90 days) and a startup info message is logged.

**LiteLLM → Langfuse**: LiteLLM natively supports Langfuse as a callback. When enabled, every LLM call made through LiteLLM Proxy is automatically traced in Langfuse with model, tokens, cost, and latency — no custom code needed.

**CrewAI → Langfuse**: Blackbeard registers a CrewAI `BaseEventListener` that maps CrewAI events to Langfuse SDK calls (`langfuse.trace()`, `trace.span()`, `trace.generation()`), adding Blackbeard-specific metadata (sandbox tier, policy decisions, agent name, execution ID).

## 7. Trace Batching & Performance

- Trace events are buffered and sent in batches (configurable: batch size, flush interval).
- Traces are written asynchronously — they never block execution.
- **Sampling**: Configurable via `ObservabilityConfig.spec.langfuse.sampling_rate` (default: 1.0 = trace everything). For high-volume deployments, set to 0.1–0.5. Sampling is per-execution (a sampled-out execution produces no trace at all, rather than partial traces). Policy denial events are always traced regardless of sampling rate. When a sampled-out execution encounters a policy denial, the execution is upgraded from sampled-out to sampled-in — the full trace is created retroactively. This ensures all policy-relevant events have complete execution context. This may increase the effective sampling rate slightly, but policy denials are rare events and the impact is negligible.
- Trace retention is managed in Langfuse's own configuration (default: 30 days). Blackbeard does not control Langfuse's data lifecycle.

## 8. Events Consumed

| Source Event | Action |
|-------------|--------|
| `execution.*` | Create/update trace spans |
| `agent.policy.denied` | Record policy denial span |
| `agent.policy.budget_warning` | Record budget warning span |

## 9. Acceptance Criteria

1. Every execution produces a Langfuse trace with task, LLM call, and tool call spans.
2. Tool call spans include the sandbox tier used (`none`, `wasm`, `docker`, `microvm`) as metadata.
3. Langfuse UI (linked) shows execution timeline, agent reasoning, and tool call details.
4. LiteLLM → Langfuse callback works: every LLM call appears in Langfuse with model, tokens, cost.
5. Policy denials appear in traces as Langfuse events with full context.
6. Optional OpenTelemetry export sends valid OTLP spans to a configured collector.
7. PII is redacted from traces before they are sent to Langfuse (PRD 08, Presidio).
8. Trace writes (async via Langfuse SDK) never add >5ms latency to execution critical path.
9. Langfuse self-hosted instance is included in the default `docker-compose.yaml`.

## Trace Data Retention

Langfuse stores trace data in ClickHouse. Without retention policies, storage grows unboundedly.

**Default retention:** 90 days. Traces older than 90 days are automatically deleted from ClickHouse.

**Configuration:** Retention period is configurable via `PlatformConfig`:
```yaml
observability:
  trace_retention_days: 90        # default
  sampling_rate: 1.0              # 1.0 = trace everything (default for MVP)
```

**Langfuse unavailability:** Trace writes are fire-and-forget. If Langfuse is unavailable during execution:
- Execution continues normally — tracing never blocks execution
- Trace data for that execution is permanently lost
- A warning is logged: `"Langfuse trace write failed for execution {id}: {error}"`
- A metric `blackbeard_langfuse_trace_errors_total` is incremented for operator alerting
