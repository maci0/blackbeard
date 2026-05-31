import {
  BlackbeardApiError,
  TERMINAL_STATUSES,
  type AuditLogEntry,
  type BlackbeardConfig,
  type Resource,
  type Execution,
  type ExecutionEventsResponse,
  type ListResponse,
  type AuthResponse,
  type TokenResponse,
  type User,
  type HealthResponse,
  type ReadinessResponse,
  type HITLResponseResult,
  type SpendRecord,
  type VersionListResponse,
  type VersionDetail,
} from "./types.js";

export const KIND_PLURALS: Record<string, string> = {
  Agent: "agents",
  Task: "tasks",
  Crew: "crews",
  Tool: "tools",
  LLMConnection: "llm-connections",
  AgentPolicy: "agent-policies",
  Guardrail: "guardrails",
  Flow: "flows",
  KnowledgeSource: "knowledge-sources",
  Role: "roles",
  RoleBinding: "role-bindings",
  Automation: "automations",
  Project: "projects",
  ServiceAccount: "service-accounts",
};

const _PLURAL_SET: ReadonlySet<string> = new Set(Object.values(KIND_PLURALS));

export class BlackbeardClient {
  private readonly baseUrl: string;
  private apiKey?: string;
  private token?: string;
  private readonly timeout: number;

  constructor(config: BlackbeardConfig = {}) {
    const env =
      typeof globalThis !== "undefined" &&
      typeof (globalThis as Record<string, unknown>).process === "object"
        ? (
            (globalThis as Record<string, unknown>).process as {
              env?: Record<string, string | undefined>;
            }
          ).env
        : undefined;

    this.baseUrl = (
      config.baseUrl ??
      env?.BLACKBEARD_BASE_URL ??
      "http://localhost:8000"
    ).replace(/\/+$/, "");
    this.apiKey = config.apiKey ?? env?.BLACKBEARD_API_KEY;
    this.token = config.token ?? env?.BLACKBEARD_TOKEN;
    this.timeout = config.timeout ?? 30_000;
  }

