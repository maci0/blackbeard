import { create } from 'zustand'
import { api } from '@/api/client'
import type { Resource } from '@/lib/types'
import { STORAGE_KEYS } from '@/lib/utils'

interface NamespaceState {
  current: string
  namespaces: string[]
  loading: boolean
  error: string | null
  setCurrent: (ns: string) => void
  fetchNamespaces: () => Promise<void>
  createNamespace: (name: string) => Promise<void>
}

export const useNamespaceStore = create<NamespaceState>((set, get) => ({
  current: localStorage.getItem(STORAGE_KEYS.NAMESPACE) ?? 'default',
  namespaces: ['default'],
  loading: false,
  error: null,

  setCurrent: (ns: string) => {
    localStorage.setItem(STORAGE_KEYS.NAMESPACE, ns)
    set({ current: ns })
  },

  fetchNamespaces: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
    try {
      const result = await api.get<{ items: Resource[]; total: number }>('/api/v1/namespaces')
      const names = result.items.map((r) => r.metadata.name)
      if (!names.includes('default')) {
        names.unshift('default')
      }
      set({ namespaces: names, loading: false })
    } catch {
      set({ loading: false, error: 'Failed to load namespaces' })
    }
  },

  createNamespace: async (name: string) => {
    await api.post<Resource>('/api/v1/namespaces', {
      apiVersion: 'blackbeard/v1',
      kind: 'Namespace',
      metadata: { name, namespace: 'default' },
      spec: {},
    })
    const names = [...get().namespaces]
    if (!names.includes(name)) {
      names.push(name)
    }
    set({ namespaces: names })
  },
}))
