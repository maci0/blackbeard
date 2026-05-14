#!/bin/bash
set -euo pipefail

API="${BLACKBEARD_API:-http://localhost:8000}"
KEY="${BLACKBEARD_API_KEY:-change-me-in-production}"
H=(-H "X-API-Key: $KEY" -H "Content-Type: application/json")

echo "Seeding Blackbeard at $API ..."

# ── LLM Connection: Ollama qwen3.5 ──────────────────────────────────
curl -sf -X POST "$API/api/v1/llm-connections" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "LLMConnection",
  "metadata": {"name": "ollama-qwen"},
  "spec": {
    "provider": "ollama",
    "model": "qwen3.6",
    "base_url": "http://host.docker.internal:11434",
    "parameters": {"temperature": 0.3, "max_tokens": 512}
  }
}' > /dev/null
echo "  LLMConnection/ollama-qwen"

# ── Agent: Researcher ────────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/agents" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Agent",
  "metadata": {"name": "researcher"},
  "spec": {
    "role": "Researcher",
    "goal": "List key facts about a topic",
    "backstory": "You find facts and list them. Be brief. /no_think",
    "llm": "ref:llm-connections/ollama-qwen",
    "max_iter": 5,
    "verbose": true
  }
}' > /dev/null
echo "  Agent/researcher"

# ── Agent: Writer ────────────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/agents" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Agent",
  "metadata": {"name": "writer"},
  "spec": {
    "role": "Writer",
    "goal": "Write a short summary from given facts",
    "backstory": "You write clear, short summaries. Be brief. /no_think",
    "llm": "ref:llm-connections/ollama-qwen",
    "max_iter": 5,
    "verbose": true
  }
}' > /dev/null
echo "  Agent/writer"

# ── Task: Research ───────────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/tasks" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Task",
  "metadata": {"name": "research-topic"},
  "spec": {
    "description": "Write 3 key facts about {topic} in bullet point format.",
    "expected_output": "3 bullet points about {topic}, each one sentence.",
    "agent": "ref:agents/researcher"
  }
}' > /dev/null
echo "  Task/research-topic"

# ── Task: Write report ───────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/tasks" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Task",
  "metadata": {"name": "write-report"},
  "spec": {
    "description": "Using the research facts provided, write a 2-3 sentence summary about {topic}.",
    "expected_output": "A short summary about {topic} in 2-3 sentences.",
    "agent": "ref:agents/writer",
    "context": ["ref:tasks/research-topic"]
  }
}' > /dev/null
echo "  Task/write-report"

# ── Crew: Research Crew ──────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/crews" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Crew",
  "metadata": {"name": "research-crew"},
  "spec": {
    "process": "sequential",
    "agents": ["ref:agents/researcher", "ref:agents/writer"],
    "tasks": ["ref:tasks/research-topic", "ref:tasks/write-report"],
    "verbose": true
  }
}' > /dev/null
echo "  Crew/research-crew"

echo ""
echo "Seed complete. 6 resources created."
echo "Run a crew: curl -X POST $API/api/v1/crews/research-crew/kickoff -H 'X-API-Key: $KEY' -H 'Content-Type: application/json' -d '{\"inputs\":{\"topic\":\"AI agents\"}}'"