  private headers(hasBody: boolean): Record<string, string> {
    const h: Record<string, string> = {};
    if (hasBody) h["Content-Type"] = "application/json";
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    } else if (this.apiKey) {
      h["X-API-Key"] = this.apiKey;
    }
    return h;
  }

  private async rawRequest(
    method: string,
    path: string,
    body?: unknown
  ): Promise<Response> {
    let resp: Response;
    try {
      resp = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers(body !== undefined),
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(this.timeout),
      });
    } catch (err) {
      if (
        err instanceof DOMException &&
        (err.name === "TimeoutError" || err.name === "AbortError")
      ) {
        throw new BlackbeardApiError(0, `${method} ${path}: request timed out after ${this.timeout}ms`, undefined, { cause: err });
      }
      throw new BlackbeardApiError(
        0,
        `${method} ${path}: ${err instanceof Error ? err.message : "network request failed"}`,
        undefined,
        { cause: err },
      );
    }

    if (!resp.ok) {
      const fallback = resp.statusText || `HTTP ${resp.status}`;
      const errorBody = (await resp
        .json()
        .catch(() => ({}))) as Record<string, unknown>;
      const detail =
        (typeof errorBody.detail === "string" && errorBody.detail) ? errorBody.detail : fallback;
      throw new BlackbeardApiError(resp.status, detail, errorBody);
    }

    return resp;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const resp = await this.rawRequest(method, path, body);
    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  }

  // ── Health ──

  /** Check API liveness. */
  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/api/v1/health");
  }

  /** Check API readiness (database, Valkey, LiteLLM connectivity). */
  async readiness(): Promise<ReadinessResponse> {
    return this.request<ReadinessResponse>(
      "GET",
      "/api/v1/health/ready"
    );
  }

  // ── Auth ──

  /** Authenticate with email and password. Stores the access token for subsequent requests. */
  async login(email: string, password: string): Promise<AuthResponse> {
    const result = await this.request<AuthResponse>(
      "POST",
      "/api/v1/auth/login",
      { email, password }
    );
    this.token = result.access_token;
    this.apiKey = undefined;
    return result;
  }

  /** Register a new user account. Stores the access token for subsequent requests. */
  async register(
    email: string,
    password: string,
    displayName: string
  ): Promise<AuthResponse> {
    const result = await this.request<AuthResponse>(
      "POST",
      "/api/v1/auth/register",
      { email, password, display_name: displayName }
    );
    this.token = result.access_token;
    this.apiKey = undefined;
    return result;
  }

  /** Exchange a refresh token for a new access token. Updates the stored token. */
  async refresh(refreshToken: string): Promise<TokenResponse> {
    const result = await this.request<TokenResponse>(
      "POST",
      "/api/v1/auth/refresh",
      { refresh_token: refreshToken }
    );
    this.token = result.access_token;
    this.apiKey = undefined;
    return result;
  }

  /** Get the currently authenticated user's profile. */
  async whoami(): Promise<User> {
    return this.request<User>("GET", "/api/v1/auth/me");
  }

  /** Generate or rotate the current user's API key. Requires JWT auth. */
  async generateApiKey(): Promise<{ api_key: string }> {
    return this.request<{ api_key: string }>("POST", "/api/v1/auth/api-key");
  }

  /** Revoke the current user's API key. Idempotent. Requires JWT auth. */
  async revokeApiKey(): Promise<void> {
    await this.request<void>("DELETE", "/api/v1/auth/api-key");
  }

  // ── Resources ──

  /** Resolve a resource kind to its URL plural form. */
  private plural(kind: string): string {
    const p = KIND_PLURALS[kind];
    if (p) return p;
    if (_PLURAL_SET.has(kind)) return kind;
    throw new BlackbeardApiError(
      0,
      `Unknown resource kind '${kind}'. Valid kinds: ${Object.keys(KIND_PLURALS).sort().join(", ")}`
    );
  }

  /** List resources of a given kind with optional filters. */
  async list(
    kind: string,
    options?: {
      project?: string;
      label_selector?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<ListResponse<Resource>> {
    const params = new URLSearchParams();
    params.set("project", options?.project ?? "default");
    if (options?.label_selector)
      params.set("label_selector", options.label_selector);
    params.set("limit", String(options?.limit ?? 100));
    params.set("offset", String(options?.offset ?? 0));
    return this.request<ListResponse<Resource>>(
      "GET",
      `/api/v1/${this.plural(kind)}?${params}`
    );
  }

  /** Get a single resource by kind and name. */
  async get(
    kind: string,
    name: string,
    project?: string
  ): Promise<Resource> {
    const params = new URLSearchParams({
      project: project ?? "default",
    });
    return this.request<Resource>(
      "GET",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`
    );
  }

  /** Create a resource, or update it if one with the same kind/name/project exists. */
  async create(resource: Resource): Promise<Resource> {
    return this.request<Resource>(
      "POST",
      `/api/v1/${this.plural(resource.kind)}`,
      resource
    );
  }

  /** Update a resource by kind and name (optimistic locking via version). */
  async update(
    kind: string,
    name: string,
    resource: Partial<Resource>,
    project?: string
  ): Promise<Resource> {
    const params = new URLSearchParams({
      project: project ?? "default",
    });
    return this.request<Resource>(
      "PUT",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`,
      resource
    );
  }

  /** Delete a resource by kind and name. Idempotent. */
  async delete(kind: string, name: string, project?: string): Promise<void> {
    const params = new URLSearchParams({
      project: project ?? "default",
    });
    await this.request<void>(
      "DELETE",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`
    );
  }

  /** List version snapshots for a resource. */
  async listVersions(
    kind: string,
    name: string,
    project?: string
  ): Promise<VersionListResponse> {
    const params = new URLSearchParams({ project: project ?? "default" });
    return this.request<VersionListResponse>(
      "GET",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}/versions?${params}`
    );
  }

  /** Get the full snapshot of a resource at a specific version. */
  async getVersion(
    kind: string,
    name: string,
    version: number,
    project?: string
  ): Promise<VersionDetail> {
    const params = new URLSearchParams({ project: project ?? "default" });
    return this.request<VersionDetail>(
      "GET",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}/versions/${version}?${params}`
    );
  }

  /** Rollback a resource to a previous version. */
  async rollback(
    kind: string,
    name: string,
    version: number,
    project?: string
  ): Promise<Resource> {
    const params = new URLSearchParams({ project: project ?? "default" });
    return this.request<Resource>(
      "POST",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}/rollback?${params}`,
      { version }
    );
  }

  /** Create or update multiple resources (sequential upsert). */
  async apply(resources: Resource[]): Promise<Resource[]> {
    const results: Resource[] = [];
    for (let i = 0; i < resources.length; i++) {
      const res = resources[i]!;
      try {
        results.push(await this.create(res));
      } catch (err) {
        if (err instanceof BlackbeardApiError) {
          const name = res.metadata?.name ?? "?";
          throw new BlackbeardApiError(
            err.status,
            `[${i}] ${res.kind}/${name}: ${err.detail}`,
            err.body,
            { cause: err },
          );
        }
        throw err;
      }
    }
    return results;
  }

  // ── Executions ──

  /** Kick off a crew execution. */
  async kickoff(
    crewName: string,
    inputs?: Record<string, unknown>,
    project?: string
  ): Promise<Execution> {
    const params = new URLSearchParams({
      project: project ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${encodeURIComponent(crewName)}/kickoff?${params}`,
      { inputs: inputs ?? {} }
    );
  }

  /** Start a crew training run. */
  async train(
    crewName: string,
    options?: {
      inputs?: Record<string, unknown>;
      n_iterations?: number;
      filename?: string;
      project?: string;
    }
  ): Promise<Execution> {
    const params = new URLSearchParams({
      project: options?.project ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${encodeURIComponent(crewName)}/train?${params}`,
      {
        inputs: options?.inputs ?? {},
        n_iterations: options?.n_iterations ?? 3,
        filename: options?.filename ?? "training_data.pkl",
      }
    );
  }

  /** Start a crew test run. */
  async test(
    crewName: string,
    options?: {
      inputs?: Record<string, unknown>;
      n_iterations?: number;
      project?: string;
    }
  ): Promise<Execution> {
    const params = new URLSearchParams({
      project: options?.project ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${encodeURIComponent(crewName)}/test?${params}`,
      {
        inputs: options?.inputs ?? {},
        n_iterations: options?.n_iterations ?? 3,
      }
    );
  }

  /** Run a flow. */
  async runFlow(
    flowName: string,
    inputs?: Record<string, unknown>,
    project?: string
  ): Promise<Execution> {
    const params = new URLSearchParams({
      project: project ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/flows/${encodeURIComponent(flowName)}/run?${params}`,
      { inputs: inputs ?? {} }
    );
  }

  /** Get execution details by ID. */
  async getExecution(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "GET",
      `/api/v1/executions/${encodeURIComponent(executionId)}`
    );
  }

  /** List executions with optional filters. */
  async listExecutions(options?: {
    crew_name?: string;
    project?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Execution>> {
    const params = new URLSearchParams();
    if (options?.crew_name) params.set("crew_name", options.crew_name);
    if (options?.project) params.set("project", options.project);
    if (options?.status) params.set("status", options.status);
    params.set("limit", String(options?.limit ?? 100));
    params.set("offset", String(options?.offset ?? 0));
    const qs = params.toString();
    return this.request<ListResponse<Execution>>(
      "GET",
      `/api/v1/executions${qs ? `?${qs}` : ""}`
    );
  }

  /** Get LiteLLM spend data for an execution. */
  async getExecutionSpend(
    executionId: string
  ): Promise<SpendRecord[]> {
    return this.request<SpendRecord[]>(
      "GET",
      `/api/v1/executions/${encodeURIComponent(executionId)}/spend`
    );
  }

  /** List execution events for streaming/replay. */
  async getExecutionEvents(
    executionId: string,
    options?: { after?: number; limit?: number }
  ): Promise<ExecutionEventsResponse> {
    const params = new URLSearchParams();
    params.set("after", String(options?.after ?? -1));
    params.set("limit", String(options?.limit ?? 200));
    return this.request<ExecutionEventsResponse>(
      "GET",
      `/api/v1/executions/${encodeURIComponent(executionId)}/events?${params}`
    );
  }

  /** Cancel a queued or running execution. */
  async cancel(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "PATCH",
      `/api/v1/executions/${encodeURIComponent(executionId)}/cancel`
    );
  }

  /** Submit a human-in-the-loop response to a paused execution. */
  async respond(
    executionId: string,
    response: string,
    feedback?: string
  ): Promise<HITLResponseResult> {
    const body: Record<string, string> = { response };
    if (feedback !== undefined) body.feedback = feedback;
    return this.request<HITLResponseResult>(
      "POST",
      `/api/v1/executions/${encodeURIComponent(executionId)}/respond`,
      body
    );
  }

  /** Retry a terminal execution. Creates a new execution with the same inputs. */
  async retry(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "POST",
      `/api/v1/executions/${encodeURIComponent(executionId)}/retry`
    );
  }

  /** Wait for an execution to reach a terminal status. Polls until complete or timeout. */
  async wait(
    executionId: string,
    pollInterval = 2000,
    timeout = 300_000
  ): Promise<Execution> {
    const deadline = performance.now() + timeout;

    while (true) {
      const exec = await this.getExecution(executionId);
      if (TERMINAL_STATUSES.has(exec.status)) return exec;
      if (performance.now() >= deadline) {
        throw new BlackbeardApiError(
          0,
          `Execution ${executionId} did not complete within ${timeout}ms (current status: ${exec.status})`
        );
      }
      await new Promise((r) => setTimeout(r, pollInterval));
    }
  }

  /** List audit log entries with optional filters. */
  async listAuditLogs(options?: {
    action?: string;
    actor_id?: string;
    resource_type?: string;
    resource_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<AuditLogEntry>> {
    const params = new URLSearchParams();
    if (options?.action) params.set("action", options.action);
    if (options?.actor_id) params.set("actor_id", options.actor_id);
    if (options?.resource_type) params.set("resource_type", options.resource_type);
    if (options?.resource_id) params.set("resource_id", options.resource_id);
    params.set("limit", String(options?.limit ?? 100));
    params.set("offset", String(options?.offset ?? 0));
    const qs = params.toString();
    return this.request<ListResponse<AuditLogEntry>>(
      "GET",
      `/api/v1/audit-logs${qs ? `?${qs}` : ""}`
    );
  }

  /** Fetch all resources by listing each kind in parallel (14 requests). For a single-request alternative, use {@link exportYaml}. */
  async exportAll(project = "default"): Promise<Resource[]> {
    const responses = await Promise.all(
      Object.keys(KIND_PLURALS).map((kind) =>
        this.list(kind, { project, limit: 1000 })
      )
    );
    return responses.flatMap((r) => r.items);
  }

  /** Export all resources as a multi-document YAML string via the server's bulk export endpoint (single request). */
  async exportYaml(project = "default"): Promise<string> {
    const params = new URLSearchParams({ project });
    const resp = await this.rawRequest("GET", `/api/v1/resources/export?${params}`);
    return resp.text();
  }
}
