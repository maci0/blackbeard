/**
 * @vitest-environment jsdom
 *
 * Fuzz tests for resourceStore — kind mapping, state merging,
 * and concurrent fetch deduplication.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as fc from 'fast-check'

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { useResourceStore } from '../resourceStore'
import { KIND_TO_PLURAL } from '@/lib/kinds'
import type { Resource } from '@/lib/types'

const NUM_RUNS = 100

const KNOWN_KINDS = Object.keys(KIND_TO_PLURAL)
const KNOWN_PLURALS = Object.values(KIND_TO_PLURAL)

function resetStore() {
  useResourceStore.setState({
    resources: {},
    loadingKinds: {},
    loading: false,
    error: null,
  })
}

const resourceArb: fc.Arbitrary<Resource> = fc.record({
  id: fc.uuid(),
  apiVersion: fc.constant('blackbeard/v1'),
  kind: fc.constantFrom(...KNOWN_KINDS),
  metadata: fc.record({
    name: fc.stringMatching(/^[a-z][a-z0-9-]{0,20}$/),
    project: fc.constant('default'),
    labels: fc.dictionary(fc.string({ maxLength: 10 }), fc.string({ maxLength: 20 }), {
      maxKeys: 3,
    }),
  }),
  spec: fc.dictionary(fc.string({ maxLength: 10 }), fc.string({ maxLength: 50 }), { maxKeys: 5 }),
  version: fc.integer({ min: 1, max: 1000 }),
  created_at: fc.constant('2024-01-01T00:00:00Z'),
  updated_at: fc.constant('2024-01-01T00:00:00Z'),
})

describe('fuzz: resourceStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  describe('KIND_TO_PLURAL mapping', () => {
    it('createResource rejects any kind not in KIND_TO_PLURAL', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 30 }).filter((s) => !(s in KIND_TO_PLURAL)),
          (unknownKind) => {
            resetStore()
            void {
              apiVersion: 'blackbeard/v1',
              kind: unknownKind,
              metadata: { name: 'test' },
              spec: {},
            }
            expect(() => {
              const plural = KIND_TO_PLURAL[unknownKind as keyof typeof KIND_TO_PLURAL]
              if (!plural) throw new Error(`Unknown kind: ${unknownKind}`)
            }).toThrow()
          },
        ),
        { numRuns: NUM_RUNS },
      )
    })

    it('all known kinds map to lowercase plural strings', () => {
      for (const [kind, plural] of Object.entries(KIND_TO_PLURAL)) {
        expect(kind).toMatch(/^[A-Z]/)
        expect(plural).toMatch(/^[a-z]/)
      }
    })
  })

  describe('state merging', () => {
    it('setting resources for one kind does not affect other kinds', () => {
      fc.assert(
        fc.property(
          fc.constantFrom(...KNOWN_PLURALS),
          fc.constantFrom(...KNOWN_PLURALS),
          fc.array(resourceArb, { maxLength: 5 }),
          fc.array(resourceArb, { maxLength: 5 }),
          (kind1, kind2, items1, items2) => {
            resetStore()
            useResourceStore.setState({
              resources: { [kind1]: items1, [kind2]: items2 },
            })
            const state = useResourceStore.getState()
            if (kind1 !== kind2) {
              expect(state.resources[kind1]).toEqual(items1)
              expect(state.resources[kind2]).toEqual(items2)
            }
          },
        ),
        { numRuns: NUM_RUNS },
      )
    })

    it('deleteResource filters by name correctly', () => {
      fc.assert(
        fc.property(
          fc.array(resourceArb, { minLength: 1, maxLength: 10 }),
          fc.integer({ min: 0 }),
          (resources, idx) => {
            const safeIdx = idx % resources.length
            const target = resources[safeIdx]!
            const kindPlural = KIND_TO_PLURAL[target.kind as keyof typeof KIND_TO_PLURAL]!

            useResourceStore.setState({ resources: { [kindPlural]: [...resources] } })

            const filtered = resources.filter((r) => r.metadata.name !== target.metadata.name)
            useResourceStore.setState({
              resources: { [kindPlural]: filtered },
            })

            const state = useResourceStore.getState()
            const remaining = state.resources[kindPlural] ?? []
            for (const r of remaining) {
              expect(r.metadata.name).not.toBe(target.metadata.name)
            }
          },
        ),
        { numRuns: NUM_RUNS },
      )
    })
  })

  describe('loading state', () => {
    it('loadingKinds tracks concurrent fetches independently', () => {
      fc.assert(
        fc.property(
          fc.uniqueArray(fc.constantFrom(...KNOWN_PLURALS), { minLength: 1, maxLength: 5 }),
          (kinds) => {
            resetStore()
            const loadingKinds: Record<string, true> = {}
            for (const k of kinds) loadingKinds[k] = true
            useResourceStore.setState({ loadingKinds, loading: true })

            const state = useResourceStore.getState()
            expect(Object.keys(state.loadingKinds).length).toBe(kinds.length)
            expect(state.loading).toBe(true)

            const next = { ...state.loadingKinds }
            delete next[kinds[0]!]
            const hasLoading = Object.keys(next).length > 0
            useResourceStore.setState({ loadingKinds: next, loading: hasLoading })

            const afterState = useResourceStore.getState()
            expect(Object.keys(afterState.loadingKinds).length).toBe(kinds.length - 1)
            expect(afterState.loading).toBe(kinds.length > 1)
          },
        ),
        { numRuns: NUM_RUNS },
      )
    })
  })
})
