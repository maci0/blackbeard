#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash deploy/seed.sh [OPTIONS]

Seed the Blackbeard database with RBAC roles, an example research crew,
and common tools (builtin + MCP). Requires a running Blackbeard stack.
Ollama with qwen3.6 is needed only to execute the seeded crew.

Resources are created via POST — re-running will upsert (update existing
resources and increment their version).

Options:
  --help, -h    Show this help

Environment:
  BLACKBEARD_SERVER      API base URL (default: http://localhost:8000)
  BLACKBEARD_API_KEY     API key     (default: change-me-in-production)

Examples:
  bash deploy/seed.sh
  BLACKBEARD_SERVER=http://prod:8000 BLACKBEARD_API_KEY=my-key bash deploy/seed.sh
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) usage ;;
  esac
done

API="${BLACKBEARD_SERVER:-http://localhost:8000}"
KEY="${BLACKBEARD_API_KEY:-change-me-in-production}"
H=(-H "X-API-Key: $KEY" -H "Content-Type: application/json")

# Verify server is reachable before seeding
if ! curl -sSf --connect-timeout 5 "$API/api/v1/health" > /dev/null 2>&1; then
  echo "Error: Cannot reach Blackbeard API at $API" >&2
  echo "  Is the server running? Try: curl $API/api/v1/health" >&2
  exit 1
fi

ERRORS=0
CREATED=0

seed() {
  local label="$1"
  shift
  local resp http_code
  resp=$(curl -sS -w '\n%{http_code}' "$@" 2>&1)
  http_code=${resp##*$'\n'}
  resp=${resp%$'\n'*}
  case "$http_code" in
    2??) echo "  + $label"; CREATED=$((CREATED + 1)) ;;
    *)
      echo "  x $label (HTTP $http_code)" >&2
      [ -n "$resp" ] && echo "$resp" | sed 's/^/    /' >&2
      ERRORS=$((ERRORS + 1))
      ;;
  esac
}

echo "Seeding Blackbeard at $API ..."

# ── RBAC Roles ──────────────────────────────────────────────────────

seed "Role/owner" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "owner"},
  "spec": {
    "description": "Full access to all resources and operations",
    "rules": [{"resources": ["*"], "verbs": ["*"]}]
  }
}'

seed "Role/admin" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "admin"},
  "spec": {
    "description": "Administrative access to all resources",
    "rules": [{"resources": ["*"], "verbs": ["get", "list", "create", "update", "delete", "run"]}]
  }
}'

seed "Role/developer" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "developer"},
  "spec": {
    "description": "Create and manage agents, tasks, crews, and tools",
    "rules": [
      {"resources": ["Agent", "Task", "Crew", "Tool", "LLMConnection", "Flow", "KnowledgeSource"], "verbs": ["get", "list", "create", "update", "delete"]},
      {"resources": ["Crew"], "verbs": ["run"]},
      {"resources": ["AgentPolicy", "Guardrail"], "verbs": ["get", "list"]}
    ]
  }
}'

seed "Role/operator" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "operator"},
  "spec": {
    "description": "Run crews and manage executions",
    "rules": [
      {"resources": ["Agent", "Task", "Crew", "Tool", "LLMConnection", "Flow", "KnowledgeSource"], "verbs": ["get", "list"]},
      {"resources": ["Crew"], "verbs": ["run"]},
      {"resources": ["AgentPolicy", "Guardrail"], "verbs": ["get", "list"]}
    ]
  }
}'

seed "Role/viewer" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "viewer"},
  "spec": {
    "description": "Read-only access to all resources",
    "rules": [{"resources": ["*"], "verbs": ["get", "list"]}]
  }
}'

seed "Role/policy-admin" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "policy-admin"},
  "spec": {
    "description": "Manage agent policies, guardrails, roles, and role bindings",
    "rules": [
      {"resources": ["AgentPolicy", "Guardrail", "Role", "RoleBinding"], "verbs": ["get", "list", "create", "update", "delete"]}
    ]
  }
}'

