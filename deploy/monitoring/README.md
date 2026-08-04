# Monitoring Setup

Optional monitoring stack for Blackbeard using Prometheus and Grafana.

## Files

| File | Purpose |
|------|---------|
| `prometheus.yaml` | Prometheus scrape config for API (`/api/v1/metrics`), LiteLLM, PostgreSQL, Valkey |
| `alerts.yaml` | Alert rules for service health, RED metrics, executor saturation, spend, disk |
| `grafana-dashboard.json` | Grafana dashboard with health, latency, spend, DB metrics |

## API metrics (exported by Blackbeard)

| Metric | Type | Meaning |
|--------|------|---------|
| `http_requests_total` | Counter | Request count by `method`, `status` |
| `http_request_duration_seconds` | Histogram | Request latency by `method`, `status` |
| `blackbeard_active_executions` | Gauge | Executor threads currently running crews |
| `blackbeard_executor_queued_tasks` | Gauge | Crews waiting on the thread pool |
| `blackbeard_executor_max_workers` | Gauge | Configured max concurrent executions |
| `blackbeard_executor_saturated` | Gauge | `1` when pool is full and queue is non-empty |
| `blackbeard_executions_total` | Counter | Terminal outcomes by `type`, `status` |
| `blackbeard_execution_duration_seconds` | Histogram | Wall-clock duration of terminal executions by `type`, `status` |
| `blackbeard_webhook_deliveries_total` | Counter | Outbound webhook attempts by `status` (`success`/`failure`/`error`/`ssrf_blocked`) |
| `blackbeard_sse_active` | Gauge | Active SSE event streams |
| `blackbeard_sse_max` | Gauge | Configured max concurrent SSE streams |

## Quick Start

Add Prometheus and Grafana to your docker-compose.yaml:

The `networks: [backend]` entries are required: the main compose file defines
named networks, so services without one land on the default network and cannot
reach the API or LiteLLM. The two exporters back the `postgres` and `valkey`
scrape jobs in `prometheus.yaml`; without them the `PostgresDown` and
`ValkeyDown` alerts fire permanently.

```yaml
services:
  prometheus:
    image: prom/prometheus:v3.4.1
    volumes:
      - ./deploy/monitoring/prometheus.yaml:/etc/prometheus/prometheus.yml
      - ./deploy/monitoring/alerts.yaml:/etc/prometheus/alerts.yaml
    ports:
      - "127.0.0.1:9090:9090"
    networks: [backend]

  grafana:
    image: grafana/grafana:12.0.1
    volumes:
      - grafana-data:/var/lib/grafana
    ports:
      - "127.0.0.1:3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    networks: [backend]

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.16.0
    environment:
      DATA_SOURCE_NAME: "postgresql://${POSTGRES_USER:-blackbeard}:${POSTGRES_PASSWORD:-blackbeard}@postgres:5432/${POSTGRES_DB:-blackbeard}?sslmode=disable"
    networks: [backend]

  valkey-exporter:
    image: oliver006/redis_exporter:v1.66.0
    environment:
      REDIS_ADDR: "valkey:6379"
      REDIS_PASSWORD: "${VALKEY_PASSWORD:-valkey-dev-secret}"
    networks: [backend]

volumes:
  grafana-data:
```

## Importing the Dashboard

1. Open Grafana at http://localhost:3001
2. Add Prometheus as a data source (http://prometheus:9090)
3. Import `grafana-dashboard.json` via Dashboards > Import

## Alert Rules

| Alert | Severity | Trigger |
|-------|----------|---------|
| APIDown | Critical | API unreachable for 1 minute |
| APIHighLatency | Warning | histogram p95 > 2s for 5 minutes |
| APIHighErrorRate | Warning | 5xx rate > 5% for 5 minutes |
| ExecutorSaturated | Warning | Executor full + queue for 5 minutes |
| ExecutionHighFailureRate | Warning | >25% executions failed over 15 minutes |
| ExecutionHighLatency | Warning | execution duration p95 > 30m for 15 minutes |
| WebhookHighFailureRate | Warning | >50% webhook deliveries failed/error for 15 minutes |
| LiteLLMDown | Critical | LiteLLM unreachable for 1 minute |
| LiteLLMHighSpend | Warning | Total spend > $100 |
| PostgresDown | Critical | DB unreachable for 1 minute |
| PostgresHighConnections | Warning | > 80 connections for 5 minutes |
| PostgresDiskUsage | Warning | DB size > 5GB |
| ValkeyDown | Warning | Valkey unreachable for 1 minute |
| ValkeyHighMemory | Warning | Memory > 90% for 5 minutes |

## OpenTelemetry

The API supports OTEL trace export. Set `OTEL_ENDPOINT` in `.env` to send traces to Jaeger, Tempo, or any OTLP collector:

```bash
OTEL_ENDPOINT=http://jaeger:4317
```

When unset, tracing is disabled with no overhead.
