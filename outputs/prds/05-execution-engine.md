# PRD 05 — Execution Engine

## 1. Purpose

The Execution Engine is the runtime that loads YAML resource definitions, resolves references, constructs the agent/task/crew/flow runtime graph, invokes LLMs, dispatches tool calls through sandboxed execution environments, manages state, enforces agent policies (PRD 03), and produces structured outputs. It is the only module that actually "runs" agent workloads.

### 1.1 MVP Scope

**Implemented:** Sequential and hierarchical crew execution. Flow execution with all step types: crew, function, router (Python function dispatch), condition (safe expression eval), and transform (WASM data massaging). Train and test modes via CrewAI native APIs. Budget enforcement via LiteLLM virtual keys. Guardrails (function, LLM, schema). AgentPolicy enforcement (tool allowlist/denylist, delegation, sandbox tier). Workflow hooks (before/after kickoff, before/after task, before/after flow step, on_error). HITL respond endpoint. SSE + WebSocket streaming. Webhooks. Automation triggers (cron, webhook, API). gRPC API on :50051. WASM sandbox tier.

**Deferred to post-MVP:** Temporal workflow backend, Docker and MicroVM sandbox tiers, dynamic task creation in hierarchical mode, warm container/VM pools.

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    API Gateway / CLI                          │
│   POST /api/v1/crews/{name}/kickoff (MVP)                      │
│   POST /api/v1/automations/{name}/kickoff (post-MVP)           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   Execution Scheduler                         │
│  Receives kickoff requests, creates Execution records,        │
│  dispatches to worker pool (in-process or Temporal)           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   Execution Worker                            │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐      │
│  │  Resource    │  │  Runtime     │  │  LLM           │      │
│  │  Loader      │  │  Graph       │  │  Dispatcher    │      │
│  │  (YAML→obj)  │  │  Builder     │  │  (multi-model) │      │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘      │
│         │                │                   │               │
│  ┌──────▼──────────────▼──────────────────▼──────────────┐  │
│  │              Execution Loop                             │  │
│  │  For each task in process order:                         │  │
│  │    1. Inject context from prior tasks                    │  │
│  │    2. Build agent prompt (system + task + context)       │  │
│  │    3. Policy check: is this LLM allowed? Budget OK?      │  │
│  │    4. LLM call → parse response                         │  │
│  │    5. If tool call → policy check → sandbox dispatch     │  │
│  │    6. Repeat until max_iter or final answer              │  │
│  │    7. Run guardrails → retry if failed                   │  │
│  │    8. Execute callbacks                                  │  │
│  │    9. Store result, emit events, checkpoint              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Policy        │  │  Sandbox     │  │  Callback    │      │
│  │  Enforcer      │  │  Manager     │  │  Resolver    │      │
│  │  (PRD 03)      │  │  (section 6) │  │  (imports)   │      │
│  └────────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐                        │
│  │  State Manager │  │  Memory      │                        │
│  │  (checkpoint,  │  │  Manager     │                        │
│  │   flow state)  │  │  (STM/LTM)   │                        │
│  └────────────────┘  └──────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

## 3. Execution Lifecycle

### 3.1 Kickoff

```
POST /api/v1/automations/{name}/kickoff
{
  "inputs": {"topic": "AI safety"},
  "execution_mode": "async",           // async | sync | stream
  "checkpoint_from": null              // resume from checkpoint UUID
}

→ 202 Accepted
{
  "execution_id": "exec-abc123",
  "status": "queued",
  "status_url": "/api/v1/executions/exec-abc123"
}
```

**MVP endpoint**: For MVP (before Automation resources exist), crews are kicked off directly:

```
POST /api/v1/crews/{name}/kickoff
{
  "inputs": {"topic": "AI safety"}
}

→ 202 Accepted
{
  "id": "exec-abc123",
  "crew_name": "research-crew",
  "crew_namespace": "default",
  "status": "queued",
  "inputs": {"topic": "AI safety"},
  "total_tokens": 0,
  "cost_usd": "0",
  "created_at": "2026-05-10T12:00:00Z",
  "tasks": []
}
```

The execution engine code path is identical regardless of entry point. The only difference is where runtime defaults come from (Automation resource vs. namespace/org defaults).

Post-MVP, the Automation-based endpoint (`/api/v1/automations/{name}/kickoff`) wraps this with deployment versioning, triggers, and runtime configuration.

### 3.2 Execution States

```
queued → loading → running → completed
                     │
                     ├──→ failed
                     ├──→ cancelled
                     ├──→ waiting_for_human ──→ cancelled
                     │         │
                     │         └──→ failed (HITL timeout, default 24h)
                     └──→ paused (checkpoint) ──→ cancelled
                               │
                               └──→ failed (TTL expired, default 7d)
```

**Terminal states:** `completed`, `failed`, `cancelled`. Timeout behavior: agent `max_execution_time` exceeded → `failed` with `error_code: EXECUTION_TIMEOUT`. HITL waiting has a configurable timeout (default 24h, set via `spec.human_feedback.timeout` on the Task resource) ... expiry → `failed`. Paused checkpoints have a TTL (default 7d, configurable via PlatformConfig `execution.checkpoint_ttl`) ... expiry → `failed` with garbage collection.

### 3.3 Status Polling

```
GET /api/v1/executions/{execution_id}
{
  "execution_id": "exec-abc123",
  "status": "running",
  "progress": {
    "total_tasks": 4,
    "completed_tasks": 2,
    "current_task": "research-ai",
    "current_agent": "researcher"
  },
  "started_at": "2026-05-10T12:00:00Z",
  "elapsed_seconds": 45,
  "token_usage": {
    "prompt_tokens": 12400,
    "completion_tokens": 3200,
    "total_tokens": 15600,
    "estimated_cost_usd": 0.23
  }
}
```

### 3.4 Cancellation

```
PATCH /api/v1/executions/{id}/cancel
{
  "reason": "User requested cancellation"    // optional
}

→ 200 OK
{
  "execution_id": "exec-abc123",
  "status": "cancelled",
  "cancelled_at": "2026-05-10T12:05:00Z"
}
```

Cancellation is best-effort for running executions. The in-flight LLM call may complete before cancellation takes effect; its result is discarded. Active sandbox instances are terminated immediately. Cancellation from `queued` or `loading` states is immediate.

Cancelled by user or API request. Active LLM calls terminate best-effort; sandbox instances destroyed.

## 4. Resource Loading

1. Fetch the Crew or Flow resource directly (MVP) or via the Automation record (post-MVP).
2. Recursively resolve all `ref:` dependencies (agents, tasks, tools, knowledge sources).
3. Resolve the **AgentPolicy** for each agent (agent-level > crew-level > namespace-level > org default — PRD 03, section 3.1).
4. Resolve the **Sandbox profile** for each agent based on its policy's `code_execution.sandbox` and each tool's `sandbox` field.
5. Build the execution graph (DAG for sequential; tree for hierarchical; event graph for flows).
6. Validate the graph: no cycles (except explicit flow loops), all refs resolved, all tools available and policy-allowed.
7. Resolve Python callback paths: import the modules, verify callables exist.
8. Pre-warm sandboxes: start WASM runtimes, pull Docker images if needed.
9. If any resolution fails → `status: failed` with a clear error listing what's missing.

## 5. Process Modes

