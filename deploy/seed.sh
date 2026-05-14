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
    "model": "qwen3.5",
    "parameters": {"temperature": 0.7, "max_tokens": 2048}
  }
}' > /dev/null
echo "  LLMConnection/ollama-qwen"

# ── Agent: Researcher ────────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/agents" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Agent",
  "metadata": {"name": "researcher"},
  "spec": {
    "role": "Research Analyst",
    "goal": "Find accurate and relevant information on any given topic",
    "backstory": "You are an expert research analyst with deep knowledge of search techniques and information synthesis. You excel at finding key facts and summarizing complex topics. /no_think",
    "llm": "ref:llm-connections/ollama-qwen",
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
    "role": "Content Writer",
    "goal": "Write clear, engaging content based on research findings",
    "backstory": "You are a skilled content writer who transforms complex research into readable, well-structured prose. You focus on clarity and accuracy. /no_think",
    "llm": "ref:llm-connections/ollama-qwen",
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
    "description": "Research the given topic thoroughly. Identify key facts, recent developments, and important context. Compile your findings into a structured summary.",
    "expected_output": "A detailed bullet-point summary of key findings with sources",
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
    "description": "Write a comprehensive report based on the research findings. Structure it with an introduction, key sections, and conclusion.",
    "expected_output": "A well-structured report in markdown format, 500-1000 words",
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
