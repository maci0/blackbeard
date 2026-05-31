import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act, cleanup } from "@testing-library/react";
import React from "react";
import {
  BlackbeardProvider,
  useBlackbeard,
  CrewRunner,
  ExecutionStatus,
  CrewViewer,
  apiFetch,
  BlackbeardApiError,
} from "../src/index";
import type { BlackbeardConfig, Execution, Resource } from "../src/types";

// ---------------------------------------------------------------------------
// Fetch mock helpers
// ---------------------------------------------------------------------------

let fetchSpy: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    statusText: "Error",
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const defaultConfig: BlackbeardConfig = {
  baseUrl: "http://localhost:8000",
  apiKey: "test-key",
};

function makeExecution(overrides: Partial<Execution> = {}): Execution {
  return {
    id: "exec-1",
    crew_name: "my-crew",
    crew_project: "default",
    execution_type: "kickoff",
    status: "completed",
    n_iterations: null,
    training_file: null,
    inputs: {},
    outputs: { result: "done" },
    error: null,
    total_tokens: 1500,
    prompt_tokens: 1000,
    completion_tokens: 500,
    cost_usd: "0.0150",
    initiated_by: "user-1",
    principal_chain: null,
    created_at: "2025-01-01T00:00:00Z",
    started_at: "2025-01-01T00:00:01Z",
    completed_at: "2025-01-01T00:00:10Z",
    ...overrides,
  };
}

function makeResource(kind: string, name: string, spec: Record<string, unknown> = {}): Resource {
  return {
    id: `id-${name}`,
    apiVersion: "blackbeard.ai/v1",
    kind,
    metadata: { name, project: "default" },
    spec,
    version: 1,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  };
}

// ---------------------------------------------------------------------------
// BlackbeardProvider + useBlackbeard
// ---------------------------------------------------------------------------

describe("BlackbeardProvider", () => {
  it("renders children", () => {
    render(
      <BlackbeardProvider {...defaultConfig}>
        <div data-testid="child">hello</div>
      </BlackbeardProvider>,
    );
    expect(screen.getByTestId("child")).toHaveTextContent("hello");
  });

  it("provides config values through useBlackbeard hook", () => {
    function ConfigReader() {
      const config = useBlackbeard();
      return (
        <div>
          <span data-testid="base-url">{config.baseUrl}</span>
          <span data-testid="api-key">{config.apiKey}</span>
        </div>
      );
    }

    render(
      <BlackbeardProvider
        baseUrl="https://api.test.com"
        apiKey="sk-12345"
      >
        <ConfigReader />
      </BlackbeardProvider>,
    );

    expect(screen.getByTestId("base-url")).toHaveTextContent("https://api.test.com");
    expect(screen.getByTestId("api-key")).toHaveTextContent("sk-12345");
  });

  it("provides token through the hook", () => {
    function TokenReader() {
      const config = useBlackbeard();
      return <span data-testid="token">{config.token ?? "none"}</span>;
    }

    render(
      <BlackbeardProvider baseUrl="http://localhost:8000" token="jwt-abc">
        <TokenReader />
      </BlackbeardProvider>,
    );

    expect(screen.getByTestId("token")).toHaveTextContent("jwt-abc");
  });

  it("memoizes the context value for stable references", () => {
    const seen: BlackbeardConfig[] = [];

    function Collector() {
      const config = useBlackbeard();
      seen.push(config);
      return null;
    }

    const { rerender } = render(
      <BlackbeardProvider baseUrl="http://a.com" apiKey="k1">
        <Collector />
      </BlackbeardProvider>,
    );

    rerender(
      <BlackbeardProvider baseUrl="http://a.com" apiKey="k1">
        <Collector />
      </BlackbeardProvider>,
    );

    expect(seen[0]).toBe(seen[1]);
  });
});

