import { create } from 'zustand'
import { api } from '@/api/client'
import { getErrorMessage } from '@/lib/utils'
import type { Execution, ExecutionEvent } from '@/lib/types'

const MAX_EVENTS = 2000
const EVENTS_FETCH_LIMIT = 200

interface PaginationParams {
  limit?: number
  offset?: number
}

interface ExecutionState {
  executions: Execution[]
  executionsTotal: number
  currentExecution: Execution | null
  events: ExecutionEvent[]
  spendData: Record<string, unknown> | null
  loading: boolean
  error: string | null

  fetchExecutions: (crewName?: string, pagination?: PaginationParams) => Promise<void>
  fetchExecution: (id: string) => Promise<void>
  kickoff: (crewName: string, inputs: Record<string, unknown>) => Promise<Execution>
  cancelExecution: (id: string) => Promise<void>
  pollExecution: (id: string) => Promise<void>
  pollExecutions: (crewName?: string, pagination?: PaginationParams) => Promise<void>
  addEvents: (newEvents: ExecutionEvent[]) => void
  clearEvents: () => void
  fetchEvents: (id: string, after?: number) => Promise<void>
  fetchSpend: (id: string) => Promise<void>
}

function executionsPath(crewName?: string, pagination?: PaginationParams): string {
  const params = new URLSearchParams()
  if (crewName) params.set('crew_name', crewName)
  if (pagination?.limit != null) params.set('limit', String(pagination.limit))
  if (pagination?.offset != null) params.set('offset', String(pagination.offset))
  const qs = params.toString()
  return qs ? `/api/v1/executions?${qs}` : '/api/v1/executions'
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  executions: [],
  executionsTotal: 0,
  currentExecution: null,
  events: [],
  spendData: null,
  loading: false,
  error: null,

  fetchExecutions: async (crewName?: string, pagination?: PaginationParams) => {
    set({ loading: true, error: null })
    try {
      const result = await api.get<{ items: Execution[]; total: number }>(
        executionsPath(crewName, pagination),
      )
      set({ executions: result.items, executionsTotal: result.total, loading: false })
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to fetch executions')
      set({ error: message, loading: false })
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
      const message = getErrorMessage(err, 'Failed to fetch execution')
      set({ error: message, loading: false })
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
    try {
      const execution = await api.get<Execution>(`/api/v1/executions/${id}`)
      set((state) => {
        const prev = state.currentExecution
        if (
          prev?.id === id &&
          prev.status === execution.status &&
          prev.total_tokens === execution.total_tokens &&
          prev.error === execution.error &&
          (prev.tasks?.length ?? 0) === (execution.tasks?.length ?? 0)
        ) {
          const prevTasks = prev.tasks ?? []
          const nextTasks = execution.tasks ?? []
          let tasksMatch = true
          for (let i = 0; i < prevTasks.length; i++) {
            if (prevTasks[i]?.status !== nextTasks[i]?.status) {
              tasksMatch = false
              break
            }
          }
          if (tasksMatch) return state
        }
        return {
          currentExecution: execution,
          executions: state.executions.map((e) => (e.id === id ? execution : e)),
        }
      })
    } catch (err) {
      console.warn('[poll] execution fetch failed:', getErrorMessage(err, 'unknown error'))
    }
  },

  pollExecutions: async (crewName?: string, pagination?: PaginationParams) => {
    try {
      const result = await api.get<{ items: Execution[]; total: number }>(
        executionsPath(crewName, pagination),
      )
      set((state) => {
        const prev = state.executions
        if (prev.length === 0) return { executions: result.items, executionsTotal: result.total }
        const prevById = new Map(prev.map((e) => [e.id, e]))
        let changed = prev.length !== result.items.length
        const merged = result.items.map((item) => {
          const existing = prevById.get(item.id)
          if (
            existing &&
            existing.status === item.status &&
            existing.total_tokens === item.total_tokens
          ) {
            return existing
          }
          changed = true
          return item
        })
        return changed
          ? { executions: merged, executionsTotal: result.total }
          : { ...state, executionsTotal: result.total }
      })
    } catch (err) {
      console.warn('[poll] executions fetch failed:', getErrorMessage(err, 'unknown error'))
    }
  },

  addEvents: (newEvents: ExecutionEvent[]) => {
    set((state) => {
      if (newEvents.length === 0) return state
      const lastSeq = state.events.at(-1)?.sequence ?? -1
      const unique = newEvents.filter((e) => e.sequence > lastSeq)
      if (unique.length === 0) return state
      let merged = state.events.concat(unique)
      if (merged.length > MAX_EVENTS) {
        merged = merged.slice(merged.length - MAX_EVENTS)
      }
      return { events: merged }
    })
  },

  clearEvents: () => {
    set({ events: [] })
  },

  fetchEvents: async (id: string, after?: number) => {
    const evts = get().events
    const lastSeq = after ?? evts.at(-1)?.sequence ?? -1
    try {
      const result = await api.get<{ events: ExecutionEvent[]; next_sequence: number }>(
        `/api/v1/executions/${id}/events?after=${lastSeq}&limit=${EVENTS_FETCH_LIMIT}`,
      )
      get().addEvents(result.events)
    } catch (err) {
      console.warn('[poll] events fetch failed:', getErrorMessage(err, 'unknown error'))
    }
  },

  fetchSpend: async (id: string) => {
    try {
      const result = await api.get<Record<string, unknown>>(`/api/v1/executions/${id}/spend`)
      set({ spendData: result })
    } catch (err) {
      console.warn('[poll] spend fetch failed:', getErrorMessage(err, 'unknown error'))
      set({ spendData: null })
    }
  },
}))
