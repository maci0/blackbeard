import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Anchor, LogIn } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useDocumentTitle } from '@/lib/hooks'
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

  const error = localError ?? storeError

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

        {error && <ErrorAlert message={error} className="mb-4" />}

        {/* Form */}
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <fieldset disabled={loading} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium">
                Email <span className="text-destructive">*</span>
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                autoFocus
                required
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-sm font-medium">
                Password <span className="text-destructive">*</span>
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                placeholder="Enter your password"
              />
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
