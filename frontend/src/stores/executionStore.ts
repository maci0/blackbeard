import { create } from 'zustand'
import { api } from '@/api/client'

export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export interface ExecutionTask {
  id: string
  task_name: string
  agent_name: string | null
  order: number
  status: string
  output: string | null
  error: string | null
  tokens_used: number
  cost_usd: number
  started_at: string | null
  completed_at: string | null
}

export interface ExecutionEvent {
  sequence: number
  event_type: string
  timestamp: string
  data: Record<string, unknown>
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
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  tasks: ExecutionTask[]
}

interface ExecutionState {
  executions: Execution[]
  currentExecution: Execution | null
  events: ExecutionEvent[]
  spendData: Record<string, unknown> | null
  loading: boolean
  error: string | null

  fetchExecutions: (crewName?: string) => Promise<void>
  fetchExecution: (id: string) => Promise<void>
  kickoff: (crewName: string, inputs: Record<string, unknown>) => Promise<Execution>
  cancelExecution: (id: string) => Promise<void>
  pollExecution: (id: string) => Promise<void>
  pollExecutions: (crewName?: string) => Promise<void>
  addEvents: (newEvents: ExecutionEvent[]) => void
  clearEvents: () => void
  fetchEvents: (id: string, after?: number) => Promise<void>
  fetchSpend: (id: string) => Promise<void>
}

function executionsPath(crewName?: string): string {
  return crewName
    ? `/api/v1/executions?crew_name=${encodeURIComponent(crewName)}`
    : '/api/v1/executions'
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  executions: [],
  currentExecution: null,
  events: [],
  spendData: null,
  loading: false,
  error: null,

  fetchExecutions: async (crewName?: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.get<{ items: Execution[]; total: number }>(executionsPath(crewName))
      set({ executions: result.items, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  fetchExecution: async (id: string) => {
    // Only clear currentExecution when loading a *different* execution
    // to avoid flickering the spinner on refetch of the same execution.
    set((state) => ({
      loading: true,
      error: null,
      currentExecution: state.currentExecution?.id === id ? state.currentExecution : null,
      spendData: state.currentExecution?.id === id ? state.spendData : null,
    }))
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
    const updated = await api.patch<Execution>(`/api/v1/executions/${id}/cancel`)
    set((state) => ({
      executions: state.executions.map((e) => (e.id === id ? updated : e)),
      currentExecution: state.currentExecution?.id === id ? updated : state.currentExecution,
    }))
  },

  pollExecution: async (id: string) => {
    const execution = await api.get<Execution>(`/api/v1/executions/${id}`)
    set((state) => ({
      currentExecution: state.currentExecution?.id === id ? execution : state.currentExecution,
      executions: state.executions.map((e) => (e.id === id ? execution : e)),
    }))
  },

  pollExecutions: async (crewName?: string) => {
    try {
      const result = await api.get<{ items: Execution[]; total: number }>(executionsPath(crewName))
      set({ executions: result.items })
    } catch {
      // Silently ignore poll failures to avoid flashing errors
    }
  },

  addEvents: (newEvents: ExecutionEvent[]) => {
    set((state) => {
      if (newEvents.length === 0) return state
      const lastSeq = state.events.length > 0 ? state.events[state.events.length - 1]!.sequence : -1
      const unique = newEvents.filter((e) => e.sequence > lastSeq)
      if (unique.length === 0) return state
      return { events: state.events.concat(unique) }
    })
  },

  clearEvents: () => {
    set({ events: [] })
  },

  fetchEvents: async (id: string, after?: number) => {
    // Default to the last known sequence to avoid re-fetching all events
    const lastSeq =
      after ??
      (() => {
        const evts = get().events
        return evts.length > 0 ? evts[evts.length - 1]!.sequence : -1
      })()
    try {
      const result = await api.get<{ events: ExecutionEvent[]; next_sequence: number }>(
        `/api/v1/executions/${id}/events?after=${lastSeq}&limit=200`,
      )
      get().addEvents(result.events)
    } catch {
      // Silently ignore — events are supplementary
    }
  },

  fetchSpend: async (id: string) => {
    try {
      const result = await api.get<Record<string, unknown>>(`/api/v1/executions/${id}/spend`)
      set({ spendData: result })
    } catch {
      // Silently ignore — spend data is optional (LiteLLM may not be tracking)
      set({ spendData: null })
    }
  },
}))
