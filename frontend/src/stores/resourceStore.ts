import { create } from 'zustand'
import { api } from '@/api/client'
import { KIND_TO_PLURAL, ALL_PLURALS } from '@/lib/kinds'

export interface Resource {
  id: string
  apiVersion: string
  kind: string
  metadata: {
    name: string
    namespace: string
    labels: Record<string, string>
  }
  spec: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

interface ResourceState {
  resources: Record<string, Resource[]>
  loading: boolean
  error: string | null

  fetchResources: (kindPlural: string) => Promise<void>
  fetchAllResources: () => Promise<void>
  createResource: (resource: {
    apiVersion: string
    kind: string
    metadata: { name: string; namespace?: string; labels?: Record<string, string> }
    spec: Record<string, unknown>
  }) => Promise<Resource>
  updateResource: (
    kindPlural: string,
    name: string,
    data: {
      spec?: Record<string, unknown>
      metadata?: { name: string; namespace?: string; labels?: Record<string, string> }
      version: number
    },
  ) => Promise<Resource>
  deleteResource: (kindPlural: string, name: string) => Promise<void>
}


export const useResourceStore = create<ResourceState>((set) => ({
  resources: {},
  loading: false,
  error: null,

  fetchResources: async (kindPlural: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.get<{ items: Resource[]; total: number }>(
        `/api/v1/${kindPlural}`,
      )
      set((state) => ({
        resources: { ...state.resources, [kindPlural]: result.items },
        loading: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  fetchAllResources: async () => {
    set({ loading: true, error: null })
    try {
      const results = await Promise.allSettled(
        ALL_PLURALS.map((kind) =>
          api
            .get<{ items: Resource[]; total: number }>(`/api/v1/${kind}`)
            .then((r) => ({ kind, items: r.items })),
        ),
      )
      const updated: Record<string, Resource[]> = {}
      for (const result of results) {
        if (result.status === 'fulfilled') {
          updated[result.value.kind] = result.value.items
        }
      }
      set((state) => ({
        resources: { ...state.resources, ...updated },
        loading: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  createResource: async (resource) => {
    const kindPlural = KIND_TO_PLURAL[resource.kind]
    if (!kindPlural) throw new Error(`Unknown kind: ${resource.kind}`)
    const created = await api.post<Resource>(`/api/v1/${kindPlural}`, resource)
    set((state) => {
      const existing = state.resources[kindPlural] || []
      const idx = existing.findIndex((r) => r.id === created.id)
      const updated =
        idx >= 0
          ? existing.map((r, i) => (i === idx ? created : r))
          : [...existing, created]
      return { resources: { ...state.resources, [kindPlural]: updated } }
    })
    return created
  },

  updateResource: async (kindPlural, name, data) => {
    const updated = await api.put<Resource>(`/api/v1/${kindPlural}/${name}`, data)
    set((state) => ({
      resources: {
        ...state.resources,
        [kindPlural]: (state.resources[kindPlural] || []).map((r) =>
          r.metadata.name === name ? updated : r,
        ),
      },
    }))
    return updated
  },

  deleteResource: async (kindPlural, name) => {
    await api.delete<void>(`/api/v1/${kindPlural}/${name}`)
    set((state) => ({
      resources: {
        ...state.resources,
        [kindPlural]: (state.resources[kindPlural] || []).filter(
          (r) => r.metadata.name !== name,
        ),
      },
    }))
  },
}))
