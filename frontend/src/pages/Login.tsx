import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Anchor, LogIn, Shield, Eye, EyeOff } from 'lucide-react'
import { useAuthStore, TOKEN_KEY, REFRESH_KEY } from '@/stores/authStore'
import { useDocumentTitle } from '@/hooks'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const loading = useAuthStore((s) => s.loading)
  const storeError = useAuthStore((s) => s.error)
  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/studio'

  useEffect(() => {
    useAuthStore.setState({ error: null })
  }, [])

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [oidcEnabled, setOidcEnabled] = useState(false)
  const clearError = () => setLocalError(null)

  useEffect(() => {
    fetch('/api/v1/config/public')
      .then((r) => r.json())
      .then((d: { oidc_enabled?: boolean }) => setOidcEnabled(d.oidc_enabled === true))
      .catch(() => {
        console.debug('[Login] OIDC config fetch failed — SSO button hidden')
      })
  }, [])

  useEffect(() => {
    const hash = window.location.hash.slice(1)
    if (!hash) return
    const params = new URLSearchParams(hash)
    const token = params.get('token')
    const refresh = params.get('refresh')
    if (token && refresh) {
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(REFRESH_KEY, refresh)
      window.history.replaceState(null, '', window.location.pathname)
      void navigate(redirectTo, { replace: true })
    }
  }, [navigate, redirectTo])

  const error = localError ?? storeError
  const isFieldError = localError === 'Email and password are required.'

  useDocumentTitle('Sign In')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)

    if (!email.trim() || !password.trim()) {
      setLocalError('Email and password are required.')
      return
    }

    try {
      await login(email, password)
      void navigate(redirectTo, { replace: true })
    } catch {
      // Error is set in the store
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 dark:border dark:border-slate-700">
            <Anchor className="h-7 w-7 text-indigo-400" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Sign in to Blackbeard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Agent Management Platform</p>
        </div>

        {error && <ErrorAlert id="login-error" message={error} className="mb-4" />}

        {/* Form */}
        <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-4">
          <fieldset disabled={loading} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium">
                Email <span className="text-destructive">*</span>
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  clearError()
                }}
                autoComplete="email"
                autoFocus
                required
                aria-invalid={(isFieldError ? !email.trim() : !!error) || undefined}
                aria-describedby={error ? 'login-error' : undefined}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-sm font-medium">
                Password <span className="text-destructive">*</span>
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearError()
                  }}
                  autoComplete="current-password"
                  required
                  aria-invalid={(isFieldError ? !password.trim() : !!error) || undefined}
                  aria-describedby={error ? 'login-error' : undefined}
                  className="w-full rounded-md border bg-background px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-1 top-1/2 flex h-[44px] w-[44px] -translate-y-1/2 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              aria-busy={loading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <Spinner size="sm" className="text-current" />
              ) : (
                <LogIn className="h-4 w-4" />
              )}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </fieldset>
        </form>

        {/* SSO button */}
        {oidcEnabled && (
          <>
            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-background px-2 text-muted-foreground">or</span>
              </div>
            </div>
            <a
              href="/api/v1/auth/oidc/login"
              className="flex w-full items-center justify-center gap-2 rounded-md border px-4 py-2.5 text-sm font-medium transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Shield className="h-4 w-4" />
              Sign in with SSO
            </a>
          </>
        )}

        {/* Register link */}
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{' '}
          <Link
            to="/register"
            className="font-medium text-primary underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Create one
          </Link>
        </p>
      </div>
    </main>
  )
}
