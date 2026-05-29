export interface Resource {
  id: string
  apiVersion: string
  kind: string
  metadata: {
    name: string
    project: string
    labels: Record<string, string>
  }
  spec: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

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

export interface ExecutionEvent {
  sequence: number
  event_type: string
  timestamp: string
  data: Record<string, unknown>
}

export type ExecutionType = 'kickoff' | 'train' | 'test' | 'flow'

export interface Execution {
  id: string
  crew_name: string
  crew_project: string
  execution_type: ExecutionType
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
  tasks: ExecutionTask[] | undefined
}

export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export type RunStatus = 'idle' | 'loading' | 'saving' | 'running' | 'success' | 'error'
