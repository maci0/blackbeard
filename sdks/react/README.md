# @blackbeard/react

Embeddable React components for the Blackbeard Agent Management Platform.
Zero runtime dependencies beyond React 18+; components ship with inline
styles, no CSS import needed.

## Install

```bash
bun add @blackbeard/react
# or: npm install @blackbeard/react
```

## Quickstart

Wrap your subtree in `BlackbeardProvider`, then drop in components:

```tsx
import {
  BlackbeardProvider,
  CrewViewer,
  CrewRunner,
  ExecutionStatus,
} from "@blackbeard/react";

function App() {
  return (
    <BlackbeardProvider baseUrl="http://localhost:8000" apiKey="your-key">
      <CrewViewer crewName="research-crew" />
      <CrewRunner crewName="research-crew" onComplete={(exec) => console.log(exec.outputs)} />
      <ExecutionStatus executionId="a1b2c3..." />
    </BlackbeardProvider>
  );
}
```

Provider props: `baseUrl` (default `http://localhost:8000`), `apiKey` or
`token` (JWT Bearer, wins over apiKey), `timeout` (ms, default 30000).

## Components

- **`CrewViewer`** — read-only node graph of a crew's agents and tasks.
  Props: `crewName`, `project` (default `"default"`).
- **`CrewRunner`** — JSON input form that kicks off a crew and shows live
  status. Props: `crewName`, `project`, `onComplete(execution)`.

Both components still accept the deprecated `namespace` prop as a fallback
for `project`; it logs a console warning and will be removed.
- **`ExecutionStatus`** — status badge, token count, duration, and cost for
  an execution; polls every 3s until terminal. Props: `executionId`.

## Hooks and utilities

- **`useBlackbeard()`** — returns the provider's `BlackbeardConfig`; throws
  outside a provider.
- **`apiFetch<T>(config, path, options?)`** — typed fetch wrapper used by all
  components; throws `BlackbeardApiError` on failure. Use it for custom calls:

```tsx
import { apiFetch, useBlackbeard, type Execution } from "@blackbeard/react";

function useExecutions() {
  const config = useBlackbeard();
  return () => apiFetch<{ items: Execution[] }>(config, "/api/v1/executions");
}
```

## Error handling

`apiFetch` throws `BlackbeardApiError` with `status`, `detail`, `requestId`,
`retryAfter`, and predicates like `isNotFound` / `isRateLimited` /
`isNetworkError` (`status === 0`). Components catch their own fetch errors
and render them inline.

For the full non-React client, see the `blackbeard-sdk` TypeScript package.
