# Monitoring Setup

Optional monitoring stack for Blackbeard using Prometheus and Grafana.

## Files

| File | Purpose |
|------|---------|
| `prometheus.yaml` | Prometheus scrape config for API, LiteLLM, PostgreSQL, Valkey |
| `alerts.yaml` | Alert rules for service health, latency, spend, disk |
| `grafana-dashboard.json` | Grafana dashboard with health, latency, spend, DB metrics |

## Quick Start

Add Prometheus and Grafana to your docker-compose.yaml:

```yaml
services:
  prometheus:
    image: prom/prometheus:v3.4.1
    volumes:
      - ./deploy/monitoring/prometheus.yaml:/etc/prometheus/prometheus.yml
      - ./deploy/monitoring/alerts.yaml:/etc/prometheus/alerts.yaml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:12.0.1
    volumes:
      - grafana-data:/var/lib/grafana
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin

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
| APIHighLatency | Warning | p95 > 2s for 5 minutes |
| APIHighErrorRate | Warning | 5xx rate > 5% for 5 minutes |
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
