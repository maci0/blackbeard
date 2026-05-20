/** Configuration for the Blackbeard API connection. */
export interface BlackbeardConfig {
  /** Base URL of the Blackbeard API (e.g. "https://blackbeard.example.com"). */
  baseUrl: string
  /** System API key for authentication (mutually exclusive with token). */
  apiKey?: string
  /** JWT access token for authentication (mutually exclusive with apiKey). */
  token?: string
}

/** Metadata attached to every Blackbeard resource. */
export interface ResourceMetadata {
  name: string
  namespace: string
  labels: Record<string, string>
}

/** A generic Blackbeard resource returned from the API. */
export interface Resource {
  id: string
  apiVersion: string
  kind: string
  metadata: ResourceMetadata
  spec: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
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
  cost_usd: number | string
  started_at: string | null
  completed_at: string | null
}

/** Execution record returned from the API. */
export interface Execution {
  id: string
  crew_name: string
  crew_namespace: string
  execution_type: 'kickoff' | 'train' | 'test' | 'flow'
  status: string
  n_iterations: number | null
  training_file: string | null
  inputs: Record<string, unknown>
  outputs: Record<string, unknown> | null
  error: string | null
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number | string
  created_at: string
  started_at: string | null
  completed_at: string | null
  tasks?: ExecutionTask[]
}

/** Statuses after which an execution will not change. */
export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
