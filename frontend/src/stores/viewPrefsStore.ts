import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type ViewMode = 'cards' | 'list'

const DEFAULTS: Record<string, ViewMode> = {
  models: 'cards',
  resources: 'list',
  executions: 'list',
  webhooks: 'list',
  knowledge: 'cards',
}

interface ViewPrefsState {
  views: Record<string, ViewMode>
  getView: (page: string) => ViewMode
  setView: (page: string, mode: ViewMode) => void
}

export const useViewPrefsStore = create<ViewPrefsState>()(
  persist(
    (set, get) => ({
      views: {},
      getView: (page: string) => get().views[page] ?? DEFAULTS[page] ?? 'list',
      setView: (page: string, mode: ViewMode) =>
        set((state) => ({ views: { ...state.views, [page]: mode } })),
    }),
    {
      name: 'blackbeard_view_prefs',
      storage: createJSONStorage(() => localStorage),
    },
  ),
)
