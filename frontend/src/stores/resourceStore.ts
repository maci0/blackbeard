import { create } from 'zustand'
import { api } from '@/api/client'
import { KIND_TO_PLURAL, ALL_PLURALS } from '@/lib/kinds'
import type { Resource } from '@/lib/types'
import { getErrorMessage } from '@/lib/utils'

interface ResourceState {
  resources: Record<string, Resource[]>
  loadingKinds: Record<string, true>
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

export const useResourceStore = create<ResourceState>((set, get) => ({
  resources: {},
  loadingKinds: {},
  loading: false,
  error: null,

  fetchResources: async (kindPlural: string) => {
    if (get().loadingKinds[kindPlural]) return
    set((state) => {
      const next = { ...state.loadingKinds, [kindPlural]: true as const }
      return { loadingKinds: next, loading: true, error: null }
    })
    try {
      const result = await api.get<{ items: Resource[]; total: number }>(`/api/v1/${kindPlural}`)
      set((state) => {
        const next: Record<string, true> = { ...state.loadingKinds }
        delete next[kindPlural]
        const hasLoading = Object.keys(next).length > 0
        return {
          resources: { ...state.resources, [kindPlural]: result.items },
          loadingKinds: next,
          loading: hasLoading,
        }
      })
    } catch (err) {
      set((state) => {
        const next: Record<string, true> = { ...state.loadingKinds }
        delete next[kindPlural]
        const hasLoading = Object.keys(next).length > 0
        const message = getErrorMessage(err, 'Failed to fetch resources')
        return { error: message, loadingKinds: next, loading: hasLoading }
      })
    }
  },

  fetchAllResources: async () => {
    set((state) => {
      const next = { ...state.loadingKinds }
      for (const k of ALL_PLURALS) next[k] = true
      return { loadingKinds: next, loading: true, error: null }
    })
    const results = await Promise.allSettled(
      ALL_PLURALS.map((kind) =>
        api
          .get<{ items: Resource[]; total: number }>(`/api/v1/${kind}`)
          .then((r) => ({ kind, items: r.items })),
      ),
    )
    const updated: Record<string, Resource[]> = {}
    const failedKinds: string[] = []
    for (const result of results) {
      if (result.status === 'fulfilled') {
        updated[result.value.kind] = result.value.items
      } else {
        failedKinds.push(result.reason instanceof Error ? result.reason.message : 'fetch failed')
      }
    }
    set((state) => {
      const next = { ...state.loadingKinds }
      for (const k of ALL_PLURALS) delete next[k]
      const hasLoading = Object.keys(next).length > 0
      return {
        resources: { ...state.resources, ...updated },
        loadingKinds: next,
        loading: hasLoading,
        error: failedKinds.length > 0 ? `Failed to load some resources: ${failedKinds[0]}` : null,
      }
    })
  },

  createResource: async (resource) => {
    const kindPlural = KIND_TO_PLURAL[resource.kind]
    if (!kindPlural) throw new Error(`Unknown kind: ${resource.kind}`)
    const created = await api.post<Resource>(`/api/v1/${kindPlural}`, resource)
    set((state) => {
      const existing = state.resources[kindPlural] || []
      const idx = existing.findIndex((r) => r.id === created.id)
      const updated =
        idx >= 0 ? existing.map((r, i) => (i === idx ? created : r)) : [...existing, created]
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
        [kindPlural]: (state.resources[kindPlural] || []).filter((r) => r.metadata.name !== name),
      },
    }))
  },
}))