### 5.1 Sequential
Tasks execute in order. Output of task N is available as context to task N+1 (and to any task that declares it in `context`).

### 5.2 Hierarchical
A **Manager Agent** (specified by `manager_llm` or `manager_agent`) receives all tasks, delegates them to agents based on role/capability, collects results, and decides task ordering dynamically.

### 5.3 Flow (Event-Driven)
Steps connected by `@start`, `@listen`, `or_`, `and_`, and `@router` semantics:
- Steps fire when their trigger condition is met.
- Multiple steps can fire in parallel when independent.
- Router steps produce labelled outputs that activate downstream listeners.
- Human-in-the-loop steps pause execution and wait for external input.

---

## 6. Sandbox Architecture

Every tool invocation and code execution runs inside a **sandbox**. The sandbox tier is determined by the tool's `sandbox` field, the agent's `AgentPolicy`, and an org-level default. The Sandbox Manager selects the lightest tier that satisfies the policy constraints.

### 6.1 Sandbox Resource

```yaml
# sandboxes/high-isolation.yaml
apiVersion: blackbeard/v1
kind: Sandbox
metadata:
  name: high-isolation
  description: "Full container isolation for untrusted tool code"
spec:
  tier: docker                        # none | wasm | docker | microvm
  
  # ── Resource limits (apply to all tiers except in-process) ──
  limits:
    max_cpu_cores: 1
    max_memory_mb: 512
    max_execution_time: 60            # seconds per invocation
    max_disk_mb: 256                  # writable scratch space
    max_pids: 64                      # process count limit (docker/microvm)
  
  # ── Network policy ──────────────────────────────────────────
  network:
    mode: allowlist                   # none | allowlist | denylist | unrestricted
    allow:
      - "api.openai.com:443"
      - "api.anthropic.com:443"
      - "*.google.com:443"
    deny:
      - "169.254.169.254"            # cloud metadata
      - "10.0.0.0/8"
      - "172.16.0.0/12"
      - "192.168.0.0/16"
    dns:
      allowed: true
      servers: ["8.8.8.8"]           # override DNS to prevent internal resolution
  
  # ── Enforcement relationship ────────────────────────────────
  # The Sandbox resource's `network` section defines template defaults.
  # At runtime, the effective network rules come from the agent's
  # AgentPolicy `network.outbound` configuration (PRD 03, section 3).
  # The AgentPolicy takes precedence — the Sandbox template is only
  # used when no AgentPolicy is specified. All network patterns follow
  # the matching semantics defined in PRD 03, section 3 (suffix matching,
  # optional port).
  #
  # Port is optional. When omitted, all ports are allowed for the
  # matching host.
  
  # ── Filesystem policy ───────────────────────────────────────
  filesystem:
    root: tmpfs                       # tmpfs | overlay | bind
    writable_paths:
      - "/tmp"
      - "/workspace/outputs"
    readonly_paths:
      - "/workspace/data"             # input data mounted read-only
    denied_paths:
      - "/etc/shadow"
      - "/proc/*/environ"
    mount_inputs: true                # mount task inputs as files
    persist_outputs: true             # copy outputs out after execution
  
  # ── Capabilities ────────────────────────────────────────────
  capabilities:
    allow_network: true               # can the sandbox make outbound connections?
    allow_filesystem: true            # can it read/write any files?
    allow_subprocess: false           # can it spawn child processes?
    allow_env_vars: true              # can it read environment variables?
    allow_gpu: false                  # GPU passthrough?
  
  # ── Tier-specific config ────────────────────────────────────
  wasm:
    runtime: wasmtime                 # wasmtime | wasmer | wazero | spin
    fuel_limit: 1000000000            # instruction fuel (wasmtime)
    wasi_version: preview2
    allowed_wasi_capabilities:
      - "wasi:io/streams"
      - "wasi:http/outgoing-handler"  # only if network allowed
      - "wasi:filesystem/preopens"    # only if filesystem allowed
      - "wasi:clocks/monotonic-clock"
    # NOT allowed by default:
    # - "wasi:sockets/*"              # raw sockets
    # - "wasi:cli/environment"        # env var access (unless allow_env_vars)
    component_model: true             # WASM Component Model support
    
  docker:
    image: "blackbeard/sandbox:latest"   # base image
    runtime: runc                     # runc | runsc (gVisor) | kata
    seccomp_profile: "strict"         # strict | moderate | unconfined
    apparmor_profile: "blackbeard-sandbox"
    readonly_rootfs: true
    no_new_privileges: true
    user: "sandbox:sandbox"           # non-root
    
  microvm:
    provider: firecracker             # firecracker | cloud-hypervisor
    kernel: "vmlinux-5.10"
    vcpus: 1
    memory_mb: 512
```

### 6.2 Sandbox Tiers

Four execution tiers, **all production-valid**. The right tier depends on trust level, performance requirements, and compliance posture — not on environment (dev vs prod).

```
┌──────────────────────────────────────────────────────────────────────┐
│                        EXECUTION TIERS                               │
│                                                                      │
│  Isolation    ───────────────────────────────────────────────▶        │
│  Performance  ◀───────────────────────────────────────────────       │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────┐       │
│  │   none   │  │   WASM   │  │   Docker     │  │  MicroVM   │       │
│  │          │  │          │  │              │  │            │       │
│  │ ~0ms     │  │ ~5ms     │  │ ~500ms       │  │ ~1-3s      │       │
│  │ zero     │  │ memory+  │  │ OS-level     │  │ hardware   │       │
│  │ overhead │  │ compute  │  │ namespace    │  │ virtualiz. │       │
│  │          │  │          │  │              │  │            │       │
│  │ you own  │  │ default  │  │ untrusted    │  │ hostile /  │       │
│  │ the code │  │ tier     │  │ code         │  │ multi-ten. │       │
│  └──────────┘  └──────────┘  └──────────────┘  └────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

| Tier | Startup | Isolation | Use Case | Network | FS | Subprocess |
|------|---------|-----------|----------|---------|-------|------------|
| **none** | ~0ms | None — runs in the engine's Python process. | First-party tools you own and trust: internal SDKs, search wrappers, RAG adapters, file readers, DB connectors. Ideal when tool code is version-controlled in the same repo as the crew and reviewed like any other production code. Also appropriate for performance-critical hot paths where even 5ms WASM overhead matters. | Host | Host | Host |
| **WASM** | ~5ms | Memory-safe, capability-based. Code cannot escape the linear memory sandbox. Deterministic fuel metering prevents infinite loops. | **Recommended default.** Most tools: HTTP clients, parsers, data transforms, calculators, third-party tool packages. WASI capabilities granted granularly — no network or filesystem unless explicitly allowed. | Via `wasi:http` capability only | Via `wasi:filesystem` preopens only | Not possible |
| **Docker** | ~500ms (warm: ~50ms) | OS-level namespace/cgroup isolation. Optional gVisor (`runsc`) for syscall filtering. | Tools that need a full POSIX environment: shell commands, pip packages, system libraries, multi-file code execution, tools that spawn subprocesses. | Via network policy / iptables | Via mount policy | Via PID namespace |
| **MicroVM** | ~1-3s (warm: ~200ms) | Hardware virtualisation. Separate kernel. Strongest isolation boundary. | Highest assurance: running user-uploaded arbitrary code, multi-tenant agent execution, compliance-critical workloads (SOC2, HIPAA, FedRAMP). | Via virtual NIC + firewall | Via virtual block device | Fully isolated |

#### Tier: `none` (non-sandboxed) — detail

Non-sandboxed execution is a **deliberate, policy-governed choice**, not a security gap:

- **When to use**: The tool is authored by your team, lives in your repo, passes code review, and is deployed alongside the engine. Examples: a thin wrapper around your company's internal API client, a Pandas data transform, a custom RAG retriever.
- **Policy control**: An AgentPolicy can explicitly allow or forbid `none` tier via `minimum_sandbox_tier: none`. An org-wide default can mandate `minimum_sandbox_tier: wasm` to prevent any agent from using `none` without an explicit override.
- **Accountability**: Even in `none` mode, all tool calls are audit-logged (tool name, input hash, duration, output hash, calling agent, calling user). The tool runs under the engine's process identity with the same env vars the engine has — this is precisely why trust matters.
- **Guardrails still apply**: AgentPolicy tool allowlists, invocation limits, and cost ceilings are enforced regardless of sandbox tier. Sandboxing controls *isolation*; policy controls *authorization*. They are orthogonal.
- **Performance**: Zero serialisation overhead — input/output are native Python objects. No IPC, no container lifecycle, no fuel metering. For tools called hundreds of times per execution (e.g., a vector similarity function), this matters.

```yaml
# Example: marking a tool as trusted / non-sandboxed
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: internal-crm-lookup
spec:
  type: python
  implementation: "mycompany.tools:CRMLookup"
  sandbox: none                       # explicit: run in-process
  trusted: true                       # informational flag for UI/audit
  description: "Look up customer records in internal CRM"
