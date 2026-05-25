import {
  BlackbeardApiError,
  TERMINAL_STATUSES,
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
  Namespace: "namespaces",
};

export class BlackbeardClient {
  private baseUrl: string;
  private apiKey?: string;
  private token?: string;
  private timeout: number;

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
        throw new BlackbeardApiError(0, `Request timed out after ${this.timeout}ms`);
      }
      throw new BlackbeardApiError(
        0,
        err instanceof Error ? err.message : "Network request failed"
      );
    }

    if (!resp.ok) {
      const errorBody = await resp
        .json()
        .catch(() => ({ detail: resp.statusText }));
      const detail =
        typeof errorBody.detail === "string" ? errorBody.detail : resp.statusText;
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

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/api/v1/health");
  }

  async readiness(): Promise<ReadinessResponse> {
    return this.request<ReadinessResponse>(
      "GET",
      "/api/v1/health/ready"
    );
  }

  // ── Auth ──

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

  async whoami(): Promise<User> {
    return this.request<User>("GET", "/api/v1/auth/me");
  }

  async generateApiKey(): Promise<{ api_key: string }> {
    return this.request<{ api_key: string }>("POST", "/api/v1/auth/api-key");
  }

  async revokeApiKey(): Promise<void> {
    await this.request<void>("DELETE", "/api/v1/auth/api-key");
  }

  // ── Resources ──

  private plural(kind: string): string {
    const p = KIND_PLURALS[kind];
    if (p) return p;
    if (Object.values(KIND_PLURALS).includes(kind)) return kind;
    throw new Error(
      `Unknown resource kind '${kind}'. Valid kinds: ${Object.keys(KIND_PLURALS).sort().join(", ")}`
    );
  }

  async list(
    kind: string,
    options?: {
      namespace?: string;
      label_selector?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<ListResponse<Resource>> {
    const params = new URLSearchParams();
    params.set("namespace", options?.namespace ?? "default");
    if (options?.label_selector)
      params.set("label_selector", options.label_selector);
    params.set("limit", String(options?.limit ?? 100));
    params.set("offset", String(options?.offset ?? 0));
    return this.request<ListResponse<Resource>>(
      "GET",
      `/api/v1/${this.plural(kind)}?${params}`
    );
  }

  async get(
    kind: string,
    name: string,
    namespace?: string
  ): Promise<Resource> {
    const params = new URLSearchParams({
      namespace: namespace ?? "default",
    });
    return this.request<Resource>(
      "GET",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`
    );
  }

  async create(resource: Resource): Promise<Resource> {
    return this.request<Resource>(
      "POST",
      `/api/v1/${this.plural(resource.kind)}`,
      resource
    );
  }

  async update(
    kind: string,
    name: string,
    resource: Partial<Resource>,
    namespace?: string
  ): Promise<Resource> {
    const params = new URLSearchParams({
      namespace: namespace ?? "default",
    });
    return this.request<Resource>(
      "PUT",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`,
      resource
    );
  }

  async delete(kind: string, name: string, namespace?: string): Promise<void> {
    const params = new URLSearchParams({
      namespace: namespace ?? "default",
    });
    await this.request<void>(
      "DELETE",
      `/api/v1/${this.plural(kind)}/${encodeURIComponent(name)}?${params}`
    );
  }

  async apply(resources: Resource[]): Promise<Resource[]> {
    const results: Resource[] = [];
    for (const res of resources) {
      const result = await this.create(res);
      results.push(result);
    }
    return results;
  }

  // ── Executions ──

  async kickoff(
    crewName: string,
    inputs?: Record<string, unknown>,
    namespace?: string
  ): Promise<Execution> {
    const params = new URLSearchParams({
      namespace: namespace ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${encodeURIComponent(crewName)}/kickoff?${params}`,
      { inputs: inputs ?? {} }
    );
  }

  async train(
    crewName: string,
    options?: {
      inputs?: Record<string, unknown>;
      n_iterations?: number;
      filename?: string;
      namespace?: string;
    }
  ): Promise<Execution> {
    const params = new URLSearchParams({
      namespace: options?.namespace ?? "default",
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

  async test(
    crewName: string,
    options?: {
      inputs?: Record<string, unknown>;
      n_iterations?: number;
      namespace?: string;
    }
  ): Promise<Execution> {
    const params = new URLSearchParams({
      namespace: options?.namespace ?? "default",
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

  async runFlow(
    flowName: string,
    inputs?: Record<string, unknown>,
    namespace?: string
  ): Promise<Execution> {
    const params = new URLSearchParams({
      namespace: namespace ?? "default",
    });
    return this.request<Execution>(
      "POST",
      `/api/v1/flows/${encodeURIComponent(flowName)}/run?${params}`,
      { inputs: inputs ?? {} }
    );
  }

  async getExecution(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "GET",
      `/api/v1/executions/${encodeURIComponent(executionId)}`
    );
  }

  async listExecutions(options?: {
    crew_name?: string;
    namespace?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Execution>> {
    const params = new URLSearchParams();
    if (options?.crew_name) params.set("crew_name", options.crew_name);
    if (options?.namespace) params.set("namespace", options.namespace);
    if (options?.status) params.set("status", options.status);
    params.set("limit", String(options?.limit ?? 100));
    params.set("offset", String(options?.offset ?? 0));
    const qs = params.toString();
    return this.request<ListResponse<Execution>>(
      "GET",
      `/api/v1/executions${qs ? `?${qs}` : ""}`
    );
  }

  async getExecutionSpend(
    executionId: string
  ): Promise<SpendRecord[]> {
    return this.request<SpendRecord[]>(
      "GET",
      `/api/v1/executions/${encodeURIComponent(executionId)}/spend`
    );
  }

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

  async cancel(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "PATCH",
      `/api/v1/executions/${encodeURIComponent(executionId)}/cancel`
    );
  }

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

  async retry(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "POST",
      `/api/v1/executions/${encodeURIComponent(executionId)}/retry`
    );
  }

  async wait(
    executionId: string,
    pollInterval = 2000,
    timeout = 300_000
  ): Promise<Execution> {
    const deadline = Date.now() + timeout;

    while (true) {
      const exec = await this.getExecution(executionId);
      if (TERMINAL_STATUSES.has(exec.status)) return exec;
      if (Date.now() >= deadline) {
        throw new BlackbeardApiError(
          0,
          `Execution ${executionId} did not complete within ${timeout}ms (current status: ${exec.status})`
        );
      }
      await new Promise((r) => setTimeout(r, pollInterval));
    }
  }

  async exportAll(namespace = "default"): Promise<Resource[]> {
    const responses = await Promise.all(
      Object.keys(KIND_PLURALS).map((kind) =>
        this.list(kind, { namespace, limit: 1000 })
      )
    );
    return responses.flatMap((r) => r.items);
  }

  async exportYaml(namespace = "default"): Promise<string> {
    const params = new URLSearchParams({ namespace });
    const resp = await this.rawRequest("GET", `/api/v1/resources/export?${params}`);
    return resp.text();
  }
}
