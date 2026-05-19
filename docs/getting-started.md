# Getting Started with Blackbeard

> **See also:** For a more comprehensive walkthrough (marketplace import, train/test commands, YAML editor, group management), see [quickstart.md](quickstart.md).

Blackbeard is an open, self-hosted Agent Management Platform built on top of CrewAI. This guide walks you through standing up the platform and running your first crew.

## Prerequisites

- **Docker** (or Podman) — `run.sh` auto-detects `docker compose` or `podman-compose`
- **GCP service account** with Vertex AI access — optional; only needed if using Vertex AI as an LLM provider
- **Bun** — required only for frontend development
- **Python 3.12+** and **uv** — required only for backend development

---

## 1. Start the Platform

```bash
git clone <repo-url> blackbeard
cd blackbeard

# Copy and configure environment variables
cp .env.example .env
# Edit .env: set BLACKBEARD_API_KEY, and optionally GOOGLE_CLOUD_PROJECT, CLOUD_ML_REGION, etc.

# Start all services (API, UI, PostgreSQL, Valkey, LiteLLM)
./run.sh
```

Services started by `run.sh`:

| Service | URL |
|---------|-----|
| Blackbeard API | http://localhost:8000 |
| Blackbeard UI | http://localhost:3000 |
| LiteLLM Proxy | http://localhost:4000 |

Wait ~2 minutes for all containers to become healthy before proceeding (the API and LiteLLM containers have a 120-second startup grace period).

---

## 2. Open the UI

Navigate to **http://localhost:3000** in your browser. The home page opens the Studio visual editor where you can build and manage crews.

---

## 3. Create Your First Crew via CLI

The `blackbeard` CLI can apply a directory of YAML files, creating or updating all resources in dependency order.

```bash
# Install the standalone CLI (requires uv: https://docs.astral.sh/uv/)
cd cli
uv sync

# Apply the research-crew example (path relative to repo root)
cd ..
blackbeard apply -f examples/research-crew/

# Verify resources were created (via API)
curl -H "X-API-Key: $BLACKBEARD_API_KEY" http://localhost:8000/api/v1/agents
curl -H "X-API-Key: $BLACKBEARD_API_KEY" http://localhost:8000/api/v1/tasks
curl -H "X-API-Key: $BLACKBEARD_API_KEY" http://localhost:8000/api/v1/crews
```

Validate YAML files without applying:

```bash
blackbeard validate -f examples/research-crew/
blackbeard apply -f examples/research-crew/ --dry-run
```

---

## 4. Create a Crew in Studio

Studio is a visual drag-and-drop editor for building crews.

1. Open **http://localhost:3000/studio**
2. In the **Palette** sidebar (left), drag an **Agent** node onto the canvas
3. Click the agent node to open the **Property Panel** (right); fill in `role`, `goal`, and `backstory`
4. Drag a **Task** node onto the canvas; set `description`, `expected_output`, and assign it to your agent by drawing an edge
5. Drag a **Crew** node; connect agents and tasks to it
6. Click **Save** in the toolbar — resources are persisted via the API
7. Click **Run** to kick off an execution immediately

You can switch between the form view and a read-only YAML preview (Monaco) in the Property Panel at any time.

---

## 5. Run and Monitor

### Kick off via CLI

```bash
# Run a crew, passing inputs as key=value pairs
blackbeard kickoff research-crew --input topic="The future of agentic AI"

# Poll execution status
blackbeard status <execution-id>
blackbeard status <execution-id> --watch  # poll until terminal state
```

### Kick off via UI

Open a crew in the Studio or navigate to the Crew resource detail page and click **Run**. Fill in any required inputs as JSON and click **Run Crew**. The Executions list auto-refreshes; click a row to see per-task status, outputs, and token/cost details. LiteLLM tracks all spend, token usage, and latency automatically.

---

## 6. Next Steps

- **Create custom tools** — Write a Python class extending `crewai.tools.BaseTool`, package it, and register it with a `Tool` resource (`type: python`, `class_path: your_package.YourTool`)
- **Set up agent policies** — Use `AgentPolicy` resources to enforce tool allowlists, spending budgets, delegation rules, and minimum sandbox tiers per crew
- **Add guardrails** — Attach `Guardrail` resources to tasks to validate or filter outputs using a Python function, an LLM judge, or JSON schema validation
- **Build flows** — Create `Flow` resources to chain multiple crews into multi-step pipelines
- **Import from the Marketplace** — Use the `/marketplace` page or API to import crews from git repos or the built-in starter
- **Train and test crews** — Use `blackbeard train` and `blackbeard test-crew` for iterative improvement and evaluation
- **Set up webhooks** — Register webhook URLs for execution event delivery with HMAC-SHA256 signing
- **Install the Python SDK** — See [`sdks/python/README.md`](../sdks/python/README.md) for programmatic access
- **Browse the YAML reference** — See [`docs/yaml-reference.md`](./yaml-reference.md) for a complete field-by-field reference for all resource kinds