```

```yaml
# AgentPolicy allowing non-sandboxed execution for specific tools
spec:
  sandbox:
    minimum_tier: none                # this agent is allowed to use non-sandboxed tools
    default_tier: wasm                # but defaults to WASM for tools that don't specify
  tools:
    mode: allowlist
    allow:
      - ref: tools/internal-crm-lookup   # trusted, runs as none
      - ref: tools/serper-search          # third-party, runs as wasm (default)
```

### 6.3 WASM Tool Execution (Detail)

WASM is the **recommended default** sandbox because it provides strong isolation with near-zero overhead:

```
Tool invocation
    │
    ▼
┌──────────────────────────────────────────────┐
│  Sandbox Manager                              │
│                                              │
│  1. Load .wasm module (cached after first)   │
│  2. Create WASM instance with fuel limit     │
│  3. Grant WASI capabilities per policy:      │
│     ├── wasi:http/outgoing-handler (if net)  │
│     ├── wasi:filesystem/preopens (if fs)     │
│     ├── wasi:io/streams (always)             │
│     └── wasi:clocks (always)                 │
│  4. Serialize tool input → WASM memory       │
│  5. Call tool's exported function             │
│  6. ─── execution (fuel-limited) ───         │
│  7. Read result from WASM memory             │
│  8. If fuel exhausted → timeout error        │
│  9. Destroy instance (memory freed)          │
│  10. Return result to agent                  │
└──────────────────────────────────────────────┘
```

**WASM tool packaging**:
```
my-tool/
├── tool.wasm              # compiled WASM module (from Rust, Go, C, Python-via-componentize-py, JS-via-javy)
├── tool.yaml              # Tool resource definition
└── wit/
    └── tool.wit           # WIT interface definition (Component Model)
```

**WIT interface** (tools implement this contract):
```wit
package blackbeard:tool@0.1.0;

interface tool {
    record tool-input {
        parameters: list<tuple<string, string>>,
        context: option<string>,
    }
    
    record tool-output {
        result: string,
        metadata: option<list<tuple<string, string>>>,
        error: option<string>,
    }
    
    invoke: func(input: tool-input) -> tool-output;
}

world blackbeard-tool {
    export tool;
    
    // Imported capabilities (granted by sandbox policy)
    import wasi:http/outgoing-handler@0.2.0;
    import wasi:filesystem/preopens@0.2.0;
    import wasi:io/streams@0.2.0;
    import wasi:clocks/monotonic-clock@0.2.0;
}
```

**Why WASM as default**:

| Property | Benefit |
|----------|---------|
| Memory safety | Linear memory model — tool can't read engine memory |
| Capability-based | No network/FS unless explicitly granted via WASI |
| Fuel metering | Deterministic execution limits — no infinite loops |
| Fast startup | ~5ms vs ~500ms for Docker — critical for per-tool-call sandboxing |
| Portable | Same .wasm binary runs on Linux, macOS, ARM, x86 |
| Language-agnostic | Compile from Rust, Go, C, Python (componentize-py), JS (javy), etc. |
| No daemon | No Docker daemon needed — just a WASM runtime library |
| Cacheable | Module compilation cached; instantiation is cheap |

### 6.4 Docker Sandbox Execution (Detail)

For tools that need a full OS environment:

```
Tool invocation
    │
    ▼
┌──────────────────────────────────────────────┐
│  Sandbox Manager                              │
│                                              │
│  1. Select/pull Docker image                 │
│  2. Create container with:                   │
│     ├── Resource limits (cpu, mem, pids)      │
│     ├── Seccomp profile (strict)             │
│     ├── AppArmor profile                     │
│     ├── Read-only rootfs                     │
│     ├── Non-root user                        │
│     ├── No new privileges                    │
│     ├── Network policy (iptables rules)      │
│     └── Filesystem mounts (RO inputs, RW tmp)│
│  3. Serialize input → stdin / mounted file   │
│  4. Execute tool command                     │
│  5. Stream stdout/stderr with timeout        │
│  6. Read output file / stdout                │
│  7. Destroy container                        │
│  8. Return result to agent                   │
└──────────────────────────────────────────────┘
```

**Optional gVisor mode**: Replace `runc` with `runsc` for syscall-level filtering. Every syscall goes through gVisor's user-space kernel, catching exploit attempts that container namespaces alone would miss.

### 6.5 Sandbox Selection Logic

The Sandbox Manager picks the tier based on this precedence:

```python
def select_sandbox(tool: Tool, agent_policy: AgentPolicy, org_config: OrgConfig) -> SandboxTier:
    # 1. Tool explicitly declares its tier
    if tool.spec.sandbox:
        requested_tier = tool.spec.sandbox      # "none", "wasm", "docker", "microvm"
    # 2. Infer from tool type
    elif tool.spec.type == "wasm":
        requested_tier = "wasm"                 # .wasm binary → always WASM
    elif tool.spec.type == "python" and tool.spec.trusted:
        requested_tier = "none"                 # trusted Python → non-sandboxed
    elif tool.spec.type == "python":
        requested_tier = agent_policy.spec.sandbox.default_tier or "wasm"
    elif tool.spec.type in ("mcp-stdio",):
        requested_tier = "docker"               # needs OS environment
    elif tool.spec.type in ("mcp-http", "rest"):
        if agent_policy.spec.sandbox.get("remote_tools_bypass_floor", True):
            requested_tier = "none"             # remote call, no local code to sandbox
        else:
            requested_tier = agent_policy.spec.sandbox.default_tier or "none"
    else:
        requested_tier = agent_policy.spec.sandbox.default_tier or org_config.default_sandbox_tier
    
    # 3. Apply policy floor: never go below the agent's minimum tier
    policy_minimum = agent_policy.spec.sandbox.minimum_tier or org_config.minimum_sandbox_tier or "none"
    effective_tier = max(requested_tier, policy_minimum)
    
    return effective_tier