seed "Role/agent-unrestricted" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "agent-unrestricted"},
  "spec": {
    "description": "Unrestricted agent access — all tools and delegation",
    "subjectKinds": ["Agent"],
    "rules": [{"resources": ["Tool"], "verbs": ["invoke"]}, {"resources": ["Agent"], "verbs": ["delegate"]}]
  }
}'

seed "Role/agent-standard" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "agent-standard"},
  "spec": {
    "description": "Standard agent access — invoke tools but no delegation",
    "subjectKinds": ["Agent"],
    "rules": [{"resources": ["Tool"], "verbs": ["invoke"]}]
  }
}'

seed "Role/agent-read-only" -X POST "$API/api/v1/roles" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Role",
  "metadata": {"name": "agent-read-only"},
  "spec": {
    "description": "Read-only agent access — no tool invocation or delegation",
    "subjectKinds": ["Agent"],
    "rules": [{"resources": ["*"], "verbs": ["get", "list"]}]
  }
}'

# ── Default admin user (DEBUG mode only) ────────────────────────────
if [ "${DEBUG:-false}" = "true" ]; then
  ADMIN_PASSWORD="${BLACKBEARD_ADMIN_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")}"
  echo "  (DEBUG mode: creating default admin user)"
  admin_resp=$(curl -sSf -X POST "$API/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"admin@blackbeard.sh\", \"password\": \"${ADMIN_PASSWORD}\", \"display_name\": \"Admin\"}" 2>&1) && \
    { echo "  + User/admin@blackbeard.sh"; echo "    Admin password (stderr only): $ADMIN_PASSWORD" >&2; } || \
    echo "  ~ User/admin@blackbeard.sh (already exists or skipped)"
fi

# ── LLM Connection: Ollama qwen3.6 ──────────────────────────────────
seed "LLMConnection/ollama-qwen" -X POST "$API/api/v1/llm-connections" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "LLMConnection",
  "metadata": {"name": "ollama-qwen"},
  "spec": {
    "provider": "ollama",
    "model": "qwen3.6",
    "parameters": {"temperature": 0.3, "max_tokens": 4096}
  }
}'

# ── Agent: Researcher ────────────────────────────────────────────────
seed "Agent/researcher" -X POST "$API/api/v1/agents" "${H[@]}" -d '{
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
}'

# ── Agent: Writer ────────────────────────────────────────────────────
seed "Agent/writer" -X POST "$API/api/v1/agents" "${H[@]}" -d '{
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
}'

# ── Task: Research ───────────────────────────────────────────────────
seed "Task/research-topic" -X POST "$API/api/v1/tasks" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Task",
  "metadata": {"name": "research-topic"},
  "spec": {
    "description": "Write 3 key facts about {topic} in bullet point format.",
    "expected_output": "3 bullet points about {topic}, each one sentence.",
    "agent": "ref:agents/researcher"
  }
}'

# ── Task: Write report ───────────────────────────────────────────────
seed "Task/write-report" -X POST "$API/api/v1/tasks" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Task",
  "metadata": {"name": "write-report"},
  "spec": {
    "description": "Using the research facts provided, write a 2-3 sentence summary about {topic}.",
    "expected_output": "A short summary about {topic} in 2-3 sentences.",
    "agent": "ref:agents/writer",
    "context": ["ref:tasks/research-topic"]
  }
}'

# ── Crew: Research Crew ──────────────────────────────────────────────
seed "Crew/research-crew" -X POST "$API/api/v1/crews" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Crew",
  "metadata": {"name": "research-crew"},
  "spec": {
    "process": "sequential",
    "agents": ["ref:agents/researcher", "ref:agents/writer"],
    "tasks": ["ref:tasks/research-topic", "ref:tasks/write-report"],
    "verbose": true,
    "memory": true
  }
}'

