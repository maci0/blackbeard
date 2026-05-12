import { create } from 'zustand'
import { api } from '@/api/client'

export interface ExecutionTask {
  id: string
  task_name: string
  agent_name: string | null
  order: number
  status: string
  output: string | null
  error: string | null
}

export interface Execution {
  id: string
  crew_name: string
  crew_namespace: string
  status: string
  inputs: Record<string, unknown>
  outputs: Record<string, unknown> | null
  error: string | null
  total_tokens: number
  cost_usd: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  tasks: ExecutionTask[]
  langfuse_trace_url: string | null
}

interface ExecutionState {
  executions: Execution[]
  currentExecution: Execution | null
  loading: boolean
  error: string | null

  fetchExecutions: (crewName?: string) => Promise<void>
  fetchExecution: (id: string) => Promise<void>
  kickoff: (crewName: string, inputs: Record<string, unknown>) => Promise<Execution>
  cancelExecution: (id: string) => Promise<void>
  pollExecution: (id: string) => Promise<void>
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  executions: [],
  currentExecution: null,
  loading: false,
  error: null,

  fetchExecutions: async (crewName?: string) => {
    set({ loading: true, error: null })
    try {
      const path = crewName
        ? `/api/v1/executions?crew_name=${encodeURIComponent(crewName)}`
        : '/api/v1/executions'
      const result = await api.get<{ items: Execution[]; total: number }>(path)
      set({ executions: result.items, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  fetchExecution: async (id: string) => {
    set({ loading: true, error: null })
    try {
      const execution = await api.get<Execution>(`/api/v1/executions/${id}`)
      set({ currentExecution: execution, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  kickoff: async (crewName: string, inputs: Record<string, unknown>) => {
    const execution = await api.post<Execution>(`/api/v1/crews/${crewName}/kickoff`, {
      inputs,
    })
    set((state) => ({ executions: [execution, ...state.executions] }))
    return execution
  },

  cancelExecution: async (id: string) => {
    await api.post<void>(`/api/v1/executions/${id}/cancel`, {})
    const updated = await api.get<Execution>(`/api/v1/executions/${id}`)
    set((state) => ({
      executions: state.executions.map((e) => (e.id === id ? updated : e)),
      currentExecution: state.currentExecution?.id === id ? updated : state.currentExecution,
    }))
  },

  pollExecution: async (id: string) => {
    const execution = await api.get<Execution>(`/api/v1/executions/${id}`)
    set((state) => ({
      currentExecution:
        state.currentExecution?.id === id ? execution : state.currentExecution,
      executions: state.executions.map((e) => (e.id === id ? execution : e)),
    }))
  },
}))