```

**Tier ordering** (for `max()` comparison): `none < wasm < docker < microvm`.

**Examples**:

| Tool sandbox | Policy minimum | Policy default | Effective | Why |
|-------------|----------------|----------------|-----------|-----|
| `none` | `none` | `wasm` | **none** | Tool explicitly says none, policy allows it |
| `none` | `wasm` | `wasm` | **wasm** | Tool wants none, but policy floor is wasm |
| (unset, python) | `none` | `wasm` | **wasm** | No explicit tier, defaults to policy default |
| `docker` | `wasm` | `wasm` | **docker** | Tool requests docker, above policy floor |
| `wasm` | `docker` | `docker` | **docker** | Tool wants wasm, but policy floor is docker |
| (unset, mcp-http) | `wasm` | `wasm` | **none** | Remote HTTP call — no local code, no sandbox needed (floor doesn't apply to remote calls) |

**Why remote tools bypass the policy floor**: Tools of type `mcp-http` and `rest` execute no local code — they make an outbound HTTP call to a remote service. Sandboxing local code execution is meaningless when no local code runs. Network-level restrictions for these tools are enforced by the agent's `network.outbound` policy (PRD 03), not by the sandbox tier.

**Policy control**: This behavior is controlled by `AgentPolicy.sandbox.remote_tools_bypass_floor` (PRD 03). When set to `false`, remote tools are also subject to the minimum tier floor. Default is `true` for backward compatibility. (Though sandboxing a remote HTTP call has no practical isolation effect, enforcing the floor universally may be required for compliance-sensitive environments.)

### 6.6 Pool & Warm-Start

To minimize latency:

| Tier | Strategy |
|------|----------|
| **none** | No pooling. Direct function call. Module is already imported at resource-load time. |
| **WASM** | **Module cache**: compiled `.wasm` modules are cached in memory. Instantiation is ~5ms. A pool of pre-instantiated modules can be maintained for frequently-used tools. |
| **Docker** | **Warm container pool**: Pre-created containers in `paused` state. Resume on demand (~50ms vs ~500ms cold start). Pool size configurable per tool or globally. |
| **MicroVM** | **Warm VM pool**: Pre-booted VMs kept idle. Resume from snapshot (~200ms vs ~3s cold boot). |

---

## 7. LLM Routing

All LLM calls are routed through **LiteLLM Proxy**. See PRD 06 for the full architecture, configuration, budget enforcement, and virtual key lifecycle.

At execution time, the engine configures each CrewAI Agent's `LLM` class to point at the LiteLLM Proxy:

```python
from crewai import LLM

agent_llm = LLM(
    model="openai-gpt4o",                    # LiteLLM model alias
    base_url="http://litellm-proxy:4000",    # LiteLLM Proxy endpoint
    api_key=agent_virtual_key,               # per-agent virtual key with budget
)
```

CrewAI doesn't know it's talking to LiteLLM — it sees an OpenAI-compatible API. LiteLLM handles provider dispatch, load balancing, fallbacks, and spend tracking.

**Policy enforcement at the LLM layer:**
- **Model access**: The agent's virtual key restricts which models it can call (PRD 06, section 4.2).
- **Budget**: The virtual key has a `max_budget` derived from the AgentPolicy's `llm.max_cost_per_execution_usd` (PRD 06, section 4.4).
- **Per-task token limits**: `llm.max_tokens_per_task` is enforced by Blackbeard's policy enforcer (not LiteLLM), by tracking token usage per task and stopping the agent if exceeded.
- **Context window**: If `respect_context_window: true` (default), CrewAI monitors token count and summarises earlier messages when approaching the limit.

---

## 8. Tool Dispatch Pipeline

Every tool call goes through this pipeline:

```
Agent requests tool call
    │
    ▼
┌──────────────────────────┐
│  1. Policy Check         │  AgentPolicy: is this tool allowed?
│     (PRD 03)             │  Invocation count < limit? Budget OK?
└────────┬─────────────────┘
         │ DENY → feed denial message back to agent
         │ ALLOW ▼
┌──────────────────────────┐
│  2. Input Validation     │  Parameters match tool schema?
│                          │  Input sanitised?
└────────┬─────────────────┘
         │ INVALID → feed error back to agent
         │ VALID ▼
┌──────────────────────────┐
│  3. Sandbox Selection    │  Pick tier: in-process / WASM / Docker / MicroVM
│     (section 6.5)        │  Resolve sandbox profile
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  4. Sandbox Provisioning │  Get from warm pool or create fresh
│                          │  Apply resource limits, network policy, FS mounts
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  5. Execution            │  Run tool in sandbox
│                          │  Monitor: time, memory, fuel, network calls
└────────┬─────────────────┘
         │ TIMEOUT/OOM → return error to agent
         │ SUCCESS ▼
┌──────────────────────────┐
│  6. Output Capture       │  Read result from sandbox
│                          │  PII redaction (PRD 08)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  7. Audit & Metrics      │  Log: tool, args hash, duration, sandbox tier, status
│                          │  Emit event: tool_call.completed
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  8. Cache                │  If tool.cache: true and result is cacheable,
│                          │  store result keyed by (tool, args_hash)
└────────┬─────────────────┘
         │
         ▼
  Return result to agent conversation
```

---

## 9. State Management

### 9.1 Execution State (Crews)
- Per-execution context: task outputs, agent memories, token metrics.
- Stored in PostgreSQL `executions` table.
- Checkpointed after each task (if checkpointing enabled).

### 9.2 Flow State
- Structured (Pydantic) or unstructured (dict) state per flow instance.
- Persisted via configurable backend (SQLite, PostgreSQL, custom).
- Each flow instance gets a UUID.
- Fork and resume supported.

### 9.3 Memory

| Memory Type | Scope | Backend |
|-------------|-------|---------|
| **Short-term** | Single execution | In-memory |
| **Long-term** | Across executions | Vector DB (LanceDB / Qdrant / Chroma) |
| **Entity** | Named entities mentioned across runs | Vector DB |

Memory is opt-in per agent/crew (`memory: true`).

---

## 10. Human-in-the-Loop

When a task has `human_input: true` or a flow step has `human_feedback`:

1. Execution state transitions to `waiting_for_human`.
2. An event `execution.human_input_required` is emitted.
3. The execution pauses and checkpoints.
4. A human submits feedback via API, UI, or email reply link.
5. Execution resumes with the human's input injected into context.

---

## 11. Streaming

When `stream: true`:

```
GET /api/v1/executions/{id}/stream
Accept: text/event-stream