# ── Tools ────────────────────────────────────────────────────────────
seed "Tool/file-read" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "file-read"},
  "spec": {
    "type": "builtin",
    "class_path": "FileReadTool",
    "description": "Read the contents of a file from the local filesystem"
  }
}'

seed "Tool/file-write" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "file-write"},
  "spec": {
    "type": "builtin",
    "class_path": "FileWriterTool",
    "description": "Write content to a file on the local filesystem"
  }
}'

seed "Tool/directory-read" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "directory-read"},
  "spec": {
    "type": "builtin",
    "class_path": "DirectoryReadTool",
    "description": "List files and directories in a given path"
  }
}'

seed "Tool/scrape-website" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "scrape-website"},
  "spec": {
    "type": "builtin",
    "class_path": "ScrapeWebsiteTool",
    "description": "Scrape and extract text content from a website URL"
  }
}'

seed "Tool/pdf-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "pdf-search"},
  "spec": {
    "type": "builtin",
    "class_path": "PDFSearchTool",
    "description": "Search and extract text from PDF documents"
  }
}'

seed "Tool/csv-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "csv-search"},
  "spec": {
    "type": "builtin",
    "class_path": "CSVSearchTool",
    "description": "Search and query data in CSV files"
  }
}'

seed "Tool/json-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "json-search"},
  "spec": {
    "type": "builtin",
    "class_path": "JSONSearchTool",
    "description": "Search and query data in JSON files"
  }
}'

seed "Tool/txt-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "txt-search"},
  "spec": {
    "type": "builtin",
    "class_path": "TXTSearchTool",
    "description": "Search and extract text from plain text files"
  }
}'

seed "Tool/website-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "website-search"},
  "spec": {
    "type": "builtin",
    "class_path": "WebsiteSearchTool",
    "description": "Search for specific content within a website"
  }
}'

seed "Tool/vision" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "vision"},
  "spec": {
    "type": "builtin",
    "class_path": "VisionTool",
    "description": "Analyze and describe images using vision models"
  }
}'

# ── MCP Servers (no auth required) ───────────────────────────────────
seed "Tool/mcp-filesystem" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-filesystem"},
  "spec": {
    "type": "mcp-stdio",
    "description": "Read, write, and manage files on the local filesystem via MCP",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp/workspace"]
  }
}'

seed "Tool/mcp-fetch" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-fetch"},
  "spec": {
    "type": "mcp-stdio",
    "description": "Fetch and extract content from URLs (web pages, APIs)",
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}'

seed "Tool/mcp-memory" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-memory"},
  "spec": {
    "type": "mcp-stdio",
    "description": "Persistent memory via a knowledge graph — store and retrieve entities and relations",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-memory"]
  }
}'

seed "Tool/mcp-brave-search" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-brave-search"},
  "spec": {
    "type": "mcp-stdio",
    "description": "Web search via Brave Search API (requires BRAVE_API_KEY env var)",
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-server-brave-search"]
  }
}'

seed "Tool/mcp-context7" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-context7"},
  "spec": {
    "type": "mcp-http",
    "description": "Look up library documentation and code examples — no auth required",
    "url": "https://mcp.context7.com/sse"
  }
}'

seed "Tool/mcp-sequentialthinking" -X POST "$API/api/v1/tools" "${H[@]}" -d '{
  "apiVersion": "blackbeard/v1",
  "kind": "Tool",
  "metadata": {"name": "mcp-sequentialthinking"},
  "spec": {
    "type": "mcp-stdio",
    "description": "Dynamic problem-solving through structured sequential thinking with revision support",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
  }
}'

echo ""
echo "Seed complete: $CREATED created, $ERRORS failed."
if [ "$ERRORS" -gt 0 ]; then
  echo "Some resources failed — check server logs for details." >&2
  exit 1
fi

echo ""
echo "Try it:"
echo "  blackbeard kickoff research-crew --input topic=\"AI agents\" --wait"
