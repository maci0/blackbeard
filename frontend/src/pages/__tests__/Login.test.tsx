/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Login from '../Login'
import { useAuthStore } from '@/stores/authStore'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ state: null, pathname: '/login', search: '', hash: '', key: 'default' }),
  }
})

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

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )
}

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      loading: false,
      error: null,
    })
  })

  describe('rendering', () => {
    it('renders email and password fields', () => {
      renderLogin()

      expect(screen.getByLabelText(/^email/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument()
    })

    it('renders sign in button', () => {
      renderLogin()

      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    })

    it('renders register link', () => {
      renderLogin()

      expect(screen.getByText(/create one/i)).toBeInTheDocument()
    })

    it('renders page heading', () => {
      renderLogin()

      expect(screen.getByText('Sign in to Blackbeard')).toBeInTheDocument()
    })
  })

  describe('validation', () => {
    it('shows error when fields contain only whitespace', async () => {
      const user = userEvent.setup()
      // Mock login to not be called — validation should prevent it
      const mockLogin = vi.fn()
      useAuthStore.setState({ login: mockLogin })

      renderLogin()

      const emailInput = screen.getByLabelText(/email/i)
      const passwordInput = screen.getByLabelText(/^password/i)

      // Type a space into each field so they pass HTML required check
      // but fail the trim() check in handleSubmit
      await user.type(emailInput, ' ')
      await user.type(passwordInput, ' ')

      // Programmatically submit the form since the browser required
      // validation won't fire in jsdom for type="email" with whitespace
      act(() => {
        const form = emailInput.closest('form')!
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      })

      // Wait for the error to appear
      expect(await screen.findByText('Email and password are required.')).toBeInTheDocument()
      expect(mockLogin).not.toHaveBeenCalled()
    })
  })

  describe('login flow', () => {
    it('shows error on invalid credentials', async () => {
      const mockLogin = vi.fn().mockImplementation(() => {
        useAuthStore.setState({ error: 'Invalid credentials' })
        return Promise.reject(new Error('Invalid credentials'))
      })
      useAuthStore.setState({ login: mockLogin, error: null })

      renderLogin()

      const user = userEvent.setup()
      await user.type(screen.getByLabelText(/email/i), 'bad@example.com')
      await user.type(screen.getByLabelText(/^password/i), 'wrong')

      await user.click(screen.getByRole('button', { name: /sign in/i }))

      expect(await screen.findByText('Invalid credentials')).toBeInTheDocument()
    })

    it('calls login with email and password on submit', async () => {
      const user = userEvent.setup()
      const mockLogin = vi.fn().mockResolvedValue(undefined)
      useAuthStore.setState({ login: mockLogin })

      renderLogin()

      await user.type(screen.getByLabelText(/email/i), 'test@example.com')
      await user.type(screen.getByLabelText(/^password/i), 'secretpassword')
      await user.click(screen.getByRole('button', { name: /sign in/i }))

      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'secretpassword')
    })

    it('navigates to /studio on successful login', async () => {
      const user = userEvent.setup()
      const mockLogin = vi.fn().mockResolvedValue(undefined)
      useAuthStore.setState({ login: mockLogin })

      renderLogin()

      await user.type(screen.getByLabelText(/email/i), 'test@example.com')
      await user.type(screen.getByLabelText(/^password/i), 'password')
      await user.click(screen.getByRole('button', { name: /sign in/i }))

      expect(mockNavigate).toHaveBeenCalledWith('/studio', { replace: true })
    })

    it('shows loading state during login', () => {
      useAuthStore.setState({ loading: true })

      renderLogin()

      const button = screen.getByRole('button', { name: /signing in/i })
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute('aria-busy', 'true')
    })

    it('disables form fields during loading', () => {
      useAuthStore.setState({ loading: true })

      renderLogin()

      expect(screen.getByLabelText(/email/i)).toBeDisabled()
      expect(screen.getByLabelText(/^password/i)).toBeDisabled()
    })
  })
})