describe("useBlackbeard", () => {
  it("throws when used outside a provider", () => {
    function Orphan() {
      useBlackbeard();
      return null;
    }

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(
      "useBlackbeard must be used within a <BlackbeardProvider>",
    );
    consoleSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// ExecutionStatus
// ---------------------------------------------------------------------------

describe("ExecutionStatus", () => {
  it("shows loading state initially", () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders completed execution status", async () => {
    const execution = makeExecution({ status: "completed" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(execution));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
    });
  });

  it("renders token count", async () => {
    const execution = makeExecution({ total_tokens: 1500 });
    fetchSpy.mockResolvedValueOnce(jsonResponse(execution));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTitle("Total tokens")).toHaveTextContent("1.5k tokens");
    });
  });

  it("renders cost when present", async () => {
    const execution = makeExecution({ cost_usd: "0.0150" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(execution));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTitle("Cost")).toHaveTextContent("$0.0150");
    });
  });

  it("renders error message for failed executions", async () => {
    const execution = makeExecution({
      status: "failed",
      error: "LLM provider returned 503",
    });
    fetchSpy.mockResolvedValueOnce(jsonResponse(execution));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("failed")).toBeInTheDocument();
      expect(screen.getByText("LLM provider returned 503")).toBeInTheDocument();
    });
  });

  it("shows error state when fetch fails", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("connection refused"));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/connection refused/)).toBeInTheDocument();
    });
  });

  it("polls for non-terminal statuses and stops on terminal", async () => {
    vi.useFakeTimers();
    const running = makeExecution({ status: "running" });
    const completed = makeExecution({ status: "completed" });

    fetchSpy.mockResolvedValueOnce(jsonResponse(running));
    fetchSpy.mockResolvedValueOnce(jsonResponse(completed));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    // Wait for first fetch
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText("running")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Advance past poll interval (3000ms)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });

    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    // No more polls after terminal
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it("sends X-API-Key header in fetch requests", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider baseUrl="http://localhost:8000" apiKey="my-key">
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("my-key");
  });

  it("prefers token over apiKey for auth", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider baseUrl="http://localhost:8000" apiKey="key" token="tok">
        <ExecutionStatus executionId="exec-1" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok");
    expect(headers["X-API-Key"]).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// CrewRunner
// ---------------------------------------------------------------------------

describe("CrewRunner", () => {
  it("renders crew name in header", () => {
    // Provide a non-resolving fetch to prevent act warnings
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="research-crew" />
      </BlackbeardProvider>,
    );
    expect(screen.getByText("Run: research-crew")).toBeInTheDocument();
  });

  it("renders a Run button", () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );
    expect(screen.getByText("Run")).toBeInTheDocument();
  });

  it("renders instructions text", () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );
    expect(screen.getByText("Provide inputs as JSON and click Run.")).toBeInTheDocument();
  });

  it("renders a textarea for JSON inputs", () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );
    const textarea = screen.getByLabelText("Inputs (JSON)");
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveValue("{}");
  });

  it("shows error for invalid JSON input", async () => {
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );

    const textarea = screen.getByLabelText("Inputs (JSON)");
    fireEvent.change(textarea, { target: { value: "not valid json" } });

    const runButton = screen.getByText("Run");
    fireEvent.click(runButton);

    await waitFor(() => {
      expect(screen.getByText("Invalid JSON in inputs field")).toBeInTheDocument();
    });
  });

  it("calls kickoff API on run and shows execution status", async () => {
    const kickoffResponse = { id: "exec-1" };
    fetchSpy.mockResolvedValueOnce(jsonResponse(kickoffResponse));
    // ExecutionStatus will poll; return a completed execution then block
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );

    const runButton = screen.getByText("Run");
    fireEvent.click(runButton);

    await waitFor(() => {
      expect(screen.getByText("Run another")).toBeInTheDocument();
    });

    // Verify the kickoff API was called
    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toContain("/api/v1/crews/my-crew/kickoff");
    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("POST");
  });

  it("sends custom inputs in kickoff request", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: "exec-1" }));
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );

    const textarea = screen.getByLabelText("Inputs (JSON)");
    fireEvent.change(textarea, { target: { value: '{"topic": "AI safety"}' } });

    const runButton = screen.getByText("Run");
    fireEvent.click(runButton);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const body = JSON.parse(
      (fetchSpy.mock.calls[0]![1] as RequestInit).body as string,
    );
    expect(body.inputs).toEqual({ topic: "AI safety" });
  });

  it("resets to input form when 'Run another' is clicked", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: "exec-1" }));
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" />
      </BlackbeardProvider>,
    );

    fireEvent.click(screen.getByText("Run"));

    await waitFor(() => {
      expect(screen.getByText("Run another")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Run another"));

    expect(screen.getByText("Run")).toBeInTheDocument();
    expect(screen.getByLabelText("Inputs (JSON)")).toBeInTheDocument();
  });

  it("shows API error message when kickoff fails", async () => {
    fetchSpy.mockResolvedValueOnce(errorResponse(403, "Permission denied"));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="forbidden-crew" />
      </BlackbeardProvider>,
    );

    fireEvent.click(screen.getByText("Run"));

    await waitFor(() => {
      expect(screen.getByText("Permission denied")).toBeInTheDocument();
    });
  });

  it("uses custom project param in kickoff URL", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: "exec-1" }));
    fetchSpy.mockResolvedValueOnce(jsonResponse(makeExecution()));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewRunner crewName="my-crew" project="staging" />
      </BlackbeardProvider>,
    );

    fireEvent.click(screen.getByText("Run"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toContain("project=staging");
  });
});

