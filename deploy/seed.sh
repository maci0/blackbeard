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
    "parameters": {"temperature": 0.3, "max_tokens": 4096}
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

# ── Tools ────────────────────────────────────────────────────────────
curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "file-read"},
  "spec": {
    "type": "builtin",
    "class_path": "FileReadTool",
    "description": "Read the contents of a file from the local filesystem"
  }
}' > /dev/null
echo "  Tool/file-read"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "file-write"},
  "spec": {
    "type": "builtin",
    "class_path": "FileWriterTool",
    "description": "Write content to a file on the local filesystem"
  }
}' > /dev/null
echo "  Tool/file-write"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "directory-read"},
  "spec": {
    "type": "builtin",
    "class_path": "DirectoryReadTool",
    "description": "List files and directories in a given path"
  }
}' > /dev/null
echo "  Tool/directory-read"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "scrape-website"},
  "spec": {
    "type": "builtin",
    "class_path": "ScrapeWebsiteTool",
    "description": "Scrape and extract text content from a website URL"
  }
}' > /dev/null
echo "  Tool/scrape-website"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "pdf-search"},
  "spec": {
    "type": "builtin",
    "class_path": "PDFSearchTool",
    "description": "Search and extract text from PDF documents"
  }
}' > /dev/null
echo "  Tool/pdf-search"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "csv-search"},
  "spec": {
    "type": "builtin",
    "class_path": "CSVSearchTool",
    "description": "Search and query data in CSV files"
  }
}' > /dev/null
echo "  Tool/csv-search"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "json-search"},
  "spec": {
    "type": "builtin",
    "class_path": "JSONSearchTool",
    "description": "Search and query data in JSON files"
  }
}' > /dev/null
echo "  Tool/json-search"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "txt-search"},
  "spec": {
    "type": "builtin",
    "class_path": "TXTSearchTool",
    "description": "Search and extract text from plain text files"
  }
}' > /dev/null
echo "  Tool/txt-search"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "website-search"},
  "spec": {
    "type": "builtin",
    "class_path": "WebsiteSearchTool",
    "description": "Search for specific content within a website"
  }
}' > /dev/null
echo "  Tool/website-search"

curl -sf -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "vision"},
  "spec": {
    "type": "builtin",
    "class_path": "VisionTool",
    "description": "Analyze and describe images using vision models"
  }
}' > /dev/null
echo "  Tool/vision"

echo ""
echo "Seed complete. 16 resources created."
echo "Run a crew: curl -X POST $API/api/v1/crews/research-crew/kickoff -H 'X-API-Key: $KEY' -H 'Content-Type: application/json' -d '{\"inputs\":{\"topic\":\"AI agents\"}}'"