data: {"type": "task_started", "task": "research-ai", "agent": "researcher"}
data: {"type": "token", "content": "The latest developments"}
data: {"type": "tool_call", "tool": "serper-search", "sandbox": "wasm", "args": {"query": "AI 2026"}}
data: {"type": "tool_result", "tool": "serper-search", "status": "success", "duration_ms": 340}
data: {"type": "policy_warning", "agent": "researcher", "budget_type": "tokens", "used": 45000, "limit": 50000}
data: {"type": "task_completed", "task": "research-ai", "tokens": 4200}
data: {"type": "execution_completed", "total_tokens": 15600}
```

### SSE Event Types

Each SSE event has a `type` field and a typed `data` payload:

| Event Type | Payload Fields | Description |
|------------|---------------|-------------|
| `execution.started` | `execution_id`, `crew_name`, `total_tasks` | Execution has begun |
| `task.started` | `execution_id`, `task_name`, `agent_name` | Task assigned to agent, LLM calls beginning |
| `task.completed` | `execution_id`, `task_name`, `agent_name`, `output_preview`, `tokens`, `duration_ms` | Task finished successfully |
| `task.failed` | `execution_id`, `task_name`, `agent_name`, `error` | Task failed after retries |
| `tool_call.started` | `execution_id`, `task_name`, `tool_name`, `sandbox_tier` | Tool invocation beginning |
| `tool_call.completed` | `execution_id`, `task_name`, `tool_name`, `duration_ms`, `success` | Tool invocation finished |
| `llm_call.completed` | `execution_id`, `task_name`, `agent_name`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd` | LLM call finished |
| `policy.denied` | `execution_id`, `task_name`, `agent_name`, `action`, `reason` | Policy enforcement blocked an action |
| `guardrail.failed` | `execution_id`, `task_name`, `guardrail_name`, `retry_count` | Guardrail validation failed |
| `execution.completed` | `execution_id`, `status`, `output`, `total_tokens`, `total_cost_usd`, `duration_ms` | Execution finished |
| `execution.failed` | `execution_id`, `error`, `failed_task` | Execution failed |
| `execution.cancelled` | `execution_id`, `cancelled_by`, `reason` | Execution cancelled by user or API |

**SSE wire format:**
```
event: task.completed
data: {"execution_id":"exec-abc","task_name":"research-ai","agent_name":"researcher","tokens":4200,"duration_ms":12400}

```

---

## 11.1 Real-time Event Streaming

All execution activity is captured as an append-only log of **ExecutionEvents**, stored in the `execution_events` table (section 15) and streamed to the frontend via SSE.

### ExecutionEvent Model

Each event is an immutable record with a monotonically increasing sequence number per execution:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `execution_id` | UUID | FK to executions |
| `sequence` | INTEGER | Monotonically increasing per execution, used for ordering and replay |
| `event_type` | VARCHAR(64) | Event type (see table below) |
| `timestamp` | TIMESTAMPTZ | When the event occurred |
| `data` | JSONB | Event-specific payload |

### CrewAI Events Captured

The Blackbeard event listener registers on CrewAI's event bus and captures the following events into the `execution_events` table:

| Event Type | CrewAI Source | Data Payload |
|------------|--------------|--------------|
| `crew_started` | `CrewKickoffStartedEvent` | `{crew_name, inputs, total_tasks}` |
| `crew_completed` | `CrewKickoffCompletedEvent` | `{crew_name, output_preview, total_tokens, total_cost_usd, duration_ms}` |
| `task_started` | `TaskStartedEvent` | `{task_name, agent_name, task_description}` |
| `task_completed` | `TaskCompletedEvent` | `{task_name, agent_name, output_preview, tokens, duration_ms}` |
| `tool_started` | `ToolUsageStartedEvent` | `{tool_name, agent_name, sandbox_tier, input_preview}` |
| `tool_finished` | `ToolUsageFinishedEvent` | `{tool_name, agent_name, sandbox_tier, duration_ms, success, output_preview}` |
| `llm_started` | `LLMCallStartedEvent` | `{agent_name, model, prompt_tokens_estimate}` |
| `llm_completed` | `LLMCallCompletedEvent` | `{agent_name, model, prompt_tokens, completion_tokens, cost_usd, duration_ms}` |
| `policy_denied` | Blackbeard policy enforcer | `{agent_name, action, resource, reason}` |
| `error` | Various | `{source, error_type, message, task_name, agent_name}` |

### SSE Endpoint (Live Streaming)

The SSE endpoint streams events to the frontend as they occur:

```
GET /api/v1/executions/{execution_id}/stream
Accept: text/event-stream

event: task_started
data: {"sequence":3,"event_type":"task_started","timestamp":"2026-05-10T12:00:05Z","data":{"task_name":"research-ai","agent_name":"researcher"}}

event: tool_started
data: {"sequence":4,"event_type":"tool_started","timestamp":"2026-05-10T12:00:06Z","data":{"tool_name":"serper-search","agent_name":"researcher","sandbox_tier":"wasm"}}

event: tool_finished
data: {"sequence":5,"event_type":"tool_finished","timestamp":"2026-05-10T12:00:06Z","data":{"tool_name":"serper-search","duration_ms":340,"success":true}}
```

The client can optionally pass `?after_sequence=N` to resume from a specific point (e.g., after a reconnection). The server replays all events with `sequence > N` from the database, then switches to live streaming.

### REST Endpoint (Historical Replay)

For historical event access and debugging:

```
GET /api/v1/executions/{execution_id}/events
    ?event_type=tool_finished           # optional filter
    &after_sequence=0                   # optional: events after this sequence
    &limit=100                          # optional: max events to return

200 OK
{
  "events": [
    {"sequence": 1, "event_type": "crew_started", "timestamp": "...", "data": {...}},
    {"sequence": 2, "event_type": "task_started", "timestamp": "...", "data": {...}},
    ...
  ],
  "total": 42,
  "has_more": false
}
```

### ExecutionTask Live Status

During execution, the `execution_tasks` table is updated in real-time as events occur:

- When `task_started` is emitted: `execution_tasks.status` set to `running`, `started_at` set
- When `task_completed` is emitted: `execution_tasks.status` set to `completed`, `completed_at` set, `output` and `token_usage` populated
- When a task fails: `execution_tasks.status` set to `failed`

The execution detail API returns the current state of all tasks, enabling the frontend to show live progress without polling for individual task status.

---

## 11.2 CrewAI Built-in Feature Delegation

Blackbeard delegates to CrewAI's built-in features rather than reimplementing them. These features are exposed via the resource spec and passed through to CrewAI at execution time:

| Feature | CrewAI Mechanism | Blackbeard Resource Config | Description |
|---------|-----------------|---------------------------|-------------|
| **Memory** | `Crew(memory=True)` | `spec.memory: true` on Crew resource | Enables short-term, long-term, and entity memory across tasks within a crew execution |
| **Planning** | `Agent(planning=True)` | `spec.planning: true` on Agent resource | Agent creates a step-by-step plan before executing tasks |
| **Checkpointing** | CrewAI native checkpointing | Enabled via execution config | Allows pausing and resuming executions from the last completed task |
| **Human-in-the-loop** | `Task(human_input=True)` | `spec.human_input: true` on Task resource | Pauses execution after task completion and waits for human feedback before proceeding |
| **Guardrails** | `Task(guardrail=callback)` | `spec.guardrails` on Task resource (see PRD 08) | Validates task output using CrewAI's built-in guardrail callback mechanism |
| **Training** | `Crew.train(n_iterations, inputs, filename)` | Via API: `POST /crews/{name}/train` | Iterative human feedback loop that produces trained agent data (`.pkl`) for improved outputs |
| **Testing** | `Crew.test(n_iterations, inputs, openai_model_name)` | Via API: `POST /crews/{name}/test` | Benchmarks crew performance with an eval model, returns per-task scores |
| **Replay** | `Crew.replay(task_id)` | Via API: `POST /crews/{name}/replay` | Re-executes a specific task from a prior execution for debugging |

