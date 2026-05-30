import { create } from 'zustand'
import { api, ApiError } from '@/api/client'
import { getErrorMessage } from '@/lib/utils'

export interface User {
  id: string
  email: string
  display_name: string
  is_active: boolean
  created_at: string
}

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  loading: boolean
  error: string | null
  sessionExpired: boolean

  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  fetchMe: () => Promise<void>
  hydrate: () => void
  setSessionExpired: (v: boolean) => void
}

export const TOKEN_KEY = 'blackbeard_token'
export const REFRESH_KEY = 'blackbeard_refresh_token'

function applyAuthResult(
  result: { access_token: string; refresh_token: string; user: User },
  set: (state: Partial<AuthState>) => void,
) {
  localStorage.setItem(TOKEN_KEY, result.access_token)
  localStorage.setItem(REFRESH_KEY, result.refresh_token)
  api.setToken(result.access_token)
  set({
    token: result.access_token,
    refreshToken: result.refresh_token,
    user: result.user,
    loading: false,
  })
}

let _initialToken: string | null = null
let _initialRefresh: string | null = null
try {
  _initialToken = localStorage.getItem(TOKEN_KEY)
  _initialRefresh = localStorage.getItem(REFRESH_KEY)
  if (_initialToken) api.setToken(_initialToken)
} catch {
  // localStorage unavailable (test env, private browsing, or storage disabled)
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: _initialToken,
  refreshToken: _initialRefresh,
  loading: false,
  error: null,
  sessionExpired: false,

  hydrate: () => {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored) {
      api.setToken(stored)
      set({ token: stored })
    }
    const storedRefresh = localStorage.getItem(REFRESH_KEY)
    if (storedRefresh) {
      set({ refreshToken: storedRefresh })
    }
  },

  login: async (email: string, password: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.post<{ access_token: string; refresh_token: string; user: User }>(
        '/api/v1/auth/login',
        { email, password },
      )
      applyAuthResult(result, set)
    } catch (err) {
      const message = getErrorMessage(err, 'Login failed')
      set({ error: message, loading: false })
      throw err
    }
  },

  register: async (email: string, password: string, displayName: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.post<{ access_token: string; refresh_token: string; user: User }>(
        '/api/v1/auth/register',
        { email, password, display_name: displayName },
      )
      applyAuthResult(result, set)
    } catch (err) {
      const message = getErrorMessage(err, 'Registration failed')
      set({ error: message, loading: false })
      throw err
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    api.setToken('')
    set({ user: null, token: null, refreshToken: null, error: null, sessionExpired: false })
  },

  setSessionExpired: (v: boolean) => {
    if (v) {
      get().logout()
      window.location.href = '/login'
      return
    }
    set({ sessionExpired: v })
  },

  refresh: async () => {
    const currentRefresh = get().refreshToken
    if (!currentRefresh) {
      get().logout()
      return
    }
    try {
      const result = await api.post<{
        access_token: string
        refresh_token?: string
      }>('/api/v1/auth/refresh', {
        refresh_token: currentRefresh,
      })
      localStorage.setItem(TOKEN_KEY, result.access_token)
      api.setToken(result.access_token)
      if (result.refresh_token) {
        localStorage.setItem(REFRESH_KEY, result.refresh_token)
        set({ token: result.access_token, refreshToken: result.refresh_token })
      } else {
        set({ token: result.access_token })
      }
    } catch {
      console.warn('[auth] token refresh failed')
      get().logout()
    }
  },

  fetchMe: async () => {
    if (!get().token) return
    set({ loading: true })
    try {
      const user = await api.get<User>('/api/v1/auth/me')
      set({ user, loading: false })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        try {
          await get().refresh()
          if (get().token) {
            const user = await api.get<User>('/api/v1/auth/me')
            set({ user, loading: false })
            return
          }
        } catch {
          console.warn('[auth] token refresh failed, showing session expired dialog')
        }
        set({ sessionExpired: true })
      }
      set({ loading: false, error: null })
    }
  },
}))
