import type {
  BlackbeardConfig,
  Resource,
  Execution,
  ListResponse,
  AuthResponse,
  User,
} from "./types.js";

const KIND_PLURALS: Record<string, string> = {
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
};

export class BlackbeardClient {
  private baseUrl: string;
  private apiKey?: string;
  private token?: string;
  private timeout: number;

  constructor(config: BlackbeardConfig = {}) {
    this.baseUrl = (config.baseUrl ?? "http://localhost:8000").replace(
      /\/$/,
      ""
    );
    this.apiKey = config.apiKey;
    this.token = config.token;
    this.timeout = config.timeout ?? 30_000;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    } else if (this.apiKey) {
      h["X-API-Key"] = this.apiKey;
    }
    return h;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers(),
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!resp.ok) {
        const error = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(
          `HTTP ${resp.status}: ${typeof error.detail === "string" ? error.detail : resp.statusText}`
        );
      }

      if (resp.status === 204) return undefined as T;
      return (await resp.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  // ── Auth ──

  async login(email: string, password: string): Promise<AuthResponse> {
    const result = await this.request<AuthResponse>(
      "POST",
      "/api/v1/auth/login",
      { email, password }
    );
    this.token = result.access_token;
    return result;
  }

  async whoami(): Promise<User> {
    return this.request<User>("GET", "/api/v1/auth/me");
  }

  // ── Resources ──

  private plural(kind: string): string {
    return KIND_PLURALS[kind] ?? `${kind.toLowerCase()}s`;
  }

  async list(
    kind: string,
    options?: { namespace?: string; limit?: number; offset?: number }
  ): Promise<ListResponse<Resource>> {
    const params = new URLSearchParams();
    if (options?.namespace) params.set("namespace", options.namespace);
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.offset) params.set("offset", String(options.offset));
    const qs = params.toString();
    return this.request<ListResponse<Resource>>(
      "GET",
      `/api/v1/${this.plural(kind)}${qs ? `?${qs}` : ""}`
    );
  }

  async get(
    kind: string,
    name: string,
    namespace?: string
  ): Promise<Resource> {
    const qs = namespace ? `?namespace=${namespace}` : "";
    return this.request<Resource>(
      "GET",
      `/api/v1/${this.plural(kind)}/${name}${qs}`
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
    const qs = namespace ? `?namespace=${namespace}` : "";
    return this.request<Resource>(
      "PUT",
      `/api/v1/${this.plural(kind)}/${name}${qs}`,
      resource
    );
  }

  async delete(kind: string, name: string, namespace?: string): Promise<void> {
    const qs = namespace ? `?namespace=${namespace}` : "";
    await this.request<void>(
      "DELETE",
      `/api/v1/${this.plural(kind)}/${name}${qs}`
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
    const qs = namespace ? `?namespace=${namespace}` : "";
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${crewName}/kickoff${qs}`,
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
    const qs = options?.namespace ? `?namespace=${options.namespace}` : "";
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${crewName}/train${qs}`,
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
    const qs = options?.namespace ? `?namespace=${options.namespace}` : "";
    return this.request<Execution>(
      "POST",
      `/api/v1/crews/${crewName}/test${qs}`,
      {
        inputs: options?.inputs ?? {},
        n_iterations: options?.n_iterations ?? 3,
      }
    );
  }

  async getExecution(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "GET",
      `/api/v1/executions/${executionId}`
    );
  }

  async listExecutions(options?: {
    crew_name?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResponse<Execution>> {
    const params = new URLSearchParams();
    if (options?.crew_name) params.set("crew_name", options.crew_name);
    if (options?.status) params.set("status", options.status);
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.offset) params.set("offset", String(options.offset));
    const qs = params.toString();
    return this.request<ListResponse<Execution>>(
      "GET",
      `/api/v1/executions${qs ? `?${qs}` : ""}`
    );
  }

  async cancel(executionId: string): Promise<Execution> {
    return this.request<Execution>(
      "PATCH",
      `/api/v1/executions/${executionId}/cancel`
    );
  }

  async wait(
    executionId: string,
    pollInterval = 2000,
    timeout = 300_000
  ): Promise<Execution> {
    const terminal = new Set(["completed", "failed", "cancelled"]);
    const deadline = Date.now() + timeout;

    while (Date.now() < deadline) {
      const exec = await this.getExecution(executionId);
      if (terminal.has(exec.status)) return exec;
      await new Promise((r) => setTimeout(r, pollInterval));
    }
    throw new Error(`Execution ${executionId} did not complete within timeout`);
  }
}
