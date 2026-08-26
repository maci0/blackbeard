import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Anchor, LogIn, Shield, Eye, EyeOff } from 'lucide-react'
import { api } from '@/api/client'
import { useAuthStore, TOKEN_KEY, REFRESH_KEY } from '@/stores/authStore'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const loading = useAuthStore((s) => s.loading)
  const storeError = useAuthStore((s) => s.error)
  const rawRedirect = (location.state as { from?: string } | null)?.from
  const redirectTo =
    rawRedirect && rawRedirect.startsWith('/') && !rawRedirect.startsWith('//')
      ? rawRedirect
      : '/studio'

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
    api
      .get<{ oidc_enabled?: boolean }>('/api/v1/config/public')
      .then((d) => setOidcEnabled(d.oidc_enabled === true))
      .catch((err: unknown) => {
        console.warn('[login] OIDC config fetch failed:', err)
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
  const emailMissing =
    localError === 'Email is required.' || localError === 'Email and password are required.'
  const passwordMissing =
    localError === 'Password is required.' || localError === 'Email and password are required.'

  useDocumentTitle('Sign In')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)

    if (!email.trim() && !password.trim()) {
      setLocalError('Email and password are required.')
      document.getElementById('login-email')?.focus()
      return
    }
    if (!email.trim()) {
      setLocalError('Email is required.')
      document.getElementById('login-email')?.focus()
      return
    }
    if (!password.trim()) {
      setLocalError('Password is required.')
      document.getElementById('login-password')?.focus()
      return
    }

    try {
      await login(email, password)
      setPassword('')
      void navigate(redirectTo, { replace: true })
    } catch {
      // Error is set in the store: move focus so screen readers announce it
      document.getElementById('login-email')?.focus()
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50/80 via-background to-violet-50/60 px-4 dark:from-indigo-950/30 dark:via-background dark:to-violet-950/20">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 shadow-lg shadow-indigo-500/20 dark:border dark:border-slate-700 dark:shadow-indigo-400/10">
            <Anchor className="h-8 w-8 text-indigo-400" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Blackbeard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Agent Management Platform</p>
        </div>

        <div className="rounded-2xl border bg-card/80 p-6 shadow-xl backdrop-blur-sm">
          {error && <ErrorAlert id="login-error" message={error} className="mb-4" />}

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
                  aria-required="true"
                  aria-invalid={(emailMissing ? !email.trim() : !!error) || undefined}
                  aria-describedby={
                    emailMissing && !email.trim()
                      ? 'login-email-error'
                      : error
                        ? 'login-error'
                        : undefined
                  }
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  placeholder="you@example.com"
                />
                {emailMissing && !email.trim() && (
                  <p id="login-email-error" className="mt-1 text-xs text-destructive">
                    Email is required
                  </p>
                )}
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
                    aria-required="true"
                    aria-invalid={(passwordMissing ? !password.trim() : !!error) || undefined}
                    aria-describedby={
                      passwordMissing && !password.trim()
                        ? 'login-password-error'
                        : error
                          ? 'login-error'
                          : undefined
                    }
                    className="w-full rounded-md border bg-background px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-1 top-1/2 flex h-[44px] w-[44px] -translate-y-1/2 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
                {passwordMissing && !password.trim() && (
                  <p id="login-password-error" className="mt-1 text-xs text-destructive">
                    Password is required
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                aria-busy={loading}
                className="btn-press inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <Spinner size="sm" className="text-current" />
                ) : (
                  <LogIn className="h-4 w-4" aria-hidden="true" />
                )}
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </fieldset>
          </form>

          {oidcEnabled && (
            <>
              <div className="relative my-5">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-card px-2 text-muted-foreground">or</span>
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
        </div>

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
