# Quickstart

This guide walks you through starting Blackbeard, loading an example crew, running it, and creating your first agent. You will have a working setup in under 15 minutes.

**What you will build:** A running Blackbeard instance with a research crew that takes a topic as input, researches it, and writes a summary.

**What you will learn:**

- How to start the platform with Docker Compose
- How to seed the database with example resources
- How to run a crew from the CLI and the UI
- How to create your own agent

**Prerequisites:**

- [ ] [Docker](https://docs.docker.com/get-docker/) (or [Podman](https://podman.io/)) with Compose support
- [ ] [Git](https://git-scm.com/)
- [ ] [uv](https://docs.astral.sh/uv/) -- Python package manager (for the CLI)
- [ ] [Ollama](https://ollama.com/) with `qwen3.6` pulled -- only needed to execute crews locally; not required to start services

---

## Step 1: Clone and Start

Clone the repository and start all services.

```bash
git clone https://github.com/blackbeard/blackbeard.git
cd blackbeard
./run.sh
```

`run.sh` does three things:

1. Creates `.env` from `.env.example` if it does not exist (with safe dev defaults)
2. Builds the API and UI Docker images
3. Starts all five services: API, UI, PostgreSQL, Valkey, LiteLLM

Wait for all containers to become healthy. The API and LiteLLM have a 120-second startup grace period, so this takes about 2 minutes on the first run.

You should see output like:

```
Starting Blackbeard...
  API:      http://localhost:8000
  UI:       http://localhost:3000
  LiteLLM:  http://localhost:4000
```

> **Tip:** Run `./run.sh --detach` to start in background mode. Use `docker compose logs -f api` to follow logs.

---

## Step 2: Open the UI

Navigate to **http://localhost:3000** in your browser. You will see the Dashboard page -- this shows execution metrics, resource counts, and recent activity. The platform is running but has no resources yet, so the dashboard will be empty.

Use the sidebar to navigate to the **Studio** page (the visual graph editor) or any other page. You can also press `Cmd+K` (macOS) or `Ctrl+K` to open the command palette for quick navigation.

---

## Step 3: Seed the Database

The seed script creates RBAC roles, an example research crew (agents, tasks, LLM connection), agent policies, and a collection of builtin and MCP tools.

```bash
bash deploy/seed.sh
```

You should see output like:

```
Seeding Blackbeard at http://localhost:8000 ...
  + Role/owner
  + Role/admin
  + Role/developer
  ...
  + Crew/research-crew
  + Tool/file-read
  ...

Seed complete: 34 created, 0 failed.
```

Refresh the UI. You can now see resources in the Resources page (click "Resources" in the sidebar). The Studio page will show the research crew if you open it.

> **Note:** The seed script uses `POST` for all resources, which means re-running it updates existing resources rather than creating duplicates.

---

## Step 4: Run the Example Crew

### From the CLI

Install the CLI and kick off an execution.

```bash
cd cli
uv sync
uv run blackbeard kickoff research-crew --input topic="AI agents" --wait
```

The `--wait` flag polls until the execution completes. You will see a panel with the execution ID, status, and -- once finished -- the outputs and token usage.

> **Note:** This requires Ollama running locally with the `qwen3.6` model. The seeded LLM connection points to `ollama/qwen3.6`. If you use a different model provider, update the LLMConnection resource first.

### From the UI

1. Navigate to **http://localhost:3000/studio**
2. Load the **research-crew** from the crew selector
3. Click **Run** in the toolbar
4. Enter `{"topic": "AI agents"}` as the input JSON
5. Click **Run Crew**

The execution appears in the Executions page. Click it to see per-task status, outputs, and cost details.

---

## Step 5: View Execution Results

### CLI

```bash
# List all executions
uv run blackbeard executions

# Get details for a specific execution
uv run blackbeard status <execution-id>

# View execution events (step-by-step log)
uv run blackbeard events <execution-id>
```

### API

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/api/v1/executions
```

### UI

Navigate to the **Executions** page. Each execution shows status, crew name, duration, token usage, and cost. Click a row to expand task-level details and outputs.

---

## Step 6: Create Your Own Agent

### Via YAML and CLI

Create a file called `my-agent.yaml`:

```yaml
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: summarizer
spec:
  role: "Content Summarizer"
  goal: "Produce concise summaries of long-form content"
  backstory: >
    You are an expert at distilling complex information into clear,
    actionable summaries. You focus on key takeaways and skip filler.
  llm: "ref:llm-connections/ollama-qwen"
  max_iter: 5
  verbose: true
```

Validate and apply it:

```bash
uv run blackbeard validate -f my-agent.yaml
uv run blackbeard apply -f my-agent.yaml
```

Verify it was created:

```bash
uv run blackbeard list Agent
uv run blackbeard get Agent summarizer
```

### Via the Studio UI

1. Open the Studio
2. Drag an **Agent** node from the palette onto the canvas
3. Click the node to open the property panel
4. Fill in `role`, `goal`, and `backstory`
5. Click **Save**

The agent is now persisted as a resource and can be referenced by tasks and crews.

---

## Step 7: Build a Complete Crew

A crew needs at least one agent and one task. Here is a minimal example with two YAML files.

**`tasks/summarize.yaml`:**

```yaml
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: summarize-content
spec:
  description: "Summarize the following content: {content}"
  expected_output: "A 3-5 sentence summary covering the key points."
  agent: "ref:agents/summarizer"
```

**`crews/summary-crew.yaml`:**

```yaml
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: summary-crew
spec:
  process: sequential
  agents:
    - "ref:agents/summarizer"
  tasks:
    - "ref:tasks/summarize-content"
  verbose: true
```

Apply all resources (the CLI resolves dependencies automatically):

```bash
uv run blackbeard apply -f my-agent.yaml -f tasks/summarize.yaml -f crews/summary-crew.yaml
```

Run it:

```bash
uv run blackbeard kickoff summary-crew --input content="Blackbeard is a self-hosted agent management platform..." --wait
```

---

## Step 8: Import from the Marketplace

The Marketplace lets you import pre-built crews from git repositories or the bundled example library.

### From the UI

1. Navigate to **http://localhost:3000/marketplace**
2. Click **Import Built-in** to load all bundled example crews (research, code-review, content-pipeline, data-analysis, seo-writer, simple-crew, support-triage, chained-crews, and shared tools)
3. Or paste an HTTPS git URL to import resources from any public repository

### From the API

```bash
# Import built-in example crew
curl -X POST -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"url": "built-in"}' \
  http://localhost:8000/api/v1/marketplace/import

# Import from a git repository
curl -X POST -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/org/crew-templates.git", "path": "agents/"}' \
  http://localhost:8000/api/v1/marketplace/import
```

The import endpoint clones the repo (shallow, HTTPS only), finds all YAML files, validates them, and upserts the resources.

---

## Step 9: Train and Test Your Crew

Beyond standard execution, Blackbeard supports iterative training and evaluation runs.

### Train a crew

Training runs the crew multiple times and persists learning data for performance improvement.

```bash
uv run blackbeard train research-crew --input topic="AI agents" --iterations 3 --wait
```

### Test a crew

Test runs evaluate crew performance with metrics, using an LLM judge to score outputs.

```bash
uv run blackbeard test-crew research-crew --input topic="AI agents" --iterations 3 --wait
```

### From the UI

In the Studio toolbar, use the **Train** and **Test** buttons alongside the standard **Run** button.

---

## Step 10: Export Resources from the Server

Use the `export` command to download resources from the server as YAML files, useful for backup or version control.

```bash
# Export all resources as YAML
uv run blackbeard export --all > backup.yaml

# Export all resources to a directory
uv run blackbeard export --all -o backup/

# Export a single resource
uv run blackbeard export Agent researcher

# Inspect a single resource as JSON
uv run blackbeard get Agent researcher --json
```

---

## Step 11: Use the YAML Editor

The Studio property panel includes a bidirectional YAML editor (Monaco). You can switch between the form view and YAML view at any time -- changes sync automatically. This is useful for power users who prefer editing raw YAML.

---

## Step 12: Manage Users and Groups

### Create users

```bash
uv run blackbeard user invite -e alice@example.com -d "Alice"
```

### Manage groups

```bash
uv run blackbeard group create engineering --description "Engineering team"
uv run blackbeard group list
```

To add or remove group members, use the API:

```bash
# Add a member (requires user ID and group ID)
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"user_id": "<user-uuid>"}' \
  http://localhost:8000/api/v1/groups/<group-uuid>/members

# Remove a member
curl -X DELETE -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/groups/<group-uuid>/members/<user-uuid>
```

Groups can be used as subjects in RoleBindings for team-level RBAC.

---

## Next Steps

- **Add tools to agents** -- see `examples/research-crew/tools/` for examples of builtin and Python tools
- **Set up agent policies** -- create `AgentPolicy` resources to enforce spending budgets, tool allowlists, and delegation rules
- **Add guardrails** -- attach `Guardrail` resources to tasks for output validation (function, LLM, or schema-based)
- **Configure RBAC** -- create users, groups, roles, and role bindings for team access control
- **Use different LLM providers** -- create `LLMConnection` resources pointing to OpenAI, Anthropic, or Vertex AI
- **Build flows** -- create `Flow` resources to chain multiple crews into multi-step pipelines
- **Set up webhooks** -- register webhook URLs at `POST /api/v1/webhooks` for execution event delivery
- **Install the Python SDK** -- see [sdks/python/README.md](../sdks/python/README.md) for programmatic access
- **Read the YAML reference** -- see [docs/yaml-reference.md](yaml-reference.md) for every field on every resource kind
- **Explore the API** -- open http://localhost:8000/docs for interactive Swagger documentation (debug mode)
