# Tool sandbox tiers

Blackbeard isolates tool execution by tier. The effective tier is the maximum of:

1. `tool.spec.sandbox` (default `none`)
2. Agent policy `spec.sandbox.minimum_tier` (default `none`)

Python/builtin tools cannot run under `wasm` isolation; that tier is promoted to `docker`.

## Tiers

| Tier | Runtime | Notes |
|------|---------|--------|
| `none` | In-process | No isolation |
| `wasm` | Wasmtime | Only for `type: wasm` + `wasm_module` |
| `docker` / `podman` | OCI container | Disposable, caps dropped, read-only FS |
| `gvisor` | runsc | Syscall isolation on top of docker/podman |
| `microvm` | Firecracker or libkrun | Strongest isolation (needs host setup) |

## Declaring tools

### Command tool (recommended for real isolation)

```yaml
apiVersion: blackbeard.io/v1
kind: Tool
metadata:
  name: echo-safe
spec:
  type: python
  description: Echo via sandboxed shell
  sandbox: docker
  command: /bin/echo
  args: []
  # Optional:
  # image: alpine:3.20
  # capabilities: [network]   # required for outbound network
  # env:
  #   FOO: bar
```

At call time the agent args are passed as JSON on stdin. Use a wrapper script as `command` if you need to map JSON to CLI flags.

### WASM tool

```yaml
spec:
  type: wasm
  wasm_module: tools/my-tool.wasm
  description: Isolated WASM tool
  sandbox: wasm
```

Module must export `run(input_json) -> string`.

### Python class in a container

```yaml
spec:
  type: python
  class_path: crewai_tools.SerperDevTool
  sandbox: docker
  image: my-registry/tools-with-deps:1.0  # must include tool deps
  capabilities: [network]  # if the tool calls external APIs
  config:
    api_key: "..."
```

Without `capabilities: [network]`, containers run with `--network none`.

## Host requirements

| Tier | Requirement |
|------|-------------|
| docker/podman | `docker` or `podman` on PATH; `CONTAINER_RUNTIME=auto\|docker\|podman` |
| gvisor | `runsc` + docker/podman |
| microvm | Firecracker kernel/rootfs **or** libkrun (`krun`/`crun`) |
| wasm | `wasmtime` Python package (bundled with the API image) |

Default image: `CONTAINER_DEFAULT_IMAGE` (default `python:3.13-slim`).

## Policy floor

```yaml
kind: AgentPolicy
metadata:
  name: sandboxed
spec:
  sandbox:
    minimum_tier: docker
```

Any tool with `sandbox: none` is promoted to `docker` for agents using this policy. Agent build fails if the runtime is not available on the host.
