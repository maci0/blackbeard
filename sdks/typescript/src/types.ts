/** Configuration for the Blackbeard API connection. */
export interface BlackbeardConfig {
  /** Base URL of the Blackbeard API (e.g. "https://blackbeard.example.com"). */
  baseUrl?: string;
  /** System API key for authentication (mutually exclusive with token). */
  apiKey?: string;
  /** JWT access token for authentication (mutually exclusive with apiKey). */
  token?: string;
  /** Request timeout in milliseconds (default: 30000). */
  timeout?: number;
}

/** Metadata attached to every Blackbeard resource. */
export interface ResourceMetadata {
  name: string;
  project?: string;
  labels?: Record<string, string>;
}

/** A generic Blackbeard resource returned from the API. */
export interface Resource {
  id?: string;
  apiVersion: string;
  kind: string;
  metadata: ResourceMetadata;
  spec: Record<string, unknown>;
  version?: number;
  created_at?: string;
  updated_at?: string;
}

/** Paginated list response from the API. */
export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

/** An individual task within an execution. */
export interface ExecutionTask {
  id: string;
  task_name: string;
  agent_name: string | null;
  order: number;
  status: "pending" | "running" | "completed" | "failed";
  output: string | null;
  error: string | null;
  tokens_used: number;
  cost_usd: string;
  started_at: string | null;
  completed_at: string | null;
}

/** Execution record returned from the API. */
export interface Execution {
  id: string;
  crew_name: string;
  crew_project: string;
  execution_type: "kickoff" | "train" | "test" | "flow";
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  n_iterations: number | null;
  training_file: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  error: string | null;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: string;
  initiated_by: string | null;
  principal_chain: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  tasks?: ExecutionTask[];
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

/** Execution event returned from the events endpoint. */
export interface ExecutionEvent {
  sequence: number;
  event_type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

/** Response shape from GET /executions/:id/events. */
export interface ExecutionEventsResponse {
  events: ExecutionEvent[];
  next_sequence: number;
  has_more: boolean;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string | null;
  token_type: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  uptime_s: number;
}

export interface ReadinessResponse {
  status: string;
  service: string;
  checks: Record<string, { status: string; latency_ms?: number; error?: string }>;
}

export interface HITLResponseResult {
  status: string;
  execution_id: string;
}

export interface SpendRecord {
  request_id: string;
  call_type: string;
  model: string;
  spend: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  startTime: string;
  endTime: string;
  [key: string]: unknown;
}

/** A single entry from the audit log. */
export interface AuditLogEntry {
  id: string;
  timestamp: string;
  actor_type: string;
  actor_id: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  request_id: string | null;
}

export const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

/** Summary of a resource version returned from the versions list endpoint. */
export interface VersionSummary {
  version: number;
  changed_by: string | null;
  created_at: string;
  changed_keys: string[];
}

/** Response shape from GET /{kind}/{name}/versions. */
export interface VersionListResponse {
  versions: VersionSummary[];
}

/** Full snapshot of a resource at a specific version. */
export interface VersionDetail {
  version: number;
  changed_by: string | null;
  created_at: string;
  spec: Record<string, unknown>;
  labels: Record<string, string> | null;
}

/** Options for constructing a {@link BlackbeardApiError}. */
export interface BlackbeardApiErrorOptions extends ErrorOptions {
  /** Value of the X-Request-Id response header, if present. */
  requestId?: string;
  /** Parsed Retry-After header in seconds, if present. */
  retryAfter?: number;
}

/**
 * Normalize API error detail (string, list, or object) to a single string.
 * FastAPI validation errors return detail as an array of {loc, msg, type}.
 */
export function formatErrorDetail(detail: unknown, fallback: string): string {
  if (detail == null) return fallback;
  if (typeof detail === "string") return detail || fallback;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) {
        const rec = item as { loc?: unknown[]; msg?: string };
        const locParts = (rec.loc ?? [])
          .filter((x) => x !== "body")
          .map(String);
        const locStr = locParts.join(".");
        const msg = rec.msg ?? String(item);
        return locStr ? `${locStr}: ${msg}` : msg;
      }
      return String(item);
    });
    return parts.length > 0 ? parts.join("; ") : fallback;
  }
  return String(detail);
}

/** Error thrown when the API returns a non-OK response or a network failure occurs. */
export class BlackbeardApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body?: Record<string, unknown>;
  /** Value of the X-Request-Id response header, if present. */
  readonly requestId?: string;
  /** Parsed Retry-After header in seconds, if present. */
  readonly retryAfter?: number;

  constructor(
    status: number,
    detail: string,
    body?: Record<string, unknown>,
    options?: BlackbeardApiErrorOptions,
  ) {
    super(`HTTP ${status}: ${detail}`, options);
    this.name = "BlackbeardApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
    this.requestId = options?.requestId;
    this.retryAfter = options?.retryAfter;
  }

  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  get isServerError(): boolean {
    return this.status >= 500;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  get isTimeout(): boolean {
    return this.status === 0 && this.detail.toLowerCase().includes("timed out");
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}