**Principle:** Blackbeard is a management layer over CrewAI, not a reimplementation. When CrewAI provides a feature natively, Blackbeard exposes it through YAML configuration and passes it through. Blackbeard only builds features that CrewAI does not provide: RBAC, sandbox isolation, visual editing, deployment lifecycle, and the execution event log.

---

## 11.3 JIT Tool Loading

The ResourceLoader supports three tool loading strategies (see PRD 04 §10 for full spec):

| Mode | Behavior |
|------|----------|
| **jit** (default) | Agents get `search_tools` + `get_tool` meta-tools only. Tools discovered on demand. |
| **eager** | All agent tools loaded into prompt at build time (legacy). |
| **hybrid** | Core tools in prompt + `search_tools` for the rest. |

**ResourceLoader changes for JIT mode:**

1. `build_agent()` checks `crew.spec.tool_loading` (default: `jit`)
2. In JIT mode: instead of resolving tool refs and building CrewAI tool objects, inject two meta-tools:
   - `SearchToolsTool(api_url, api_key, namespace, agent_policy)` — queries the tool registry API
   - `GetToolTool(api_url, api_key, namespace)` — fetches full tool spec and returns a dynamically constructed CrewAI tool
3. RBAC is enforced at the API level — `search_tools` only returns tools the agent's policy allows
4. Tool schemas are cached in-memory per execution to avoid redundant lookups

**Agent policy integration:** The `search_tools` meta-tool filters results against the agent's `AgentPolicy.spec.tools` configuration:
- `mode: unrestricted` → all tools visible
- `mode: allowlist` → only listed tools visible
- `mode: denylist` → all except listed tools visible

## 11.4 Feature Ownership

The execution engine integrates features from multiple systems. Clear ownership prevents reimplementation:

| Capability | Owner | Blackbeard's Role |
|------------|-------|-------------------|
| Agent/Task/Crew orchestration | **CrewAI** | Pass resource config through to CrewAI objects |
| Process modes (sequential, hierarchical) | **CrewAI** | Configure via `spec.process` |
| Memory (STM, LTM, entity) | **CrewAI** | Configure via `spec.memory: true` |
| Checkpointing | **CrewAI** | Configure via `spec.checkpoint` |
| LLM routing, fallbacks, load balancing | **LiteLLM** | Generate config, manage virtual keys |
| LLM spend tracking | **LiteLLM** | Consume spend data for dashboards |
| LLM budget enforcement | **LiteLLM** | Map AgentPolicy budgets to virtual key `max_budget` |
| Sandbox isolation (WASM, Docker, MicroVM) | **Blackbeard** | Build and maintain -- unique to Blackbeard |
| Policy enforcement (tool allowlists, tier promotion) | **Blackbeard** | Build and maintain -- not provided by CrewAI |
| Execution event log + SSE streaming | **Blackbeard** | Build and maintain -- CrewAI emits events, Blackbeard captures and stores them |
| Resource loading (YAML to CrewAI objects) | **Blackbeard** | Build and maintain -- the bridge between resource model and CrewAI |
| Training & testing (human feedback loop) | **CrewAI** | Expose via API + UI — Blackbeard orchestrates training sessions, CrewAI handles the feedback loop |

---

## 11.5 Crew Training & Testing

CrewAI provides a built-in training system that improves agent performance through iterative human feedback. Blackbeard exposes this as a first-class feature accessible from both the API and the agent detail UI.

### How CrewAI Training Works

1. **Training loop**: `crew.train(n_iterations=N, inputs={...}, filename="trained_agents_data.pkl")` runs the crew N times. After each iteration, the human reviews each agent's output and provides feedback.
2. **Feedback capture**: CrewAI stores per-agent, per-iteration data: initial output, human feedback, and improved output in a session-specific `training_data.pkl`.
3. **Consolidated suggestions**: After training completes, CrewAI consolidates feedback into `trained_agents_data.pkl` — keyed by agent role, containing suggestions, quality metrics, and final summaries.
4. **Runtime use**: On subsequent `crew.kickoff()` calls, if the trained data file exists, agents automatically incorporate the consolidated suggestions into their prompts, producing higher-quality outputs without code changes.

### Crew Testing

`crew.test(n_iterations=N, inputs={...}, openai_model_name="gpt-4o")` runs the crew N times and uses an evaluation model to score outputs. Returns average scores and per-task scores — useful for measuring improvement after training.

### Task Replay

`crew.replay(task_id="uuid")` re-executes a specific task from a previous execution, useful for debugging individual task failures without re-running the entire crew.

### API Endpoints

```
POST /api/v1/crews/{name}/train
{
  "n_iterations": 3,
  "inputs": {"topic": "AI safety"},
  "filename": "research-crew-trained.pkl"    // optional, defaults to "{crew-name}-trained.pkl"
}

→ 202 Accepted
{
  "training_session_id": "train-abc123",
  "status": "running",
  "n_iterations": 3,
  "current_iteration": 0
}
```

Training sessions are interactive — after each iteration, the session pauses for human feedback:

```
GET /api/v1/training-sessions/{session_id}

→ 200 OK
{
  "training_session_id": "train-abc123",
  "status": "waiting_for_feedback",
  "current_iteration": 1,
  "n_iterations": 3,
  "agent_outputs": [
    {
      "agent_role": "Researcher",
      "task_name": "research-topic",
      "output": "1. AI safety involves...",
      "awaiting_feedback": true
    }
  ]
}

POST /api/v1/training-sessions/{session_id}/feedback
{
  "feedback": [
    {
      "agent_role": "Researcher",
      "feedback": "Good facts but too verbose. Limit to one sentence per bullet."
    }
  ]
}

→ 200 OK
{
  "status": "running",
  "current_iteration": 2
}
```

After all iterations complete:

```
GET /api/v1/training-sessions/{session_id}

→ 200 OK
{
  "status": "completed",
  "trained_data_file": "research-crew-trained.pkl",
  "iterations_completed": 3,
  "summary": {
    "Researcher": {"suggestions": "...", "quality_score": 8.5},
    "Writer": {"suggestions": "...", "quality_score": 9.0}
  }
}
```

Testing endpoint:

```
POST /api/v1/crews/{name}/test
{
  "n_iterations": 5,
  "inputs": {"topic": "AI safety"},
  "eval_model": "gpt-4o"                    // model used for scoring
}

→ 202 Accepted
{
  "test_session_id": "test-abc123",
  "status": "running"
}

GET /api/v1/test-sessions/{session_id}

→ 200 OK
{
  "status": "completed",
  "avg_score": 8.2,
  "task_scores": {
    "research-topic": {"avg": 8.5, "scores": [8, 9, 8, 9, 8.5]},
    "write-report": {"avg": 7.9, "scores": [7, 8, 8, 8, 8.5]}
  }
}
```

Replay endpoint:

```
POST /api/v1/crews/{name}/replay
{
  "task_id": "uuid-of-failed-task"
}

→ 202 Accepted
{
  "execution_id": "exec-xyz789",
  "status": "running",
  "replaying_task": "research-topic"
}
```

### Database Schema

