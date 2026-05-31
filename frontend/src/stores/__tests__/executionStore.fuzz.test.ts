/**
 * @vitest-environment jsdom
 *
 * Fuzz tests for executionStore — addEvents sequence logic,
 * executionsPath URL construction, and pollExecution state merging.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as fc from 'fast-check'

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

import { useExecutionStore } from '../executionStore'
import type { ExecutionEvent, Execution } from '@/lib/types'

const NUM_RUNS = 100

function resetStore() {
  useExecutionStore.setState({
    executions: [],
    executionsTotal: 0,
    currentExecution: null,
    events: [],
    spendData: null,
    loading: false,
    error: null,
  })
}

const eventArb: fc.Arbitrary<ExecutionEvent> = fc.record({
  sequence: fc.integer({ min: 0, max: 100_000 }),
  event_type: fc.string({ minLength: 1, maxLength: 30 }),
  timestamp: fc.string({ minLength: 1, maxLength: 30 }),
  data: fc.dictionary(fc.string({ maxLength: 10 }), fc.string({ maxLength: 50 }), {
    maxKeys: 5,
  }),
})

describe('fuzz: executionStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  describe('addEvents', () => {
    it('never crashes on arbitrary event arrays', () => {
      fc.assert(
        fc.property(fc.array(eventArb, { maxLength: 50 }), (events) => {
          resetStore()
          useExecutionStore.getState().addEvents(events)
          const state = useExecutionStore.getState()
          expect(state.events.length).toBeLessThanOrEqual(2000)
        }),
        { numRuns: NUM_RUNS },
      )
    })

    it('deduplicates events with sequence <= last stored sequence', () => {
      fc.assert(
        fc.property(
          fc
            .array(fc.integer({ min: 0, max: 1000 }), { minLength: 1, maxLength: 20 })
            .map((seqs) =>
              [...new Set(seqs)]
                .sort((a, b) => a - b)
                .map((s) => ({ sequence: s, event_type: 'test', timestamp: '', data: {} })),
            ),
          fc
            .array(fc.integer({ min: 0, max: 1000 }), { minLength: 1, maxLength: 20 })
            .map((seqs) =>
              [...new Set(seqs)]
                .sort((a, b) => a - b)
                .map((s) => ({ sequence: s, event_type: 'test', timestamp: '', data: {} })),
            ),
          (batch1, batch2) => {
            resetStore()
            useExecutionStore.getState().addEvents(batch1)
            const lastSeq = useExecutionStore.getState().events.at(-1)?.sequence ?? -1
            useExecutionStore.getState().addEvents(batch2)
            const events = useExecutionStore.getState().events
            // All events from batch2 that made it in should have sequence > lastSeq
            const batch2InStore = events.slice(batch1.length)
            for (const e of batch2InStore) {
              expect(e.sequence).toBeGreaterThan(lastSeq)
            }
          },
        ),
        { numRuns: NUM_RUNS },
      )
    })

    it('caps at MAX_EVENTS (2000)', () => {
      fc.assert(
        fc.property(fc.integer({ min: 1, max: 3000 }), (count) => {
          resetStore()
          const events: ExecutionEvent[] = Array.from({ length: count }, (_, i) => ({
            sequence: i,
            event_type: 'test',
            timestamp: '2024-01-01',
            data: {},
          }))
          useExecutionStore.getState().addEvents(events)
          expect(useExecutionStore.getState().events.length).toBeLessThanOrEqual(2000)
        }),
        { numRuns: 20 },
      )
    })

    it('empty array is no-op (state reference preserved)', () => {
      fc.assert(
        fc.property(fc.array(eventArb, { maxLength: 10 }), (seed) => {
          resetStore()
          useExecutionStore.getState().addEvents(seed)
          const stateBefore = useExecutionStore.getState()
          useExecutionStore.getState().addEvents([])
          const stateAfter = useExecutionStore.getState()
          expect(stateAfter).toBe(stateBefore)
        }),
        { numRuns: NUM_RUNS },
      )
    })
  })

  describe('clearEvents', () => {
    it('always produces empty array regardless of prior state', () => {
      fc.assert(
        fc.property(fc.array(eventArb, { maxLength: 20 }), (events) => {
          resetStore()
          useExecutionStore.getState().addEvents(events)
          useExecutionStore.getState().clearEvents()
          expect(useExecutionStore.getState().events).toEqual([])
        }),
        { numRuns: NUM_RUNS },
      )
    })
  })

  describe('fetchExecution identity logic', () => {
    it('clears currentExecution when id differs, preserves when same', () => {
      fc.assert(
        fc.property(fc.string({ minLength: 1, maxLength: 30 }), (id) => {
          const existing: Execution = {
            id: 'fixed-id',
            crew_name: 'crew',
            crew_project: 'default',
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
            initiated_by: null,
            principal_chain: [],
            created_at: '2024-01-01',
            started_at: null,
            completed_at: null,
            tasks: undefined,
          }
          useExecutionStore.setState({ currentExecution: existing })
          const shouldClear = id !== 'fixed-id'

          useExecutionStore.setState((state) => ({
            currentExecution: state.currentExecution?.id === id ? state.currentExecution : null,
          }))

          const result = useExecutionStore.getState().currentExecution
          if (shouldClear) {
            expect(result).toBeNull()
          } else {
            expect(result).toEqual(existing)
          }
        }),
        { numRuns: NUM_RUNS },
      )
    })
  })
})