// ---------------------------------------------------------------------------
// CrewViewer
// ---------------------------------------------------------------------------

describe("CrewViewer", () => {
  it("shows loading state initially", () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="my-crew" />
      </BlackbeardProvider>,
    );
    expect(screen.getByText("Loading crew...")).toBeInTheDocument();
  });

  it("renders crew name after loading", async () => {
    const crew = makeResource("Crew", "my-crew", {
      agents: ["ref:agents/researcher"],
      tasks: ["ref:tasks/research-task"],
    });
    const agent = makeResource("Agent", "researcher", { role: "Lead Researcher" });
    const task = makeResource("Task", "research-task", { agent: "ref:agents/researcher" });

    fetchSpy.mockResolvedValueOnce(jsonResponse(crew));
    fetchSpy.mockResolvedValueOnce(jsonResponse(agent));
    fetchSpy.mockResolvedValueOnce(jsonResponse(task));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="my-crew" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("my-crew")).toBeInTheDocument();
    });
  });

  it("renders agent and task nodes", async () => {
    const crew = makeResource("Crew", "my-crew", {
      agents: ["ref:agents/researcher"],
      tasks: ["ref:tasks/analyze"],
    });
    const agent = makeResource("Agent", "researcher", { role: "Data Researcher" });
    const task = makeResource("Task", "analyze", { agent: "ref:agents/researcher" });

    fetchSpy.mockResolvedValueOnce(jsonResponse(crew));
    fetchSpy.mockResolvedValueOnce(jsonResponse(agent));
    fetchSpy.mockResolvedValueOnce(jsonResponse(task));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="my-crew" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Data Researcher")).toBeInTheDocument();
      expect(screen.getByText("analyze")).toBeInTheDocument();
    });

    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.getByText("Task")).toBeInTheDocument();
  });

  it("shows empty state for crews with no agents or tasks", async () => {
    const crew = makeResource("Crew", "empty-crew", {
      agents: [],
      tasks: [],
    });

    fetchSpy.mockResolvedValueOnce(jsonResponse(crew));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="empty-crew" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText('Crew "empty-crew" has no agents or tasks.'),
      ).toBeInTheDocument();
    });
  });

  it("shows error when fetch fails", async () => {
    fetchSpy.mockResolvedValueOnce(errorResponse(404, "Crew not found"));

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="missing-crew" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Crew not found")).toBeInTheDocument();
    });
  });

  it("fetches with correct project param", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(makeResource("Crew", "my-crew", { agents: [], tasks: [] })),
    );

    render(
      <BlackbeardProvider {...defaultConfig}>
        <CrewViewer crewName="my-crew" project="production" />
      </BlackbeardProvider>,
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });

    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toContain("project=production");
  });
});

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------

