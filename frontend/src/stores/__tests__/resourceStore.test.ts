/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useResourceStore } from '../resourceStore'
import { api } from '@/api/client'

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

function resetStore() {
  useResourceStore.setState({
    resources: {},
    loadingKinds: new Set<string>(),
    loading: false,
    error: null,
  })
}

describe('resourceStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  describe('fetchResources', () => {
    it('sets items on success', async () => {
      const items = [
        {
          id: '1',
          apiVersion: 'blackbeard/v1',
          kind: 'Agent',
          metadata: { name: 'researcher', namespace: 'default', labels: {} },
          spec: { role: 'Researcher' },
          version: 1,
          created_at: '2024-01-01',
          updated_at: '2024-01-01',
        },
      ]
      mockApi.get.mockResolvedValueOnce({ items, total: 1 })

      await useResourceStore.getState().fetchResources('agents')

      const state = useResourceStore.getState()
      expect(state.resources['agents']).toEqual(items)
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/agents')
    })

    it('sets error on failure', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Network error'))

      await useResourceStore.getState().fetchResources('agents')

      const state = useResourceStore.getState()
      expect(state.error).toBe('Network error')
      expect(state.loading).toBe(false)
    })

    it('guards against duplicate fetches for same kind', async () => {
      let resolveFirst: (value: unknown) => void
      const firstPromise = new Promise((resolve) => {
        resolveFirst = resolve
      })
      mockApi.get.mockReturnValueOnce(firstPromise)

      const fetch1 = useResourceStore.getState().fetchResources('agents')

      // Second call for same kind should be a no-op
      const fetch2 = useResourceStore.getState().fetchResources('agents')

      resolveFirst!({ items: [], total: 0 })
      await fetch1
      await fetch2

      // Only one API call should have been made
      expect(mockApi.get).toHaveBeenCalledTimes(1)
    })

    it('allows fetches for different kinds concurrently', async () => {
      mockApi.get.mockResolvedValueOnce({ items: [], total: 0 })
      mockApi.get.mockResolvedValueOnce({ items: [], total: 0 })

      await Promise.all([
        useResourceStore.getState().fetchResources('agents'),
        useResourceStore.getState().fetchResources('tasks'),
      ])

      expect(mockApi.get).toHaveBeenCalledTimes(2)
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/agents')
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/tasks')
    })
  })

  describe('createResource', () => {
    it('adds created resource to items', async () => {
      const newResource = {
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'writer', namespace: 'default', labels: {} },
        spec: { role: 'Writer' },
      }
      const createdResource = {
        ...newResource,
        id: '2',
        version: 1,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }
      mockApi.post.mockResolvedValueOnce(createdResource)

      const result = await useResourceStore.getState().createResource(newResource)

      expect(result).toEqual(createdResource)
      const state = useResourceStore.getState()
      expect(state.resources['agents']).toContainEqual(createdResource)
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/agents', newResource)
    })

    it('throws for unknown kind', async () => {
      const badResource = {
        apiVersion: 'blackbeard/v1',
        kind: 'UnknownKind',
        metadata: { name: 'test' },
        spec: {},
      }

      await expect(useResourceStore.getState().createResource(badResource)).rejects.toThrow(
        'Unknown kind: UnknownKind',
      )
    })

    it('replaces existing resource with same id', async () => {
      const existing = {
        id: '1',
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'researcher', namespace: 'default', labels: {} },
        spec: { role: 'Researcher' },
        version: 1,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }
      useResourceStore.setState({ resources: { agents: [existing] } })

      const updated = { ...existing, spec: { role: 'Senior Researcher' }, version: 2 }
      mockApi.post.mockResolvedValueOnce(updated)

      await useResourceStore.getState().createResource({
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'researcher' },
        spec: { role: 'Senior Researcher' },
      })

      const state = useResourceStore.getState()
      expect(state.resources['agents']).toHaveLength(1)
      expect(state.resources['agents']![0]!.spec).toEqual({ role: 'Senior Researcher' })
    })
  })

  describe('deleteResource', () => {
    it('removes resource from items', async () => {
      const agent1 = {
        id: '1',
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'researcher', namespace: 'default', labels: {} },
        spec: {},
        version: 1,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }
      const agent2 = {
        id: '2',
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'writer', namespace: 'default', labels: {} },
        spec: {},
        version: 1,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }
      useResourceStore.setState({ resources: { agents: [agent1, agent2] } })
      mockApi.delete.mockResolvedValueOnce(undefined)

      await useResourceStore.getState().deleteResource('agents', 'researcher')

      const state = useResourceStore.getState()
      expect(state.resources['agents']).toHaveLength(1)
      expect(state.resources['agents']![0]!.metadata.name).toBe('writer')
      expect(mockApi.delete).toHaveBeenCalledWith('/api/v1/agents/researcher')
    })
  })

  describe('updateResource', () => {
    it('updates resource in items', async () => {
      const existing = {
        id: '1',
        apiVersion: 'blackbeard/v1',
        kind: 'Agent',
        metadata: { name: 'researcher', namespace: 'default', labels: {} },
        spec: { role: 'Researcher' },
        version: 1,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }
      useResourceStore.setState({ resources: { agents: [existing] } })

      const updated = { ...existing, spec: { role: 'Lead Researcher' }, version: 2 }
      mockApi.put.mockResolvedValueOnce(updated)

      const result = await useResourceStore.getState().updateResource('agents', 'researcher', {
        spec: { role: 'Lead Researcher' },
        version: 1,
      })

      expect(result).toEqual(updated)
      const state = useResourceStore.getState()
      expect(state.resources['agents']![0]!.spec).toEqual({ role: 'Lead Researcher' })
      expect(mockApi.put).toHaveBeenCalledWith('/api/v1/agents/researcher', {
        spec: { role: 'Lead Researcher' },
        version: 1,
      })
    })
  })
})
