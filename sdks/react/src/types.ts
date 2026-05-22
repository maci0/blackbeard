/** Configuration for the Blackbeard API connection. */
export interface BlackbeardConfig {
  /** Base URL of the Blackbeard API (e.g. "https://blackbeard.example.com"). */
  baseUrl?: string
  /** System API key for authentication (mutually exclusive with token). */
  apiKey?: string
  /** JWT access token for authentication (mutually exclusive with apiKey). */
  token?: string
  /** Request timeout in milliseconds (default: 30000). */
  timeout?: number
}

/** Metadata attached to every Blackbeard resource. */
export interface ResourceMetadata {
  name: string
  namespace?: string
  labels?: Record<string, string>
}

/** A generic Blackbeard resource returned from the API. */
export interface Resource {
  id?: string
  apiVersion: string
  kind: string
  metadata: ResourceMetadata
  spec: Record<string, unknown>
  version?: number
  created_at?: string
  updated_at?: string
}

/** Paginated list response from the API. */
export interface ListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

/** An individual task within an execution. */
export interface ExecutionTask {
  id: string
  task_name: string
  agent_name: string | null
  order: number
  status: string
  output: string | null
  error: string | null
  tokens_used: number
  cost_usd: string
  started_at: string | null
  completed_at: string | null
}

/** Execution record returned from the API. */
export interface Execution {
  id: string
  crew_name: string
  crew_namespace: string
  execution_type: 'kickoff' | 'train' | 'test' | 'flow'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  n_iterations: number | null
  training_file: string | null
  inputs: Record<string, unknown>
  outputs: Record<string, unknown> | null
  error: string | null
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  cost_usd: string
  initiated_by: string | null
  principal_chain: Record<string, unknown> | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  tasks?: ExecutionTask[]
}

/** Execution event returned from the events endpoint. */
export interface ExecutionEvent {
  sequence: number
  event_type: string
  timestamp: string
  data: Record<string, unknown>
}

/** Response shape from GET /executions/:id/events. */
export interface ExecutionEventsResponse {
  events: ExecutionEvent[]
  next_sequence: number
  has_more: boolean
}

/** Error thrown by apiFetch when the API returns a non-OK response. */
export class BlackbeardApiError extends Error {
  readonly status: number
  readonly detail: string
  readonly body?: Record<string, unknown>

  constructor(status: number, detail: string, body?: Record<string, unknown>) {
    super(`HTTP ${status}: ${detail}`)
    this.name = 'BlackbeardApiError'
    this.status = status
    this.detail = detail
    this.body = body
  }

  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }

  get isServerError(): boolean {
    return this.status >= 500
  }
}

/** Statuses after which an execution will not change. */
export const TERMINAL_STATUSES: ReadonlySet<string> = new Set(['completed', 'failed', 'cancelled'])