describe("apiFetch", () => {
  it("makes GET request to the correct URL", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ data: "test" }));

    const result = await apiFetch<{ data: string }>(
      defaultConfig,
      "/api/v1/health",
    );

    expect(result.data).toBe("test");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toBe("http://localhost:8000/api/v1/health");
  });

  it("sends POST with JSON body", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: "created" }));

    await apiFetch(defaultConfig, "/api/v1/agents", {
      method: "POST",
      body: { kind: "Agent", metadata: { name: "test" } },
    });

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.headers).toHaveProperty("Content-Type", "application/json");
    const body = JSON.parse(init.body as string);
    expect(body.kind).toBe("Agent");
  });

  it("sets X-API-Key header when apiKey is configured", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));

    await apiFetch({ baseUrl: "http://localhost:8000", apiKey: "key-123" }, "/test");

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-API-Key"]).toBe("key-123");
  });

  it("sets Bearer token when token is configured", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));

    await apiFetch({ baseUrl: "http://localhost:8000", token: "jwt-xyz" }, "/test");

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer jwt-xyz");
  });

  it("prefers token over apiKey", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));

    await apiFetch(
      { baseUrl: "http://localhost:8000", apiKey: "key", token: "tok" },
      "/test",
    );

    const init = fetchSpy.mock.calls[0]![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok");
    expect(headers["X-API-Key"]).toBeUndefined();
  });

  it("throws BlackbeardApiError on non-OK response", async () => {
    fetchSpy.mockResolvedValueOnce(errorResponse(422, "Validation failed"));

    try {
      await apiFetch(defaultConfig, "/api/v1/agents");
      expect.fail("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(BlackbeardApiError);
      const apiErr = err as BlackbeardApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.detail).toBe("Validation failed");
    }
  });

  it("throws BlackbeardApiError on network failure", async () => {
    fetchSpy.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    try {
      await apiFetch(defaultConfig, "/api/v1/health");
      expect.fail("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(BlackbeardApiError);
      const apiErr = err as BlackbeardApiError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.isNetworkError).toBe(true);
    }
  });

  it("returns undefined for 204 responses", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }));

    const result = await apiFetch(defaultConfig, "/api/v1/agents/test", {
      method: "DELETE",
    });

    expect(result).toBeUndefined();
  });

  it("strips trailing slashes from baseUrl", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));

    await apiFetch(
      { baseUrl: "http://localhost:8000///", apiKey: "k" },
      "/api/v1/health",
    );

    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toBe("http://localhost:8000/api/v1/health");
  });

  it("defaults to http://localhost:8000 when no baseUrl given", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}));

    await apiFetch({}, "/api/v1/health");

    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toBe("http://localhost:8000/api/v1/health");
  });
});

// ---------------------------------------------------------------------------
// BlackbeardApiError (React SDK copy)
// ---------------------------------------------------------------------------

describe("BlackbeardApiError", () => {
  it("has correct name and message", () => {
    const err = new BlackbeardApiError(500, "Internal Server Error");
    expect(err.name).toBe("BlackbeardApiError");
    expect(err.message).toBe("HTTP 500: Internal Server Error");
    expect(err.status).toBe(500);
    expect(err.detail).toBe("Internal Server Error");
  });

  it("classifies error types", () => {
    expect(new BlackbeardApiError(400, "bad").isClientError).toBe(true);
    expect(new BlackbeardApiError(500, "err").isServerError).toBe(true);
    expect(new BlackbeardApiError(401, "no").isUnauthorized).toBe(true);
    expect(new BlackbeardApiError(403, "no").isForbidden).toBe(true);
    expect(new BlackbeardApiError(404, "gone").isNotFound).toBe(true);
    expect(new BlackbeardApiError(409, "dup").isConflict).toBe(true);
    expect(new BlackbeardApiError(429, "slow").isRateLimited).toBe(true);
  });

  it("identifies network and timeout errors", () => {
    const network = new BlackbeardApiError(0, "network request failed");
    expect(network.isNetworkError).toBe(true);
    expect(network.isTimeout).toBe(false);

    const timeout = new BlackbeardApiError(0, "request timed out after 30000ms");
    expect(timeout.isTimeout).toBe(true);
    expect(timeout.isNetworkError).toBe(true);
  });

  it("stores response body", () => {
    const body = { detail: "bad", errors: ["field required"] };
    const err = new BlackbeardApiError(422, "bad", body);
    expect(err.body).toEqual(body);
  });
});
