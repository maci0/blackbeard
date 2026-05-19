# blackbeard-sdk

Python SDK for the Blackbeard Agent Management Platform.

## Install

```bash
pip install -e .
```

## Usage

```python
from blackbeard_sdk import BlackbeardClient

# API key auth
client = BlackbeardClient(base_url="http://localhost:8000", api_key="your-key")

# List agents
agents = client.list("Agent")

# Create an agent
client.create({
    "kind": "Agent",
    "apiVersion": "blackbeard/v1",
    "metadata": {"name": "researcher", "namespace": "default"},
    "spec": {"role": "Research Analyst", "goal": "Find relevant data"},
})

# Kick off a crew and wait for completion
execution = client.kickoff("my-crew", inputs={"topic": "AI safety"})
result = client.wait(execution["id"])
print(result["outputs"])
```
