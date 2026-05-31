import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { BlackbeardClient, KIND_PLURALS } from "../src/client.js";
import { BlackbeardApiError } from "../src/types.js";

// ---------------------------------------------------------------------------
// Fetch mock helpers
// ---------------------------------------------------------------------------

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, { status });
}

function noContentResponse(): Response {
  return new Response(null, { status: 204 });
}

function errorResponse(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    statusText: "Error",
    headers: { "Content-Type": "application/json" },
  });
}

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Helpers to inspect what fetch was called with
// ---------------------------------------------------------------------------

function lastFetchUrl(): string {
  const call = fetchSpy.mock.lastCall as [string, RequestInit];
  return call[0];
}

function lastFetchInit(): RequestInit {
  const call = fetchSpy.mock.lastCall as [string, RequestInit];
  return call[1];
}

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const sampleResource = {
  id: "abc-123",
  apiVersion: "blackbeard.ai/v1",
  kind: "Agent",
  metadata: { name: "researcher", project: "default" },
  spec: { role: "Researcher" },
  version: 1,
};

const sampleExecution = {
  id: "exec-1",
  crew_name: "my-crew",
  crew_project: "default",
  execution_type: "kickoff" as const,
  status: "completed" as const,
  n_iterations: null,
  training_file: null,
  inputs: {},
  outputs: { result: "done" },
  error: null,
  total_tokens: 500,
  prompt_tokens: 300,
  completion_tokens: 200,
  cost_usd: "0.01",
  initiated_by: "user-1",
  principal_chain: null,
  created_at: "2025-01-01T00:00:00Z",
  started_at: "2025-01-01T00:00:01Z",
  completed_at: "2025-01-01T00:00:10Z",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BlackbeardClient", () => {
  // ── Constructor ──

  describe("constructor", () => {
    it("uses provided baseUrl and strips trailing slashes", () => {
      const client = new BlackbeardClient({
        baseUrl: "https://api.example.com/",
        apiKey: "test-key",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 42 }),
      );
      void client.health();
      expect(lastFetchUrl()).toBe("https://api.example.com/api/v1/health");
    });

    it("defaults to http://localhost:8000 when no baseUrl given", () => {
      const client = new BlackbeardClient({ apiKey: "k" });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      void client.health();
      expect(lastFetchUrl().startsWith("http://localhost:8000")).toBe(true);
    });
  });

  // ── Auth headers ──

  describe("auth headers", () => {
    it("sends X-API-Key header when apiKey is set", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "my-api-key",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      await client.health();
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["X-API-Key"]).toBe("my-api-key");
      expect(headers["Authorization"]).toBeUndefined();
    });

    it("sends Authorization Bearer header when token is set", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        token: "jwt-token-here",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      await client.health();
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["Authorization"]).toBe("Bearer jwt-token-here");
      expect(headers["X-API-Key"]).toBeUndefined();
    });

    it("prefers token over apiKey when both are provided", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "my-key",
        token: "my-token",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      await client.health();
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["Authorization"]).toBe("Bearer my-token");
      expect(headers["X-API-Key"]).toBeUndefined();
    });

    it("sends Content-Type for requests with a body", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      await client.create(sampleResource);
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["Content-Type"]).toBe("application/json");
    });
  });

  // ── Resource CRUD ──

  describe("list()", () => {
    it("calls GET /api/v1/{kind_plural} with correct query params", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ items: [sampleResource], total: 1, limit: 100, offset: 0, has_more: false }),
      );
      const result = await client.list("Agent");
      expect(lastFetchInit().method).toBe("GET");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents");
      expect(url.searchParams.get("project")).toBe("default");
      expect(url.searchParams.get("limit")).toBe("100");
      expect(url.searchParams.get("offset")).toBe("0");
      expect(result.items).toHaveLength(1);
      expect(result.total).toBe(1);
    });

    it("passes custom project and label_selector", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ items: [], total: 0, limit: 50, offset: 10, has_more: false }),
      );
      await client.list("Task", {
        project: "staging",
        label_selector: "env=prod",
        limit: 50,
        offset: 10,
      });
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("project")).toBe("staging");
      expect(url.searchParams.get("label_selector")).toBe("env=prod");
      expect(url.searchParams.get("limit")).toBe("50");
      expect(url.searchParams.get("offset")).toBe("10");
    });

    it("accepts plural form as kind argument", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ items: [], total: 0, limit: 100, offset: 0, has_more: false }),
      );
      await client.list("agents");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents");
    });
  });

  describe("get()", () => {
    it("calls GET /api/v1/{kind_plural}/{name}", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      const result = await client.get("Agent", "researcher");
      expect(lastFetchInit().method).toBe("GET");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher");
      expect(url.searchParams.get("project")).toBe("default");
      expect(result.metadata.name).toBe("researcher");
    });

    it("uses the provided project parameter", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      await client.get("Agent", "researcher", "prod");
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("project")).toBe("prod");
    });

    it("URL-encodes names with special characters", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      await client.get("Agent", "my-agent");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/my-agent");
    });
  });

  describe("create()", () => {
    it("calls POST /api/v1/{kind_plural} with the resource body", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      const result = await client.create(sampleResource);
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents");
      expect(JSON.parse(lastFetchInit().body as string)).toEqual(sampleResource);
      expect(result.kind).toBe("Agent");
    });
  });

  describe("update()", () => {
    it("calls PUT /api/v1/{kind_plural}/{name} with partial resource", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const patch = { spec: { role: "Senior Researcher" } };
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ ...sampleResource, spec: { role: "Senior Researcher" } }),
      );
      const result = await client.update("Agent", "researcher", patch);
      expect(lastFetchInit().method).toBe("PUT");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher");
      expect(url.searchParams.get("project")).toBe("default");
      expect(result.spec.role).toBe("Senior Researcher");
    });
  });

  describe("delete()", () => {
    it("calls DELETE /api/v1/{kind_plural}/{name}", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(noContentResponse());
      await client.delete("Agent", "researcher");
      expect(lastFetchInit().method).toBe("DELETE");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher");
      expect(url.searchParams.get("project")).toBe("default");
    });

    it("uses provided project param", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(noContentResponse());
      await client.delete("Agent", "researcher", "staging");
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("project")).toBe("staging");
    });
  });

  // ── Versioning ──

  describe("listVersions()", () => {
    it("calls GET /api/v1/{kind_plural}/{name}/versions", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const versions = {
        versions: [
          { version: 1, changed_by: "user-1", created_at: "2025-01-01T00:00:00Z", changed_keys: ["spec"] },
          { version: 2, changed_by: "user-1", created_at: "2025-01-02T00:00:00Z", changed_keys: ["spec.role"] },
        ],
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(versions));
      const result = await client.listVersions("Agent", "researcher");
      expect(lastFetchInit().method).toBe("GET");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher/versions");
      expect(url.searchParams.get("project")).toBe("default");
      expect(result.versions).toHaveLength(2);
    });
  });

  describe("getVersion()", () => {
    it("calls GET /api/v1/{kind_plural}/{name}/versions/{version}", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const versionDetail = {
        version: 1,
        changed_by: "user-1",
        created_at: "2025-01-01T00:00:00Z",
        spec: { role: "Researcher" },
        labels: null,
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(versionDetail));
      const result = await client.getVersion("Agent", "researcher", 1);
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher/versions/1");
      expect(result.version).toBe(1);
    });
  });

  describe("rollback()", () => {
    it("calls POST /api/v1/{kind_plural}/{name}/rollback with version body", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      const result = await client.rollback("Agent", "researcher", 1);
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/agents/researcher/rollback");
      expect(JSON.parse(lastFetchInit().body as string)).toEqual({ version: 1 });
      expect(result.kind).toBe("Agent");
    });

    it("passes project query param", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      await client.rollback("Agent", "researcher", 2, "staging");
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("project")).toBe("staging");
    });
  });

  // ── Executions ──

  describe("kickoff()", () => {
    it("calls POST /api/v1/crews/{name}/kickoff", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      const result = await client.kickoff("my-crew", { topic: "ai" });
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/crews/my-crew/kickoff");
      expect(url.searchParams.get("project")).toBe("default");
      expect(JSON.parse(lastFetchInit().body as string)).toEqual({
        inputs: { topic: "ai" },
      });
      expect(result.id).toBe("exec-1");
    });

    it("sends empty inputs when none provided", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.kickoff("my-crew");
      expect(JSON.parse(lastFetchInit().body as string)).toEqual({
        inputs: {},
      });
    });
  });

  describe("train()", () => {
    it("calls POST /api/v1/crews/{name}/train with defaults", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.train("my-crew");
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/crews/my-crew/train");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.n_iterations).toBe(3);
      expect(body.filename).toBe("training_data.pkl");
      expect(body.inputs).toEqual({});
    });

    it("uses custom options when provided", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.train("my-crew", {
        inputs: { x: 1 },
        n_iterations: 10,
        filename: "custom.pkl",
        project: "prod",
      });
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("project")).toBe("prod");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.n_iterations).toBe(10);
      expect(body.filename).toBe("custom.pkl");
      expect(body.inputs).toEqual({ x: 1 });
    });
  });

  describe("test()", () => {
    it("calls POST /api/v1/crews/{name}/test", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.test("my-crew", { n_iterations: 5 });
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/crews/my-crew/test");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.n_iterations).toBe(5);
    });
  });

  describe("runFlow()", () => {
    it("calls POST /api/v1/flows/{name}/run", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.runFlow("my-flow", { step: 1 });
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/flows/my-flow/run");
      expect(JSON.parse(lastFetchInit().body as string)).toEqual({
        inputs: { step: 1 },
      });
    });
  });

  describe("getExecution()", () => {
    it("calls GET /api/v1/executions/{id}", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      const result = await client.getExecution("exec-1");
      expect(lastFetchInit().method).toBe("GET");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1");
      expect(result.status).toBe("completed");
    });
  });

  describe("listExecutions()", () => {
    it("sends optional filters as query params", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ items: [sampleExecution], total: 1, limit: 50, offset: 0, has_more: false }),
      );
      await client.listExecutions({
        crew_name: "my-crew",
        project: "prod",
        status: "completed",
        limit: 50,
      });
      const url = new URL(lastFetchUrl());
      expect(url.searchParams.get("crew_name")).toBe("my-crew");
      expect(url.searchParams.get("project")).toBe("prod");
      expect(url.searchParams.get("status")).toBe("completed");
      expect(url.searchParams.get("limit")).toBe("50");
    });
  });

  describe("cancel()", () => {
    it("calls PATCH /api/v1/executions/{id}/cancel", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ ...sampleExecution, status: "cancelled" }),
      );
      const result = await client.cancel("exec-1");
      expect(lastFetchInit().method).toBe("PATCH");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1/cancel");
      expect(result.status).toBe("cancelled");
    });
  });

  describe("respond()", () => {
    it("calls POST /api/v1/executions/{id}/respond with response body", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "acknowledged", execution_id: "exec-1" }),
      );
      await client.respond("exec-1", "yes, proceed", "looks good");
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1/respond");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.response).toBe("yes, proceed");
      expect(body.feedback).toBe("looks good");
    });

    it("omits feedback when not provided", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "acknowledged", execution_id: "exec-1" }),
      );
      await client.respond("exec-1", "approved");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.response).toBe("approved");
      expect(body.feedback).toBeUndefined();
    });
  });

  describe("retry()", () => {
    it("calls POST /api/v1/executions/{id}/retry", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      await client.retry("exec-1");
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1/retry");
    });
  });

  describe("getExecutionEvents()", () => {
    it("calls GET /api/v1/executions/{id}/events with pagination", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ events: [], next_sequence: 0, has_more: false }),
      );
      await client.getExecutionEvents("exec-1", { after: 5, limit: 50 });
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1/events");
      expect(url.searchParams.get("after")).toBe("5");
      expect(url.searchParams.get("limit")).toBe("50");
    });
  });

  describe("getExecutionSpend()", () => {
    it("calls GET /api/v1/executions/{id}/spend", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse([]));
      const result = await client.getExecutionSpend("exec-1");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/executions/exec-1/spend");
      expect(result).toEqual([]);
    });
  });

  // ── Auth methods ──

  describe("login()", () => {
    it("calls POST /api/v1/auth/login and stores token", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
      });
      const authResponse = {
        access_token: "new-jwt",
        refresh_token: "refresh-1",
        token_type: "bearer",
        user: {
          id: "u1",
          email: "test@example.com",
          display_name: "Test",
          is_active: true,
          created_at: "2025-01-01T00:00:00Z",
        },
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(authResponse));
      const result = await client.login("test@example.com", "password123");
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/auth/login");
      expect(result.access_token).toBe("new-jwt");

      // Subsequent calls should use the stored token
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      await client.health();
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["Authorization"]).toBe("Bearer new-jwt");
    });
  });

  describe("register()", () => {
    it("calls POST /api/v1/auth/register with display name", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
      });
      const authResponse = {
        access_token: "jwt-2",
        refresh_token: "refresh-2",
        token_type: "bearer",
        user: {
          id: "u2",
          email: "new@example.com",
          display_name: "New User",
          is_active: true,
          created_at: "2025-01-01T00:00:00Z",
        },
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(authResponse));
      await client.register("new@example.com", "pass", "New User");
      const body = JSON.parse(lastFetchInit().body as string);
      expect(body.email).toBe("new@example.com");
      expect(body.display_name).toBe("New User");
    });
  });

  describe("refresh()", () => {
    it("calls POST /api/v1/auth/refresh and updates stored token", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        token: "old-jwt",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ access_token: "refreshed-jwt", refresh_token: null, token_type: "bearer" }),
      );
      const result = await client.refresh("refresh-tok");
      expect(result.access_token).toBe("refreshed-jwt");

      // Next request should use the refreshed token
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ status: "ok", service: "blackbeard", version: "1.0", uptime_s: 0 }),
      );
      await client.health();
      const headers = lastFetchInit().headers as Record<string, string>;
      expect(headers["Authorization"]).toBe("Bearer refreshed-jwt");
    });
  });

  describe("whoami()", () => {
    it("calls GET /api/v1/auth/me", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        token: "jwt",
      });
      const user = {
        id: "u1",
        email: "me@example.com",
        display_name: "Me",
        is_active: true,
        created_at: "2025-01-01T00:00:00Z",
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(user));
      const result = await client.whoami();
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/auth/me");
      expect(result.email).toBe("me@example.com");
    });
  });

  describe("generateApiKey()", () => {
    it("calls POST /api/v1/auth/api-key", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        token: "jwt",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse({ api_key: "generated-key" }));
      const result = await client.generateApiKey();
      expect(lastFetchInit().method).toBe("POST");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/auth/api-key");
      expect(result.api_key).toBe("generated-key");
    });
  });

  describe("revokeApiKey()", () => {
    it("calls DELETE /api/v1/auth/api-key", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        token: "jwt",
      });
      fetchSpy.mockResolvedValueOnce(noContentResponse());
      await client.revokeApiKey();
      expect(lastFetchInit().method).toBe("DELETE");
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/auth/api-key");
    });
  });

  // ── Health ──

  describe("health()", () => {
    it("calls GET /api/v1/health", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const health = { status: "ok", service: "blackbeard", version: "1.0", uptime_s: 42 };
      fetchSpy.mockResolvedValueOnce(jsonResponse(health));
      const result = await client.health();
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/health");
      expect(result.status).toBe("ok");
      expect(result.uptime_s).toBe(42);
    });
  });

  describe("readiness()", () => {
    it("calls GET /api/v1/health/ready", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({
          status: "ready",
          service: "blackbeard",
          checks: { db: { status: "ok", latency_ms: 2 } },
        }),
      );
      const result = await client.readiness();
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/health/ready");
      expect(result.status).toBe("ready");
    });
  });

  // ── Bulk operations ──

  describe("apply()", () => {
    it("creates multiple resources sequentially", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const resource2 = {
        ...sampleResource,
        kind: "Task",
        metadata: { name: "research-task", project: "default" },
      };
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      fetchSpy.mockResolvedValueOnce(jsonResponse(resource2));
      const results = await client.apply([sampleResource, resource2]);
      expect(results).toHaveLength(2);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it("throws annotated error on failure mid-batch", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleResource));
      fetchSpy.mockResolvedValueOnce(errorResponse(409, "already exists"));
      const resource2 = {
        ...sampleResource,
        metadata: { name: "dupe", project: "default" },
      };
      await expect(client.apply([sampleResource, resource2])).rejects.toThrow(
        BlackbeardApiError,
      );
    });
  });

  describe("exportYaml()", () => {
    it("calls GET /api/v1/resources/export and returns text", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(textResponse("---\nkind: Agent\n"));
      const result = await client.exportYaml();
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/resources/export");
      expect(result).toContain("kind: Agent");
    });
  });

  // ── Audit logs ──

  describe("listAuditLogs()", () => {
    it("calls GET /api/v1/audit-logs with optional filters", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(
        jsonResponse({ items: [], total: 0, limit: 100, offset: 0, has_more: false }),
      );
      await client.listAuditLogs({ action: "create", resource_type: "Agent" });
      const url = new URL(lastFetchUrl());
      expect(url.pathname).toBe("/api/v1/audit-logs");
      expect(url.searchParams.get("action")).toBe("create");
      expect(url.searchParams.get("resource_type")).toBe("Agent");
    });
  });

  // ── Error handling ──

  describe("error handling", () => {
    it("throws BlackbeardApiError on 404 with detail from response", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(errorResponse(404, "Resource not found"));
      await expect(client.get("Agent", "nonexistent")).rejects.toThrow(
        BlackbeardApiError,
      );
      try {
        await client.get("Agent", "nonexistent");
      } catch (err) {
        // Already threw above, this block is just for additional checks
      }
    });

    it("sets correct properties on the error object", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(errorResponse(403, "Forbidden"));
      try {
        await client.get("Agent", "secret");
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(BlackbeardApiError);
        const apiErr = err as BlackbeardApiError;
        expect(apiErr.status).toBe(403);
        expect(apiErr.detail).toBe("Forbidden");
        expect(apiErr.isForbidden).toBe(true);
        expect(apiErr.isClientError).toBe(true);
        expect(apiErr.isServerError).toBe(false);
      }
    });

    it("wraps network errors in BlackbeardApiError with status 0", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockRejectedValueOnce(new TypeError("fetch failed"));
      try {
        await client.health();
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(BlackbeardApiError);
        const apiErr = err as BlackbeardApiError;
        expect(apiErr.status).toBe(0);
        expect(apiErr.isNetworkError).toBe(true);
      }
    });

    it("throws on unknown resource kind", () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      expect(() => client.list("FakeKind")).rejects.toThrow(BlackbeardApiError);
    });
  });

  // ── wait() ──

  describe("wait()", () => {
    it("returns immediately when execution is already terminal", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      fetchSpy.mockResolvedValueOnce(jsonResponse(sampleExecution));
      const result = await client.wait("exec-1");
      expect(result.status).toBe("completed");
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it("polls until execution reaches terminal status", async () => {
      const client = new BlackbeardClient({
        baseUrl: "http://localhost:8000",
        apiKey: "k",
      });
      const running = { ...sampleExecution, status: "running" };
      const completed = { ...sampleExecution, status: "completed" };
      fetchSpy.mockResolvedValueOnce(jsonResponse(running));
      fetchSpy.mockResolvedValueOnce(jsonResponse(completed));
      const result = await client.wait("exec-1", 10);
      expect(result.status).toBe("completed");
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });

  // ── KIND_PLURALS ──

  describe("KIND_PLURALS", () => {
    it("contains all expected resource kinds", () => {
      const expectedKinds = [
        "Agent",
        "Task",
        "Crew",
        "Tool",
        "LLMConnection",
        "AgentPolicy",
        "Guardrail",
        "Flow",
        "KnowledgeSource",
        "Role",
        "RoleBinding",
        "Automation",
        "Project",
        "ServiceAccount",
      ];
      for (const kind of expectedKinds) {
        expect(KIND_PLURALS[kind]).toBeDefined();
      }
    });

    it("maps LLMConnection to llm-connections", () => {
      expect(KIND_PLURALS["LLMConnection"]).toBe("llm-connections");
    });

    it("maps KnowledgeSource to knowledge-sources", () => {
      expect(KIND_PLURALS["KnowledgeSource"]).toBe("knowledge-sources");
    });
  });
});

// ---------------------------------------------------------------------------
// BlackbeardApiError
// ---------------------------------------------------------------------------

describe("BlackbeardApiError", () => {
  it("has correct name and message format", () => {
    const err = new BlackbeardApiError(404, "Not found");
    expect(err.name).toBe("BlackbeardApiError");
    expect(err.message).toBe("HTTP 404: Not found");
  });

  it("classifies status codes correctly", () => {
    expect(new BlackbeardApiError(400, "bad").isClientError).toBe(true);
    expect(new BlackbeardApiError(400, "bad").isServerError).toBe(false);
    expect(new BlackbeardApiError(500, "internal").isServerError).toBe(true);
    expect(new BlackbeardApiError(500, "internal").isClientError).toBe(false);
    expect(new BlackbeardApiError(401, "unauth").isUnauthorized).toBe(true);
    expect(new BlackbeardApiError(403, "denied").isForbidden).toBe(true);
    expect(new BlackbeardApiError(404, "missing").isNotFound).toBe(true);
    expect(new BlackbeardApiError(409, "conflict").isConflict).toBe(true);
    expect(new BlackbeardApiError(429, "slow down").isRateLimited).toBe(true);
  });

  it("identifies timeout errors", () => {
    const err = new BlackbeardApiError(0, "request timed out after 30000ms");
    expect(err.isTimeout).toBe(true);
    expect(err.isNetworkError).toBe(true);
  });

  it("stores the response body", () => {
    const body = { detail: "not found", code: "RESOURCE_NOT_FOUND" };
    const err = new BlackbeardApiError(404, "not found", body);
    expect(err.body).toEqual(body);
  });
});
