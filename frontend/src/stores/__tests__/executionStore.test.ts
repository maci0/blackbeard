/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useExecutionStore } from '../executionStore'
import { api } from '@/api/client'
import type { Execution, ExecutionEvent } from '@/lib/types'

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
}

function makeExecution(overrides: Partial<Execution> = {}): Execution {
  return {
    id: 'exec-1',
    crew_name: 'test-crew',
    crew_namespace: 'default',
    execution_type: 'kickoff',
    status: 'running',
    n_iterations: null,
    training_file: null,
    inputs: {},
    outputs: null,
    error: null,
    total_tokens: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    cost_usd: 0,
    created_at: '2024-01-01T00:00:00Z',
    started_at: '2024-01-01T00:00:01Z',
    completed_at: null,
    tasks: undefined,
    ...overrides,
  }
}

function resetStore() {
  useExecutionStore.setState({
    executions: [],
    currentExecution: null,
    events: [],
    spendData: null,
    loading: false,
    error: null,
  })
}

describe('executionStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  describe('fetchExecutions', () => {
    it('populates items on success', async () => {
      const items = [makeExecution({ id: 'e1' }), makeExecution({ id: 'e2' })]
      mockApi.get.mockResolvedValueOnce({ items, total: 2 })

      await useExecutionStore.getState().fetchExecutions()

      const state = useExecutionStore.getState()
      expect(state.executions).toHaveLength(2)
      expect(state.executions[0]!.id).toBe('e1')
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/executions')
    })

    it('filters by crew name when provided', async () => {
      mockApi.get.mockResolvedValueOnce({ items: [], total: 0 })

      await useExecutionStore.getState().fetchExecutions('my-crew')

      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/executions?crew_name=my-crew')
    })

    it('sets error on failure', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Server down'))

      await useExecutionStore.getState().fetchExecutions()

      const state = useExecutionStore.getState()
      expect(state.error).toBe('Server down')
      expect(state.loading).toBe(false)
    })

    it('sets loading while request is in progress', async () => {
      let resolveGet: (value: unknown) => void
      const getPromise = new Promise((resolve) => {
        resolveGet = resolve
      })
      mockApi.get.mockReturnValueOnce(getPromise)

      const fetchPromise = useExecutionStore.getState().fetchExecutions()

      expect(useExecutionStore.getState().loading).toBe(true)

      resolveGet!({ items: [], total: 0 })
      await fetchPromise

      expect(useExecutionStore.getState().loading).toBe(false)
    })
  })

  describe('fetchExecution', () => {
    it('sets current execution on success', async () => {
      const exec = makeExecution({ id: 'exec-42', status: 'completed' })
      mockApi.get.mockResolvedValueOnce(exec)

      await useExecutionStore.getState().fetchExecution('exec-42')

      const state = useExecutionStore.getState()
      expect(state.currentExecution).toEqual(exec)
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/executions/exec-42')
    })

    it('clears currentExecution when loading a different id', async () => {
      const oldExec = makeExecution({ id: 'exec-old' })
      useExecutionStore.setState({ currentExecution: oldExec })

      let resolveGet: (value: unknown) => void
      const getPromise = new Promise((resolve) => {
        resolveGet = resolve
      })
      mockApi.get.mockReturnValueOnce(getPromise)

      const fetchPromise = useExecutionStore.getState().fetchExecution('exec-new')

      // Should clear current because different id
      expect(useExecutionStore.getState().currentExecution).toBeNull()

      resolveGet!(makeExecution({ id: 'exec-new' }))
      await fetchPromise
    })

    it('keeps currentExecution when reloading the same id', async () => {
      const existing = makeExecution({ id: 'exec-same', status: 'running' })
      useExecutionStore.setState({ currentExecution: existing })

      let resolveGet: (value: unknown) => void
      const getPromise = new Promise((resolve) => {
        resolveGet = resolve
      })
      mockApi.get.mockReturnValueOnce(getPromise)

      const fetchPromise = useExecutionStore.getState().fetchExecution('exec-same')

      // Should NOT clear because same id
      expect(useExecutionStore.getState().currentExecution).toEqual(existing)

      resolveGet!(makeExecution({ id: 'exec-same', status: 'completed' }))
      await fetchPromise
    })

    it('sets error on failure', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Not found'))

      await useExecutionStore.getState().fetchExecution('nonexistent')

      const state = useExecutionStore.getState()
      expect(state.error).toBe('Not found')
      expect(state.loading).toBe(false)
    })
  })

  describe('pollExecution', () => {
    it('updates status when execution changes', async () => {
      const initial = makeExecution({ id: 'exec-1', status: 'running', total_tokens: 0 })
      useExecutionStore.setState({ currentExecution: initial, executions: [initial] })

      const updated = makeExecution({ id: 'exec-1', status: 'completed', total_tokens: 500 })
      mockApi.get.mockResolvedValueOnce(updated)

      await useExecutionStore.getState().pollExecution('exec-1')

      const state = useExecutionStore.getState()
      expect(state.currentExecution?.status).toBe('completed')
      expect(state.currentExecution?.total_tokens).toBe(500)
    })

    it('does not update state when execution is unchanged', async () => {
      const exec = makeExecution({ id: 'exec-1', status: 'running', total_tokens: 100, tasks: [] })
      useExecutionStore.setState({ currentExecution: exec, executions: [exec] })

      // Return identical data
      mockApi.get.mockResolvedValueOnce({ ...exec, tasks: [] })

      // Get a reference to the state before poll
      const stateBefore = useExecutionStore.getState()

      await useExecutionStore.getState().pollExecution('exec-1')

      const stateAfter = useExecutionStore.getState()
      // API should still have been called even though state didn't change
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/executions/exec-1')
      // State reference should be the same (no unnecessary re-render)
      expect(stateAfter.currentExecution).toBe(stateBefore.currentExecution)
    })

    it('handles undefined tasks array (the tasks?.length bug fix)', async () => {
      // Execution with no tasks defined at all
      const exec = makeExecution({ id: 'exec-1', status: 'running', tasks: undefined })
      useExecutionStore.setState({ currentExecution: exec, executions: [exec] })

      // Server returns execution also with undefined tasks
      const polled = makeExecution({ id: 'exec-1', status: 'running', tasks: undefined })
      mockApi.get.mockResolvedValueOnce(polled)

      // Should not throw
      await useExecutionStore.getState().pollExecution('exec-1')

      expect(useExecutionStore.getState().currentExecution?.status).toBe('running')
    })

    it('detects change when tasks array grows', async () => {
      const exec = makeExecution({
        id: 'exec-1',
        status: 'running',
        tasks: [
          {
            id: 't1',
            task_name: 'research',
            agent_name: 'researcher',
            order: 0,
            status: 'running',
            output: null,
            error: null,
            tokens_used: 0,
            cost_usd: 0,
            started_at: null,
            completed_at: null,
          },
        ],
      })
      useExecutionStore.setState({ currentExecution: exec, executions: [exec] })

      const updated = makeExecution({
        id: 'exec-1',
        status: 'running',
        tasks: [
          {
            id: 't1',
            task_name: 'research',
            agent_name: 'researcher',
            order: 0,
            status: 'completed',
            output: 'done',
            error: null,
            tokens_used: 100,
            cost_usd: 0.01,
            started_at: '2024-01-01',
            completed_at: '2024-01-02',
          },
          {
            id: 't2',
            task_name: 'write',
            agent_name: 'writer',
            order: 1,
            status: 'running',
            output: null,
            error: null,
            tokens_used: 0,
            cost_usd: 0,
            started_at: '2024-01-02',
            completed_at: null,
          },
        ],
      })
      mockApi.get.mockResolvedValueOnce(updated)

      await useExecutionStore.getState().pollExecution('exec-1')

      expect(useExecutionStore.getState().currentExecution?.tasks).toHaveLength(2)
    })

    it('also updates the executions list', async () => {
      const exec = makeExecution({ id: 'exec-1', status: 'running' })
      useExecutionStore.setState({ currentExecution: exec, executions: [exec] })

      const updated = makeExecution({ id: 'exec-1', status: 'completed' })
      mockApi.get.mockResolvedValueOnce(updated)

      await useExecutionStore.getState().pollExecution('exec-1')

      const state = useExecutionStore.getState()
      expect(state.executions[0]!.status).toBe('completed')
    })
  })

  describe('kickoff', () => {
    it('adds new execution to the front of the list', async () => {
      const existing = makeExecution({ id: 'old-exec' })
      useExecutionStore.setState({ executions: [existing] })

      const newExec = makeExecution({ id: 'new-exec', status: 'pending' })
      mockApi.post.mockResolvedValueOnce(newExec)

      const result = await useExecutionStore.getState().kickoff('my-crew', { topic: 'AI' })

      expect(result).toEqual(newExec)
      const state = useExecutionStore.getState()
      expect(state.executions).toHaveLength(2)
      expect(state.executions[0]!.id).toBe('new-exec')
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/crews/my-crew/kickoff', {
        inputs: { topic: 'AI' },
      })
    })
  })

  describe('cancelExecution', () => {
    it('updates execution status in both lists', async () => {
      const exec = makeExecution({ id: 'exec-1', status: 'running' })
      useExecutionStore.setState({ currentExecution: exec, executions: [exec] })

      const cancelled = makeExecution({ id: 'exec-1', status: 'cancelled' })
      mockApi.patch.mockResolvedValueOnce(cancelled)

      await useExecutionStore.getState().cancelExecution('exec-1')

      const state = useExecutionStore.getState()
      expect(state.currentExecution?.status).toBe('cancelled')
      expect(state.executions[0]!.status).toBe('cancelled')
      expect(mockApi.patch).toHaveBeenCalledWith('/api/v1/executions/exec-1/cancel')
    })
  })

  describe('addEvents', () => {
    it('appends new events by sequence', () => {
      const event1: ExecutionEvent = {
        sequence: 1,
        event_type: 'task_started',
        timestamp: '2024-01-01T00:00:01Z',
        data: {},
      }
      useExecutionStore.setState({ events: [event1] })

      const event2: ExecutionEvent = {
        sequence: 2,
        event_type: 'task_completed',
        timestamp: '2024-01-01T00:00:02Z',
        data: {},
      }

      useExecutionStore.getState().addEvents([event2])

      expect(useExecutionStore.getState().events).toHaveLength(2)
    })

    it('skips duplicate events with same or lower sequence', () => {
      const event1: ExecutionEvent = {
        sequence: 5,
        event_type: 'task_started',
        timestamp: '2024-01-01T00:00:01Z',
        data: {},
      }
      useExecutionStore.setState({ events: [event1] })

      const duplicate: ExecutionEvent = {
        sequence: 3,
        event_type: 'old_event',
        timestamp: '2024-01-01T00:00:00Z',
        data: {},
      }

      useExecutionStore.getState().addEvents([duplicate])

      expect(useExecutionStore.getState().events).toHaveLength(1)
    })

    it('does not update state for empty events array', () => {
      const stateBefore = useExecutionStore.getState()

      useExecutionStore.getState().addEvents([])

      expect(useExecutionStore.getState()).toBe(stateBefore)
    })
  })

  describe('clearEvents', () => {
    it('empties the events array', () => {
      const event: ExecutionEvent = {
        sequence: 1,
        event_type: 'test',
        timestamp: '2024-01-01',
        data: {},
      }
      useExecutionStore.setState({ events: [event] })

      useExecutionStore.getState().clearEvents()

      expect(useExecutionStore.getState().events).toEqual([])
    })
  })

  describe('pollExecutions', () => {
    it('merges updated executions preserving unchanged references', async () => {
      const exec1 = makeExecution({ id: 'e1', status: 'running', total_tokens: 10 })
      const exec2 = makeExecution({ id: 'e2', status: 'completed', total_tokens: 200 })
      useExecutionStore.setState({ executions: [exec1, exec2] })

      // e1 changed status, e2 unchanged
      const updatedExec1 = makeExecution({ id: 'e1', status: 'completed', total_tokens: 100 })
      mockApi.get.mockResolvedValueOnce({ items: [updatedExec1, exec2], total: 2 })

      await useExecutionStore.getState().pollExecutions()

      const state = useExecutionStore.getState()
      expect(state.executions[0]!.status).toBe('completed')
      // Unchanged execution should preserve reference
      expect(state.executions[1]).toBe(exec2)
    })

    it('does not fail on API error', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Poll failed'))

      // Should not throw
      await useExecutionStore.getState().pollExecutions()

      // State unchanged
      expect(useExecutionStore.getState().executions).toEqual([])
    })
  })
})
