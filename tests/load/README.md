# Load Testing

Load tests use [Locust](https://locust.io/) to simulate concurrent API traffic.

## Setup

Locust is declared as the `load` extra of the backend package:

```bash
cd backend && uv sync --extra load
uv run locust -f ../tests/load/locustfile.py --host http://localhost:8000
```

## Run (with Web UI)

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089, set user count and spawn rate, start the test.

## Run (headless)

```bash
# 50 users, ramp up 5/sec, run for 60 seconds
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --headless -u 50 -r 5 --run-time 60s

# 200 users, 2 minutes, CSV output
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --headless -u 200 -r 10 --run-time 120s \
  --csv results/load-test
```

## Test Profiles

Two user classes with different traffic patterns:

**BlackbeardUser** (10x weight): Simulates regular developers hitting read-heavy endpoints (list resources, health checks) with occasional writes (create/delete agents). Wait time: 0.5-2s between requests.

**AdminUser** (1x weight): Simulates admin operations (user management, roles, webhooks, credentials) at lower frequency. Wait time: 2-5s between requests.

## Endpoints Covered

| Endpoint | Method | User Class | Weight |
|----------|--------|------------|--------|
| /api/v1/health | GET | Regular | 10 |
| /api/v1/health/ready | GET | Regular | 5 |
| /api/v1/agents | GET | Regular | 8 |
| /api/v1/tasks | GET | Regular | 8 |
| /api/v1/crews | GET | Regular | 8 |
| /api/v1/tools | GET | Regular | 5 |
| /api/v1/llm-connections | GET | Regular | 3 |
| /api/v1/executions | GET | Regular | 2 |
| /api/v1/audit-logs | GET | Regular | 2 |
| /api/v1/resources/export | GET | Regular | 1 |
| /api/v1/agents | POST+DELETE | Regular | 3 |
| /.well-known/agent-card.json | GET | Regular | 2 |
| /api/v1/tools/library | GET | Regular | 2 |
| /api/v1/auth/me | GET | Regular | 1 |
| /api/v1/users | GET | Admin | 5 |
| /api/v1/roles | GET | Admin | 3 |
| /api/v1/groups | GET | Admin | 3 |
| /api/v1/webhooks | GET | Admin | 2 |
| /api/v1/credentials | GET | Admin | 2 |
| /api/v1/projects | GET | Admin | 1 |

## Baseline Targets

For a single-replica deployment (1 API container):

| Metric | Target |
|--------|--------|
| p50 latency (reads) | < 50ms |
| p95 latency (reads) | < 200ms |
| p50 latency (writes) | < 100ms |
| p95 latency (writes) | < 500ms |
| Throughput | > 100 req/s at 50 users |
| Error rate | < 0.1% |
| Health endpoint | < 10ms p99 |