```sql
training_sessions
  id              UUID PK
  crew_name       VARCHAR(255) NOT NULL
  crew_namespace  VARCHAR(255) NOT NULL DEFAULT 'default'
  status          VARCHAR(32)          -- running, waiting_for_feedback, completed, failed
  n_iterations    INTEGER NOT NULL
  current_iter    INTEGER NOT NULL DEFAULT 0
  inputs          JSONB
  filename        VARCHAR(512)         -- path to trained_agents_data.pkl
  agent_outputs   JSONB                -- current iteration outputs awaiting feedback
  summary         JSONB                -- final training summary with per-agent scores
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at    TIMESTAMPTZ

test_sessions
  id              UUID PK
  crew_name       VARCHAR(255) NOT NULL
  crew_namespace  VARCHAR(255) NOT NULL DEFAULT 'default'
  status          VARCHAR(32)          -- running, completed, failed
  n_iterations    INTEGER NOT NULL
  eval_model      VARCHAR(255)
  inputs          JSONB
  results         JSONB                -- avg_score, task_scores
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at    TIMESTAMPTZ
```

### UI: Agent Detail Training Panel

When viewing an Agent resource detail page, a **"Train"** tab/section provides:

1. **Start Training**: Select a crew that uses this agent → set iterations → provide sample inputs → start training session.
2. **Feedback Loop**: After each iteration, the UI shows the agent's output for each task and presents a text area for human feedback. Submit feedback to advance to the next iteration.
3. **Training History**: List of past training sessions for this agent's crews, with scores and feedback summaries.
4. **Test**: Run a test session to benchmark agent performance with an eval model. Display score charts (per-iteration, per-task).
5. **Active Training Data**: Show whether a `trained_agents_data.pkl` exists for the agent's crew and what suggestions it contains. Option to reset/delete training data.

The training panel is accessible from:
- **Resource Detail page** (`/resources/agents/{name}`) → Training tab
- **Studio** → Select agent node → Property Panel → "Train" button → navigates to training UI

### Acceptance Criteria

31. `POST /api/v1/crews/{name}/train` creates a training session and runs the first iteration.
32. After each iteration, the session pauses in `waiting_for_feedback` status until human feedback is submitted.
33. After all iterations, the trained data file is persisted and available for subsequent `kickoff` calls.
34. `POST /api/v1/crews/{name}/test` runs the crew N times and returns per-task scores from the eval model.
35. `POST /api/v1/crews/{name}/replay` re-executes a specific task from a prior execution.
36. The Agent Detail page shows a training panel with start, feedback, history, and test capabilities.
37. Training data files are stored in a configurable directory (default: `training_data/`) and associated with the crew resource.

---

## 12. Async Execution Backends

| Backend | When to Use |
|---------|-------------|
| **In-process** | Development, testing, sync execution mode. Uses `concurrent.futures.ThreadPoolExecutor`. |
| **Temporal** | Production. Durable execution — workflows survive crashes, restarts, deployments. Built-in retries, timeouts, visibility. |

The backend is selected via configuration (`EXECUTION_BACKEND=in-process|temporal`). The engine defines a `WorkflowBackend` interface; both backends implement it. Additional backends (e.g., Celery) can be added via the Plugin SDK (PRD 11) but are not shipped by default.

**`WorkflowBackend` protocol**:

```python
class WorkflowBackend(Protocol):
    """Interface for execution backends. MVP uses InProcessBackend; post-MVP adds TemporalBackend."""

    async def start_execution(
        self, execution_id: str, crew_name: str, inputs: dict
    ) -> None:
        """Start a crew/flow execution. Non-blocking — execution runs in background."""
        ...

    async def get_status(self, execution_id: str) -> ExecutionStatus:
        """Get current execution status, progress, and token usage."""
        ...

    async def cancel(self, execution_id: str) -> None:
        """Cancel a running execution. Best-effort — may not stop immediately."""
        ...

    async def resume(self, execution_id: str, feedback: dict) -> None:
        """Resume a paused execution with human feedback."""
        ...
```

The in-process backend implements this with `concurrent.futures.ThreadPoolExecutor`. The Temporal backend wraps Temporal's workflow client.

**Graceful shutdown**: When a worker receives SIGTERM:
- **In-process**: Running executions are checkpointed and marked `paused`. On restart, they can be resumed from the checkpoint.
- **Temporal**: Temporal handles this natively — activities are retried on another worker.

Workers drain in-flight tool calls (up to 30s) before shutting down.

---

## 13. Callbacks

All callback fields in YAML (`callbacks.step`, `callbacks.on_complete`, etc.):

1. Resolved to Python callables at load time.
2. Called with a structured context object.
3. Callback errors are caught, logged, and do not crash the execution (configurable: `callbacks_fail_open: true`).
4. Callbacks run **outside** the agent's sandbox — they are engine-level hooks, not agent-invoked code.

---

## 14. Error Handling

| Error Source | Handling |
|-------------|----------|
| **CrewAI unexpected exception** | Catch, log full traceback, set execution status to `failed` with error message, emit `execution.failed` event. |
| **Tool returns malformed output** | Wrap in error message, feed back to agent as "Tool returned invalid output: {summary}". Agent can retry or choose a different approach. |
| **LLM returns unparseable response** | CrewAI's built-in retry handles this. If retries exhausted, task fails with `llm_parse_error`. |
| **Network timeout (tool or LLM)** | Retry with exponential backoff (configurable: `max_retries`, `retry_backoff`). After exhaustion, feed timeout error to agent. |
| **Out-of-memory (sandbox)** | Sandbox is killed. Agent receives `resource_limit_exceeded` error. Execution continues with remaining tasks if possible. |
| **Database connection lost** | Execution pauses, retries DB connection with backoff. If unrecoverable, execution fails and last checkpoint is preserved. |
| **Callback raises exception** | If `callbacks_fail_open: true` (default), log error and continue. If `false`, task fails. |
| **Sandbox infrastructure failure** (`sandbox_infrastructure`): Sandbox runtime itself failed (Wasmtime crash, Docker daemon unreachable, module cache corruption) | Retry with same tier once. If retry fails, fail execution with `SANDBOX_INFRA_ERROR`. Do NOT fall back to a lower tier (this would violate the policy floor). Log infrastructure failure for operator alerting. |

---

## 15. Database Schema

