# blackbeard-sdk (TypeScript)

TypeScript SDK for the Blackbeard Agent Management Platform. Zero runtime
dependencies, works in Node 18+ and modern browsers (uses global `fetch`).

## Install

```bash
bun add blackbeard-sdk
# or: npm install blackbeard-sdk
```

## Quickstart

```ts
import { BlackbeardClient } from "blackbeard-sdk";

const client = new BlackbeardClient({
  baseUrl: "http://localhost:8000",
  apiKey: "your-key", // or token: "jwt" for Bearer auth
});

// Kick off a crew and wait for the result
const execution = await client.kickoff("my-crew", { topic: "AI safety" });
const result = await client.wait(execution.id);
console.log(result.outputs);
```

All config fields are optional. When omitted, the client falls back to
`BLACKBEARD_BASE_URL` (default `http://localhost:8000`), `BLACKBEARD_API_KEY`,
and `BLACKBEARD_TOKEN` environment variables (Node only). Default request
timeout is 30s, configurable via `timeout` (milliseconds).

## Resources

All 14 resource kinds are supported: Agent, Task, Crew, Tool, LLMConnection,
AgentPolicy, Guardrail, Flow, KnowledgeSource, Role, RoleBinding, Automation,
Project, ServiceAccount.

```ts
const { items } = await client.list("Agent", { label_selector: "env=prod" });
const agent = await client.get("Agent", "researcher");
await client.create({
  apiVersion: "blackbeard/v1",
  kind: "Agent",
  metadata: { name: "researcher", project: "default" },
  spec: { role: "Research Analyst", goal: "Find data", backstory: "..." },
});
await client.update("Agent", "researcher", { spec: { verbose: false }, version: 1 });
await client.delete("Agent", "researcher");
await client.apply([agentResource, taskResource, crewResource]); // bulk upsert
```

Version history: `listVersions`, `getVersion`, `rollback`.
Bulk export: `exportYaml()` (single request, multi-doc YAML string) or
`exportAll()` (parallel JSON fetch, capped at 1000 resources per kind).

## Executions

```ts
const exec = await client.kickoff("my-crew", { topic: "AI" });
await client.train("my-crew", { inputs: { topic: "AI" }, n_iterations: 3 });
await client.test("my-crew", { inputs: { topic: "AI" } });
await client.runFlow("my-flow", { topic: "AI" });

await client.getExecution(exec.id);
await client.listExecutions({ crew_name: "my-crew", status: "completed" });
await client.getExecutionEvents(exec.id, { after: -1 });
await client.getExecutionSpend(exec.id);
await client.cancel(exec.id);
await client.retry(exec.id);
await client.respond(exec.id, "Approved"); // human-in-the-loop
const final = await client.wait(exec.id, 2000, 300_000); // poll until terminal
```

## Auth

```ts
await client.login("user@example.com", "password"); // stores JWT on the client
await client.register("new@example.com", "password", "Display Name");
await client.refresh(refreshToken);
await client.whoami();
const { api_key } = await client.generateApiKey(); // requires JWT auth
await client.revokeApiKey();
```

## Error handling

Every failure (HTTP error, network failure, timeout) throws
`BlackbeardApiError`:

```ts
import { BlackbeardApiError } from "blackbeard-sdk";

try {
  await client.get("Agent", "missing");
} catch (err) {
  if (err instanceof BlackbeardApiError) {
    if (err.isNotFound) console.log("resource missing");
    else if (err.isRateLimited) console.log(`retry after ${err.retryAfter}s`);
    else if (err.isNetworkError) console.log("transport failure:", err.detail);
    else console.log(err.status, err.detail, err.requestId);
  }
}
```

`status` is `0` for network/timeout failures. `requestId` carries the server's
`X-Request-Id` header for support correlation.

## Testing

The client uses global `fetch`, so stub it with your test framework
(e.g. `vi.stubGlobal("fetch", mock)` in vitest) — no HTTP server needed.
