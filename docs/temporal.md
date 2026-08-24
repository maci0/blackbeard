# Temporal Workflow Engine Integration

Blackbeard can optionally use [Temporal](https://temporal.io) as the execution backend for crew runs. When enabled, crew executions are dispatched as durable Temporal workflows instead of running in the local ThreadPoolExecutor.

## Why Temporal?

The default ThreadPoolExecutor works well for single-node deployments, but has limitations at scale:

- **No persistence across restarts.** If the API server crashes, in-flight executions are lost and marked as failed on recovery.
- **No horizontal scaling.** Workers are bound to the API process. You cannot run execution workers on separate machines.
- **No built-in retries.** Transient failures (network timeouts, provider rate limits) require custom retry logic.
- **Limited visibility.** Execution state is only visible through the Blackbeard API.

Temporal addresses all of these:

- **Durable execution.** Workflows survive server restarts. Temporal replays workflow history to resume from the last checkpoint.
- **Scalable workers.** Temporal workers can run on any number of machines, independent of the API server.
- **Configurable retry policies.** Automatic retries with exponential backoff, configurable per-activity.
- **Built-in UI.** The Temporal web UI provides workflow history, search, and debugging tools.
- **Timeout enforcement.** Workflow-level and activity-level timeouts are enforced by the Temporal server, not the application.

## Quick Start (Docker Compose)

The simplest way to try Temporal locally is with the provided compose overlay:

```bash
docker compose -f docker-compose.yaml -f docker-compose.temporal.yaml up
```

This starts the standard Blackbeard stack plus:

| Service       | Port  | Description              |
|---------------|-------|--------------------------|
| temporal      | 7233  | Temporal gRPC server     |
| temporal-ui   | 8233  | Temporal web UI          |

The overlay automatically sets `TEMPORAL_HOST=temporal:7233` on the API service, so crew executions route through Temporal with no additional configuration.

Open http://localhost:8233 to see workflows in the Temporal UI.

## Configuration

All settings are optional environment variables. When `TEMPORAL_HOST` is unset (the default), the existing ThreadPoolExecutor is used and no Temporal dependencies are loaded.

| Variable                       | Default          | Description                                                    |
|--------------------------------|------------------|----------------------------------------------------------------|
| `TEMPORAL_HOST`                | *(unset)*        | Temporal server address (e.g. `localhost:7233`). Enables Temporal when set. |
| `TEMPORAL_NAMESPACE`           | `blackbeard`     | Temporal namespace for workflow isolation.                      |
| `TEMPORAL_TASK_QUEUE`          | `crew-execution` | Task queue name. Workers and clients must agree on this value.  |
| `TEMPORAL_WORKFLOW_TIMEOUT_S`  | `3600`           | Maximum wall-clock time for a single crew execution workflow.   |

## Installing the SDK

The `temporalio` package is an optional dependency. Install it with:

```bash
cd backend/
uv sync --extra temporal
```

Or add `temporalio` to your pip install:

```bash
pip install temporalio>=1.9,<2
```

If `TEMPORAL_HOST` is set but the SDK is not installed, the API server logs a warning and falls back to the ThreadPoolExecutor.

## How It Works

### Execution Flow

1. User calls `POST /api/v1/crews/{name}/kickoff` (or `/train`, `/test`, `/flows/{name}/run`).
2. The executor creates an `Execution` record with status `queued`, same as before.
3. If `TEMPORAL_HOST` is set and the SDK is available, `submit_temporal_execution()` starts a `CrewExecution` Temporal workflow. Otherwise, the execution goes to the ThreadPoolExecutor as before.
4. The Temporal worker picks up the workflow and runs the `run_crew` activity.
5. The activity calls the same `run_crew_async()` function used by the ThreadPoolExecutor path, so budget enforcement, PII redaction, cost alerts, and all other execution features work identically.
6. Results are stored in the database. The Temporal UI also shows workflow status and history.

### Retry Policy

The default retry policy for the `run_crew` activity:

- Initial interval: 5 seconds
- Backoff coefficient: 2.0x
- Maximum interval: 5 minutes
- Maximum attempts: 3
- Non-retryable errors: `ExecutionNotFoundError`, `ExecutionError`, `ValueError`, `KeyError`

This means transient failures (network issues, provider rate limits) are retried automatically, while logic errors fail immediately.

### Graceful Degradation

The integration is designed to never break existing deployments:

- The `temporal.py` module uses conditional imports. If `temporalio` is not installed, `TEMPORAL_AVAILABLE` is `False` and all Temporal code paths are skipped.
- If `TEMPORAL_HOST` is set but the SDK is missing, a warning is logged and the ThreadPoolExecutor is used.
- If the Temporal worker fails to start during app startup, a warning is logged and the executor falls back to threads.
- If a specific workflow submission fails, that execution is marked as failed in the database (same behavior as a ThreadPoolExecutor crash).

## Production Deployment

For production, run a proper Temporal cluster rather than the `auto-setup` dev image. See the [Temporal deployment docs](https://docs.temporal.io/self-hosted-guide) for options including Kubernetes (Helm chart), cloud-hosted (Temporal Cloud), and bare-metal setups.

Key considerations:

- Use PostgreSQL or Cassandra as the Temporal persistence backend (not SQLite).
- Run multiple Temporal workers for redundancy. Each API server instance starts its own worker, or you can run dedicated worker processes.
- Set `TEMPORAL_NAMESPACE` to isolate Blackbeard workflows from other applications sharing the same Temporal cluster.
- Tune `TEMPORAL_WORKFLOW_TIMEOUT_S` based on your longest expected crew execution time.

## Separate Worker Process

In production you may want to run workers independently of the API server (for example, on GPU nodes or larger instances). The Temporal worker is embedded in the API server by default, but you could also run it standalone:

```python
import asyncio
from blackbeard.engine.temporal import start_temporal_worker, stop_temporal_worker

async def main():
    await start_temporal_worker()
    try:
        await asyncio.Event().wait()  # run forever
    finally:
        await stop_temporal_worker()

asyncio.run(main())
```

This pattern lets you scale workers horizontally without additional API server instances.
