/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAuthStore } from '../authStore'
import { api, ApiError } from '@/api/client'

vi.mock('@/api/client', () => {
  const ApiError = class ApiError extends Error {
    status: number
    detail: unknown
    requestId?: string
    constructor(message: string, status: number, detail: unknown, requestId?: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.detail = detail
      this.requestId = requestId
    }
  }
  return {
    ApiError,
    api: {
      setToken: vi.fn(),
      getToken: vi.fn(),
      post: vi.fn(),
      get: vi.fn(),
    },
  }
})

const mockApi = api as unknown as {
  setToken: ReturnType<typeof vi.fn>
  getToken: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  get: ReturnType<typeof vi.fn>
}

describe('authStore', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      loading: false,
      error: null,
    })
  })

  describe('hydrate', () => {
    it('reads token from localStorage and sets it', () => {
      localStorage.setItem('blackbeard_token', 'stored-token-123')
      localStorage.setItem('blackbeard_refresh_token', 'stored-refresh-456')

      useAuthStore.getState().hydrate()

      const state = useAuthStore.getState()
      expect(state.token).toBe('stored-token-123')
      expect(state.refreshToken).toBe('stored-refresh-456')
      expect(mockApi.setToken).toHaveBeenCalledWith('stored-token-123')
    })

    it('does nothing when no stored token exists', () => {
      useAuthStore.getState().hydrate()

      const state = useAuthStore.getState()
      expect(state.token).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(mockApi.setToken).not.toHaveBeenCalled()
    })

    it('reads only access token when no refresh token exists', () => {
      localStorage.setItem('blackbeard_token', 'only-access')

      useAuthStore.getState().hydrate()

      const state = useAuthStore.getState()
      expect(state.token).toBe('only-access')
      expect(state.refreshToken).toBeNull()
      expect(mockApi.setToken).toHaveBeenCalledWith('only-access')
    })
  })

  describe('logout', () => {
    it('clears token, user, and localStorage', () => {
      localStorage.setItem('blackbeard_token', 'some-token')
      localStorage.setItem('blackbeard_refresh_token', 'some-refresh')
      useAuthStore.setState({
        user: { id: '1', email: 'a@b.com', display_name: 'A', is_active: true, created_at: '' },
        token: 'some-token',
        refreshToken: 'some-refresh',
        error: 'old error',
      })

      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.token).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.error).toBeNull()
      expect(localStorage.getItem('blackbeard_token')).toBeNull()
      expect(localStorage.getItem('blackbeard_refresh_token')).toBeNull()
      expect(mockApi.setToken).toHaveBeenCalledWith('')
    })
  })

  describe('login', () => {
    it('sets token and user on success', async () => {
      const mockUser = {
        id: '1',
        email: 'test@example.com',
        display_name: 'Test User',
        is_active: true,
        created_at: '2024-01-01',
      }
      mockApi.post.mockResolvedValueOnce({
        access_token: 'new-token',
        refresh_token: 'new-refresh',
        user: mockUser,
      })

      await useAuthStore.getState().login('test@example.com', 'password')

      const state = useAuthStore.getState()
      expect(state.token).toBe('new-token')
      expect(state.refreshToken).toBe('new-refresh')
      expect(state.user).toEqual(mockUser)
      expect(state.loading).toBe(false)
      expect(state.error).toBeNull()
      expect(localStorage.getItem('blackbeard_token')).toBe('new-token')
      expect(localStorage.getItem('blackbeard_refresh_token')).toBe('new-refresh')
      expect(mockApi.setToken).toHaveBeenCalledWith('new-token')
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/auth/login', {
        email: 'test@example.com',
        password: 'password',
      })
    })

    it('sets error on API failure', async () => {
      mockApi.post.mockRejectedValueOnce(new ApiError('Invalid credentials', 401, null))

      await expect(useAuthStore.getState().login('bad@example.com', 'wrong')).rejects.toThrow()

      const state = useAuthStore.getState()
      expect(state.error).toBe('Invalid credentials')
      expect(state.loading).toBe(false)
      expect(state.token).toBeNull()
      expect(state.user).toBeNull()
    })

    it('sets generic error for non-ApiError failures', async () => {
      mockApi.post.mockRejectedValueOnce(new Error('Network error'))

      await expect(useAuthStore.getState().login('test@example.com', 'password')).rejects.toThrow()

      const state = useAuthStore.getState()
      expect(state.error).toBe('Network error')
      expect(state.loading).toBe(false)
    })

    it('sets loading to true while request is in progress', async () => {
      let resolvePost: (value: unknown) => void
      const postPromise = new Promise((resolve) => {
        resolvePost = resolve
      })
      mockApi.post.mockReturnValueOnce(postPromise)

      const loginPromise = useAuthStore.getState().login('test@example.com', 'pass')

      expect(useAuthStore.getState().loading).toBe(true)
      expect(useAuthStore.getState().error).toBeNull()

      resolvePost!({
        access_token: 'tk',
        refresh_token: 'rt',
        user: {
          id: '1',
          email: 'test@example.com',
          display_name: 'Test',
          is_active: true,
          created_at: '',
        },
      })
      await loginPromise

      expect(useAuthStore.getState().loading).toBe(false)
    })
  })
})
