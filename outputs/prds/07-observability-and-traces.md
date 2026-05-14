# PRD 07 — Observability & Traces

## 1. Purpose

Provide comprehensive visibility into every crew, flow, and agent execution through a **two-layer observability architecture** that requires no external trace backend:

1. **LLM-level observability**: LiteLLM handles all LLM request tracking -- tokens, cost, latency, success/failure, full request/response inspection. Accessible via LiteLLM's built-in dashboard at `:4000/ui` and spend APIs.

2. **Crew-level observability**: Blackbeard's `execution_events` table (PRD 05, section 11.1) provides a complete crew/task/agent/tool event timeline. Events are stored as an append-only log and streamed to the frontend via SSE.

**No Langfuse.** Previous architecture used Langfuse as a trace backend. This has been removed. The combination of LiteLLM's built-in observability + Blackbeard's execution event log covers all use cases with fewer moving parts and no additional container dependency.

### What LiteLLM provides (LLM-level)

- Per-request logging: model, tokens, cost, latency, success/failure
- Full request/response inspection via dashboard at `:4000/ui`
- Spend tracking per virtual key, user, team, and model
- Budget enforcement with real-time overspend prevention
- Model health monitoring and error tracking

### What Blackbeard provides (Crew-level)

- `execution_events` table: append-only log of all crew/task/agent/tool events
- SSE endpoint for real-time event streaming to the frontend
- REST endpoint for historical event replay and filtering
- Execution summary with token usage, cost, duration, task progress
- Sandbox-tier tracking on tool calls
- Policy denial recording with full context
- Blackbeard-specific dashboards (policy denials, sandbox usage, budget utilization)

## 2. Observability Model

Every `kickoff()` produces observability data in two systems:

### 2.1 Execution Event Log (Blackbeard)

An append-only sequence of events stored in the `execution_events` table:

```
execution_events (for execution exec-abc123):
  seq=1  crew_started      {crew_name: "research-crew", total_tasks: 3}
  seq=2  task_started       {task_name: "research-ai", agent_name: "researcher"}
  seq=3  llm_started        {agent_name: "researcher", model: "gpt-4o"}
  seq=4  llm_completed      {agent_name: "researcher", model: "gpt-4o", tokens: 1200, cost_usd: 0.04}
  seq=5  tool_started       {tool_name: "serper-search", sandbox_tier: "wasm"}
  seq=6  tool_finished      {tool_name: "serper-search", duration_ms: 340, success: true}
  seq=7  llm_started        {agent_name: "researcher", model: "gpt-4o"}
  seq=8  policy_denied      {agent_name: "researcher", action: "tool_call", resource: "db-admin", reason: "not in allowlist"}
  seq=9  llm_completed      {agent_name: "researcher", model: "gpt-4o", tokens: 800, cost_usd: 0.02}
  seq=10 task_completed     {task_name: "research-ai", tokens: 2000, duration_ms: 12400}
  ...
  seq=25 crew_completed     {crew_name: "research-crew", total_tokens: 8000, total_cost_usd: 0.45}
```

### 2.2 LLM Request Logs (LiteLLM)

Every LLM call is separately logged in LiteLLM with full request/response detail, accessible via the LiteLLM dashboard at `:4000/ui`. This includes prompt messages, completion text, token counts, latency, model, provider, and cost -- detail that is too verbose for the event log.

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

## 4. Execution UI

All execution observability is built into **Blackbeard's own UI**, powered by data from the `execution_events` table and the `executions`/`execution_tasks` tables. LLM-level drill-down links to the LiteLLM dashboard.

### 4.1 Executions List

- Table: execution ID, crew/automation name, status, duration, cost, timestamp.
- Filters: status, crew/automation, date range, user.
- Search: by execution ID, input content, agent name.

### 4.2 Execution Detail View

- **Summary cards**: Total tokens, cost, duration, task count.
- **Live event log**: Real-time scrolling log of execution events (via SSE), showing crew/task/tool/LLM events as they occur. Completed executions show the full historical log.
- **Task list**: Click to expand each task's tool calls, LLM call summaries, and policy events.
- **Tool call inspector**: For each tool call -- sandbox tier, duration, success/failure.
- **Policy events**: Highlighted in orange/red -- denials, budget warnings.
- **Final output**: Rendered markdown or JSON.
- **LLM detail link**: "View LLM requests in LiteLLM" link to `:4000/ui` filtered by the execution's virtual key, for full prompt/completion inspection.

### 4.3 Execution Timeline (post-MVP)

Visual Gantt chart:
- X-axis: wall-clock time.
- Y-axis: tasks (and within tasks, agent steps).
- Colour-coded: LLM calls (blue), tool calls (green), waiting (gray), errors (red).
- Hover: show duration, tokens, cost for that event.
- Data source: `execution_events` table, ordered by timestamp.

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

All dashboards are built in **Blackbeard's own UI**:

