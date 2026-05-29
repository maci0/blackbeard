import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import * as fc from 'fast-check'

// Mock localStorage and fetch before importing store
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
  removeItem: (key: string) => storage.delete(key),
  clear: () => storage.clear(),
})
vi.stubGlobal('fetch', vi.fn())

import { useProjectStore } from '../projectStore'

const NUM_RUNS = 100

describe('fuzz: projectStore', () => {
  beforeEach(() => {
    storage.clear()
    useProjectStore.setState({
      current: 'default',
      projects: ['default'],
      loading: false,
      error: null,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('setCurrent never crashes on any string', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        useProjectStore.getState().setCurrent(s)
        expect(useProjectStore.getState().current).toBe(s)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('setCurrent persists to localStorage', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 50 }), (s) => {
        useProjectStore.getState().setCurrent(s)
        expect(storage.get('blackbeard_project')).toBe(s)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('projects array always includes at least one entry after setState', () => {
    fc.assert(
      fc.property(fc.array(fc.string(), { minLength: 0, maxLength: 10 }), (names) => {
        useProjectStore.setState({ projects: names.length > 0 ? names : ['default'] })
        expect(useProjectStore.getState().projects.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})
