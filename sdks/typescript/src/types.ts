export interface BlackbeardConfig {
  baseUrl?: string;
  apiKey?: string;
  token?: string;
  timeout?: number;
}

export interface ResourceMetadata {
  name: string;
  namespace?: string;
  labels?: Record<string, string>;
}

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

export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ExecutionTask {
  id: string;
  task_name: string;
  agent_name: string | null;
  order: number;
  status: string;
  output: string | null;
  error: string | null;
  tokens_used: number;
  cost_usd: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Execution {
  id: string;
  crew_name: string;
  crew_namespace: string;
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
  tasks: ExecutionTask[];
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