```sql
executions
  id              UUID PK
  automation_id   UUID FK → resources (kind=Automation) NULLABLE
  resource_kind   VARCHAR(32) NOT NULL   -- 'Crew' or 'Flow' (direct reference for MVP)
  resource_name   VARCHAR(255) NOT NULL  -- name of the crew/flow being executed
  namespace       VARCHAR(255) NOT NULL DEFAULT 'default'
  status          VARCHAR(32)
  inputs          JSONB
  outputs         JSONB
  progress        JSONB
  token_usage     JSONB
  error           TEXT
  checkpoint_id   UUID
  principal_chain JSONB           -- {user, crew, agent} for RBAC audit
  started_at      TIMESTAMPTZ
  completed_at    TIMESTAMPTZ
  created_by      UUID FK → users

execution_tasks
  id              UUID PK
  execution_id    UUID FK → executions
  task_name       VARCHAR(255)
  agent_name      VARCHAR(255)
  status          VARCHAR(32)
  input           JSONB
  output          JSONB
  token_usage     JSONB
  tool_calls      JSONB
  policy_denials  JSONB           -- list of denied actions during this task
  started_at      TIMESTAMPTZ
  completed_at    TIMESTAMPTZ

execution_tool_calls
  id              UUID PK
  execution_id    UUID FK → executions
  task_id         UUID FK → execution_tasks
  tool_name       VARCHAR(255)
  sandbox_tier    VARCHAR(32)     -- none, wasm, docker, microvm
  sandbox_id      VARCHAR(255)    -- sandbox instance identifier
  input_hash      VARCHAR(64)     -- SHA-256 of serialized input
  status          VARCHAR(32)     -- success, error, timeout, policy_denied
  duration_ms     INTEGER
  memory_peak_mb  INTEGER
  network_calls   INTEGER         -- outbound HTTP calls made inside sandbox
  created_at      TIMESTAMPTZ

execution_events
  id              UUID PK DEFAULT gen_random_uuid()
  execution_id    UUID FK → executions NOT NULL
  sequence        INTEGER NOT NULL       -- monotonically increasing per execution
  event_type      VARCHAR(64) NOT NULL   -- e.g. crew_started, task_completed, tool_started
  timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
  data            JSONB                  -- event-specific payload
  
  UNIQUE(execution_id, sequence)

execution_checkpoints
  id              UUID PK
  execution_id    UUID FK → executions
  state           JSONB
  created_at      TIMESTAMPTZ
```

> **Note on `automation_id` vs `resource_kind`/`resource_name`**: For MVP (before Automation resources exist), `automation_id` is NULL and `resource_kind` + `resource_name` identify the crew directly. Post-MVP, `automation_id` references the Automation, and `resource_kind`/`resource_name` are still populated for queryability.

Indexes:
  idx_exec_automation     ON executions(automation_id)
  idx_exec_status         ON executions(status)
  idx_exec_ns_status      ON executions(namespace, status)
  idx_exec_created_by     ON executions(created_by)
  idx_exec_started_at     ON executions(started_at DESC)
  idx_exec_tasks_exec     ON execution_tasks(execution_id)
  idx_exec_tools_exec     ON execution_tool_calls(execution_id)
  idx_exec_tools_task     ON execution_tool_calls(task_id)
  idx_exec_events_exec    ON execution_events(execution_id, sequence)
  idx_exec_events_type    ON execution_events(execution_id, event_type)

---

## 16. Events Emitted

| Event | Payload |
|-------|---------|
| `execution.queued` | `{execution_id, automation_id, inputs}` |
| `execution.started` | `{execution_id, principal_chain}` |
| `task.started` | `{execution_id, task_name, agent_name}` |
| `task.completed` | `{execution_id, task_name, token_usage, duration}` |
| `task.failed` | `{execution_id, task_name, error}` |
| `tool_call.started` | `{execution_id, task_name, tool_name, sandbox_tier}` |
| `tool_call.completed` | `{execution_id, task_name, tool_name, sandbox_tier, duration, status}` |
| `tool_call.sandbox_created` | `{execution_id, tool_name, sandbox_tier, sandbox_id}` |
| `tool_call.sandbox_destroyed` | `{sandbox_id, duration, resource_usage}` |
| `llm_call.completed` | `{execution_id, task_name, agent_name, model, prompt_tokens, completion_tokens, cost_usd}` |
| `policy.denied` | `{execution_id, agent, action, resource, policy, rule}` |
| `guardrail.failed` | `{execution_id, task_name, guardrail_name, retry_count}` |
| `execution.budget_warning` | `{execution_id, agent, budget_type, used, limit}` |
| `execution.human_input_required` | `{execution_id, task_name, prompt}` |
| `execution.human_input_received` | `{execution_id, feedback}` |
| `execution.completed` | `{execution_id, outputs, token_usage, duration}` |
| `execution.failed` | `{execution_id, error}` |
| `execution.cancelled` | `{execution_id, cancelled_by, reason}` |
| `execution.checkpointed` | `{execution_id, checkpoint_id}` |

**Event naming convention:** All events use dotted namespace format. The SSE event type names (section 11 of this PRD) are the canonical names used across all subsystems (internal event bus, execution_events table, webhook payloads). Event producers MUST use these exact names.

---

## 17. Acceptance Criteria

### Core Execution
1. A Crew defined in YAML can be kicked off via API and produces correct outputs.
2. Sequential and Hierarchical process modes work correctly.
3. Flow with `@start`, `@listen`, and `@router` semantics executes steps in correct order.
4. Tool calls are dispatched, results fed back to agent, and iteration continues.
5. `max_iter` limit stops execution and returns best answer.
6. Guardrails run after task completion; on failure, agent retries up to `guardrail_max_retries`.
7. Human-in-the-loop pauses execution and resumes with injected feedback.
8. Streaming endpoint delivers real-time SSE events.
9. Checkpointing works: kill a running execution, resume from checkpoint, completed tasks are skipped.
10. Callbacks fire at correct lifecycle points; callback errors don't crash execution.
11. Token usage and cost estimates are accurate and available in the execution record.

### Sandbox & Isolation
12. **none**: A tool with `sandbox: none` and `trusted: true` executes in-process with zero overhead; all invocations are still audit-logged with tool name, input hash, duration, and calling agent.
13. **none + policy floor**: A tool with `sandbox: none` assigned to an agent whose policy has `minimum_tier: wasm` is promoted to WASM; the tool author's preference is overridden by the policy floor.
14. **WASM**: A tool compiled to `.wasm` executes correctly; it cannot access host memory, filesystem (unless granted via WASI preopens), or network (unless granted via `wasi:http`).
15. **WASM fuel**: A WASM tool exceeding its fuel limit is terminated with a timeout error; the agent receives an error message and can retry or choose a different approach.
16. **Docker**: A tool running in Docker cannot access the host network, host filesystem (outside mounts), or escalate privileges.
17. **Docker gVisor**: With `runtime: runsc`, syscalls are filtered through gVisor; a tool attempting a blocked syscall gets EPERM.
18. **Network policy**: A tool in an `allowlist` sandbox can reach allowed domains but gets connection refused for blocked domains.
19. **Resource limits**: A tool exceeding memory, CPU, or time limits is killed; the agent receives a resource-limit error.
20. **Warm pool**: WASM module cache reduces cold-start from ~50ms to ~5ms. Docker warm pool reduces cold-start from ~500ms to ~50ms.
21. **Sandbox selection**: The engine correctly picks the effective tier based on tool.sandbox > inferred default, then applies `max(requested, policy_minimum)`.

### Event Streaming
22. Every execution produces an append-only log in `execution_events` with correct sequence ordering.
23. SSE endpoint streams events in real-time; a client connecting mid-execution receives all prior events via `?after_sequence=N`.
24. REST endpoint returns historical events with optional filtering by `event_type`.
25. `execution_tasks.status` is updated live as `task_started` and `task_completed` events occur.
26. CrewAI built-in features (memory, planning, checkpointing, human-in-the-loop) are passed through via resource spec config, not reimplemented.

### Policy Enforcement
27. An agent with `tools.mode: allowlist` cannot invoke unlisted tools; denial is logged and fed back to agent.
28. An agent exceeding `llm.max_tokens_per_execution` is stopped with a budget error.
29. An agent exceeding `llm.max_cost_per_execution_usd` is stopped with a cost ceiling error.
30. Every tool call, LLM call, and delegation attempt is audit-logged with sandbox tier and policy evaluation result.