- **Usage and cost dashboards** query Blackbeard's `executions` table for token/cost aggregations and LiteLLM's `/spend/logs` endpoint for detailed per-model and per-key breakdowns.
- **Agent and policy dashboards** query Blackbeard's `executions`, `execution_tasks`, `execution_tool_calls`, and `execution_events` tables for sandbox, policy, and performance data.
- **LLM-level analytics** are available via the LiteLLM dashboard at `:4000/ui`, linked from Blackbeard's LLM management pages.

**Data sources:** Dashboard data comes from two systems:
1. **Blackbeard DB**: `executions`, `execution_tasks`, `execution_tool_calls`, `execution_events` tables for crew/task/tool-level metrics.
2. **LiteLLM API**: `GET /spend/logs`, `GET /global/spend/logs`, `GET /model/metrics` for LLM-level cost and usage metrics.

Dashboard data is cached in Valkey with a 60-second TTL.

## 6. Integration Configuration

```yaml
apiVersion: blackbeard/v1
kind: ObservabilityConfig
metadata:
  name: production-observability
spec:
  # Execution event log (always enabled)
  execution_events:
    enabled: true                          # cannot be disabled — core to the platform
    retention_days: 90                     # auto-cleanup of old events

  # LiteLLM observability (always enabled when LiteLLM is deployed)
  litellm:
    dashboard_enabled: true                # expose LiteLLM dashboard link in Blackbeard UI
    spend_sync_interval: 60                # seconds between spend data polling

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

**Scoping:** One `ObservabilityConfig` per namespace. If absent, the org-level default applies. If no config exists at any level, execution event logging is enabled with defaults (retention 90 days) and a startup info message is logged.

**CrewAI event listener**: Blackbeard registers a CrewAI `BaseEventListener` that captures all crew/task/agent/tool events and writes them to the `execution_events` table (PRD 05, section 11.1). The same events are streamed to connected SSE clients in real-time.

**LiteLLM**: All LLM-level observability is handled by LiteLLM's built-in logging and dashboard. No additional callback configuration is needed -- LiteLLM logs all requests by default when using its database backend.

## 7. Event Writing & Performance

- Execution events are written to PostgreSQL asynchronously -- they never block the execution critical path.
- Events are buffered in-memory and flushed in batches (configurable: batch size, flush interval) to minimize DB round-trips.
- SSE clients receive events immediately from the in-memory buffer, before the DB flush.
- **All executions are logged.** Unlike sampling-based trace backends, the execution event log captures every execution. Events are lightweight (JSONB rows, not full prompt/completion text), so storage cost is manageable.
- **Retention**: Configurable via `ObservabilityConfig.spec.execution_events.retention_days` (default: 90 days). A background job runs daily to delete events older than the retention period.

## 8. Events Consumed

| Source Event | Action |
|-------------|--------|
| `execution.*` | Write to `execution_events` table; stream via SSE |
| `task.*` | Write to `execution_events` table; update `execution_tasks` status |
| `tool_call.*` | Write to `execution_events` table; write to `execution_tool_calls` table |
| `llm_call.*` | Write to `execution_events` table (summary); full detail logged by LiteLLM |
| `agent.policy.denied` | Write to `execution_events` table; record in `execution_tasks.policy_denials` |
| `agent.policy.budget_warning` | Write to `execution_events` table |

## 9. Acceptance Criteria

1. Every execution produces a complete event log in the `execution_events` table with correct sequence ordering.
2. Tool call events include the sandbox tier used (`none`, `wasm`, `docker`, `microvm`).
3. Blackbeard's execution detail UI shows a live event log via SSE during active executions, and a full historical log for completed executions.
4. LiteLLM dashboard at `:4000/ui` shows all LLM requests with model, tokens, cost, and full request/response detail.
5. Policy denials appear in the execution event log with full context (agent, action, resource, reason).
6. Optional OpenTelemetry export sends valid OTLP spans to a configured collector.
7. PII is redacted from event data before storage (PRD 08, Presidio).
8. Event writes (async, batched) never add >5ms latency to the execution critical path.
9. No Langfuse dependency -- all observability is provided by LiteLLM (LLM-level) and `execution_events` (crew-level).

## Event Data Retention

Execution events are stored in PostgreSQL. Without retention policies, storage grows unboundedly.

**Default retention:** 90 days. Events older than 90 days are automatically deleted by a daily background job.

**Configuration:** Retention period is configurable via `PlatformConfig`:
```yaml
observability:
  event_retention_days: 90        # default
```

**Storage estimation:** Each execution event is a small JSONB row (~500 bytes average). An execution with 50 events produces ~25KB of event data. At 1000 executions/day, this is ~25MB/day or ~2.25GB over 90 days -- well within PostgreSQL's capabilities.

**Database unavailability:** Event writes use the same PostgreSQL instance as the rest of Blackbeard. If the database is unavailable, execution itself fails (since execution state is also stored in PostgreSQL). Events buffered in memory are lost, but this is a catastrophic failure mode where event loss is the least concern.
