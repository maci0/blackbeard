# Tool Examples

Blackbeard supports five tool types:

| Type | Description |
|------|-------------|
| `python` | Python class extending `crewai.tools.BaseTool`. Specify via `class_path`. |
| `builtin` | Built-in tools shipped with CrewAI or Blackbeard. Specify via `class_path` (tool name). |
| `wasm` | WebAssembly modules running in a sandboxed WASI runtime. Specify via `wasm_module`. |
| `mcp-stdio` | MCP servers launched as subprocesses. Specify via `command` and `args`. |
| `mcp-http` | Remote MCP servers accessed over HTTP. Specify via `url`. |

## WASM Tools

WASM tooling is supported. See `deploy/wit/tool.wit` for the interface specification.
WASM tools must export `run(input: string) -> tool-result` and optionally `describe() -> string`.

No example `.wasm` modules are included yet. The sandbox runtime (`blackbeard.engine.sandbox`) is implemented -- contribute examples by compiling a Rust/C/Go module against the WIT interface above.

## MCP Tools

MCP tools are attached to agents as CrewAI `mcps` (not in-process BaseTools). At crew build, `mcp-stdio` becomes `MCPServerStdio` and `mcp-http` becomes `MCPServerHTTP` (or `MCPServerSSE` when the URL ends with `/sse` or `config.transport` is `sse`).


### stdio example

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: filesystem-reader
spec:
  type: mcp-stdio
  command: "npx"
  args: ["-y", "@modelcontextprotocol/server-filesystem"]
  env:
    HOME: /tmp
  description: "Read files from the filesystem via MCP"
```

### HTTP example

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: remote-search
spec:
  type: mcp-http
  url: "http://localhost:3001/mcp"
  description: "Remote search service via MCP HTTP"
```

## Python Tool example

```yaml
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: web-search
spec:
  type: python
  class_path: crewai_tools.SerperDevTool
  description: "Search the web for current information"
  config:
    result_n: 5
```

## Sandbox

Tools with `sandbox: wasm` run inside a WebAssembly runtime with restricted WASI capabilities. The `env` capability passes a fixed set of safe environment variables (`LANG`, `LC_ALL`, `TZ`, `TERM`).
