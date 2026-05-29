# blackbeard-sdk

Python SDK for the Blackbeard Agent Management Platform.

## Install

```bash
pip install -e .
# or with uv
cd sdks/python && uv sync
```

**Requirements:** Python 3.10+, httpx

## Usage

### API Key Authentication

```python
from blackbeard_sdk import BlackbeardClient

client = BlackbeardClient(base_url="http://localhost:8000", api_key="your-key")
```

### JWT Authentication

```python
client = BlackbeardClient(base_url="http://localhost:8000")
client.login("user@example.com", "password123")
```

### Resource CRUD

All 13 resource kinds are supported: Agent, Task, Crew, Tool, LLMConnection, AgentPolicy, Guardrail, Flow, KnowledgeSource, Role, RoleBinding, Automation, Namespace.

```python
# List agents
agents = client.list("Agent")

# List with label filtering
prod_agents = client.list("Agent", label_selector="env=prod,team=ml")

# Get a specific resource
agent = client.get("Agent", "researcher")

# Create a resource
client.create({
    "kind": "Agent",
    "apiVersion": "blackbeard/v1",
    "metadata": {"name": "researcher", "project": "default"},
    "spec": {
        "role": "Research Analyst",
        "goal": "Find relevant data",
        "backstory": "You are a skilled researcher.",
    },
})

# Update a resource (requires version for optimistic locking)
client.update("Agent", "researcher", {
    "spec": {"verbose": False},
    "version": 1,
})

# Delete a resource
client.delete("Agent", "researcher")

# Bulk apply (sequential upsert)
client.apply([agent_dict, task_dict, crew_dict])

# Export all resources as YAML
yaml_str = client.export_all(namespace="default")
```

### Crew Execution

```python
# Kick off a crew and wait for completion
execution = client.kickoff("my-crew", inputs={"topic": "AI safety"})
result = client.wait(execution["id"])
print(result["outputs"])

# Train a crew (iterative improvement)
execution = client.train("my-crew", inputs={"topic": "AI"}, n_iterations=3)
result = client.wait(execution["id"])

# Test a crew (evaluation with metrics)
execution = client.test("my-crew", inputs={"topic": "AI"}, n_iterations=3)
result = client.wait(execution["id"])

# Run a flow (multi-step pipeline)
execution = client.run_flow("my-flow", inputs={"topic": "AI"})
result = client.wait(execution["id"])

# Cancel an execution
client.cancel(execution["id"])

# List executions with filters
execs = client.list_executions(crew_name="my-crew", status="completed")

# Human-in-the-loop: respond to a paused execution
client.respond(execution["id"], "Approved — proceed with the analysis.")

# Retry a failed/cancelled execution (creates a new execution)
new_exec = client.retry(execution["id"])

# Get execution events (for streaming/replay)
events = client.get_execution_events(execution["id"])

# Get LiteLLM spend data
spend = client.get_execution_spend(execution["id"])
```

### Health Checks

```python
# Liveness check
client.health()

# Readiness check (database, Valkey, LiteLLM)
client.readiness()
```

### Auth Management

```python
# Register a new user
client.register("alice@example.com", "password123", "Alice")

# Login
client.login("alice@example.com", "password123")

# Refresh token
client.refresh(refresh_token)

# Get current user
client.whoami()

# Generate or rotate personal API key (requires JWT auth)
result = client.generate_api_key()
print(result["api_key"])

# Revoke personal API key
client.revoke_api_key()
```

### Context Manager

```python
with BlackbeardClient(base_url="http://localhost:8000", api_key="key") as client:
    agents = client.list("Agent")
    # client.close() is called automatically
```

## API Coverage

| Area | Methods |
|------|---------|
| Auth | `login`, `register`, `refresh`, `whoami`, `generate_api_key`, `revoke_api_key` |
| Resources | `list`, `get`, `create`, `update`, `delete`, `apply`, `export_all` |
| Executions | `kickoff`, `train`, `test`, `run_flow`, `cancel`, `retry`, `wait`, `respond`, `get_execution`, `list_executions`, `get_execution_events`, `get_execution_spend` |
| Health | `health`, `readiness` |
