import { create } from 'zustand'
import { api } from '@/api/client'
import type { Resource } from '@/lib/types'
import { STORAGE_KEYS } from '@/lib/utils'

interface ProjectState {
  current: string
  projects: string[]
  loading: boolean
  error: string | null
  setCurrent: (ns: string) => void
  fetchProjects: () => Promise<void>
  createProject: (name: string) => Promise<void>
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  current: localStorage.getItem(STORAGE_KEYS.PROJECT) ?? 'default',
  projects: ['default'],
  loading: false,
  error: null,

  setCurrent: (ns: string) => {
    localStorage.setItem(STORAGE_KEYS.PROJECT, ns)
    set({ current: ns })
  },

  fetchProjects: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
    try {
      const result = await api.get<{ items: Resource[]; total: number }>('/api/v1/projects')
      const names = result.items.map((r) => r.metadata.name)
      if (!names.includes('default')) {
        names.unshift('default')
      }
      set({ projects: names, loading: false })
    } catch (err) {
      console.error('[projects] Failed to load projects:', err)
      set({ loading: false, error: 'Failed to load projects' })
    }
  },

  createProject: async (name: string) => {
    await api.post<Resource>('/api/v1/projects', {
      apiVersion: 'blackbeard/v1',
      kind: 'Project',
      metadata: { name, project: 'default' },
      spec: {},
    })
    const names = [...get().projects]
    if (!names.includes(name)) {
      names.push(name)
    }
    set({ projects: names })
  },
}))
