import { create } from 'zustand'
import { api, ApiError } from '@/api/client'

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
  loading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName: string) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
  fetchMe: () => Promise<void>
  hydrate: () => void
}

const TOKEN_KEY = 'blackbeard_token'

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  loading: false,
  error: null,

  hydrate: () => {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored) {
      api.setToken(stored)
      set({ token: stored })
    }
  },

  login: async (email: string, password: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.post<{ access_token: string; user: User }>('/api/v1/auth/login', {
        email,
        password,
      })
      localStorage.setItem(TOKEN_KEY, result.access_token)
      api.setToken(result.access_token)
      set({ token: result.access_token, user: result.user, loading: false })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Login failed'
      set({ error: message, loading: false })
      throw err
    }
  },

  register: async (email: string, password: string, displayName: string) => {
    set({ loading: true, error: null })
    try {
      const result = await api.post<{ access_token: string; user: User }>('/api/v1/auth/register', {
        email,
        password,
        display_name: displayName,
      })
      localStorage.setItem(TOKEN_KEY, result.access_token)
      api.setToken(result.access_token)
      set({ token: result.access_token, user: result.user, loading: false })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Registration failed'
      set({ error: message, loading: false })
      throw err
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    api.setToken('')
    set({ user: null, token: null, error: null })
  },

  refreshToken: async () => {
    try {
      const result = await api.post<{ access_token: string }>('/api/v1/auth/refresh', {})
      localStorage.setItem(TOKEN_KEY, result.access_token)
      api.setToken(result.access_token)
      set({ token: result.access_token })
    } catch {
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
        get().logout()
      }
      set({ loading: false })
    }
  },
}))
