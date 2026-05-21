import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Anchor, UserPlus, Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useDocumentTitle } from '@/hooks'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorAlert } from '@/components/ui/ErrorAlert'

export default function Register() {
  const navigate = useNavigate()
  const register = useAuthStore((s) => s.register)
  const loading = useAuthStore((s) => s.loading)
  const storeError = useAuthStore((s) => s.error)

  useEffect(() => {
    useAuthStore.setState({ error: null })
  }, [])

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const clearError = () => setLocalError(null)

  const error = localError ?? storeError
  const validationField =
    localError === 'Email is required.'
      ? 'email'
      : localError === 'Display name is required.'
        ? 'displayName'
        : localError === 'Password must be at least 8 characters.'
          ? 'password'
          : null

  useDocumentTitle('Create Account')

  const validate = (): string | null => {
    if (!email.trim()) return 'Email is required.'
    if (!displayName.trim()) return 'Display name is required.'
    if (password.length < 8) return 'Password must be at least 8 characters.'
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)

    const validationError = validate()
    if (validationError) {
      setLocalError(validationError)
      return
    }

    try {
      await register(email, password, displayName)
      void navigate('/studio', { replace: true })
    } catch {
      // Error is set in the store
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-muted/50 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-3 flex h-12 w-12 animate-[logo-pulse_2s_ease-in-out] items-center justify-center rounded-xl bg-slate-900 dark:border dark:border-slate-700">
            <Anchor className="h-7 w-7 text-indigo-400" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">Get started with Blackbeard</p>
        </div>

        {error && <ErrorAlert id="register-error" message={error} className="mb-4" />}

        {/* Form */}
        <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-4">
          <fieldset disabled={loading} className="space-y-4">
            <div>
              <label htmlFor="register-display-name" className="mb-1.5 block text-sm font-medium">
                Display name <span className="text-destructive">*</span>
              </label>
              <input
                id="register-display-name"
                type="text"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value)
                  clearError()
                }}
                autoComplete="name"
                autoFocus
                required
                aria-invalid={
                  validationField === 'displayName' ||
                  (!validationField && !!storeError) ||
                  undefined
                }
                aria-describedby={error ? 'register-error' : undefined}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                placeholder="Your name"
              />
            </div>

            <div>
              <label htmlFor="register-email" className="mb-1.5 block text-sm font-medium">
                Email <span className="text-destructive">*</span>
              </label>
              <input
                id="register-email"
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  clearError()
                }}
                autoComplete="email"
                required
                aria-invalid={
                  validationField === 'email' || (!validationField && !!storeError) || undefined
                }
                aria-describedby={error ? 'register-error' : undefined}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="register-password" className="mb-1.5 block text-sm font-medium">
                Password <span className="text-destructive">*</span>
              </label>
              <div className="relative">
                <input
                  id="register-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    clearError()
                  }}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  aria-invalid={
                    validationField === 'password' ||
                    (!validationField && !!storeError) ||
                    undefined
                  }
                  aria-describedby={`register-password-hint${error ? ' register-error' : ''}`}
                  className="w-full rounded-md border bg-background px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  placeholder="Min 8 characters"
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
              {password.length > 0 && password.length < 8 ? (
                <p
                  id="register-password-hint"
                  className="mt-1 text-xs text-muted-foreground"
                  aria-live="polite"
                >
                  {8 - password.length} more character{password.length === 7 ? '' : 's'} needed
                </p>
              ) : (
                <p id="register-password-hint" className="sr-only" aria-live="polite">
                  {password.length >= 8
                    ? 'Password meets minimum length'
                    : 'Must be at least 8 characters'}
                </p>
              )}
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
                <UserPlus className="h-4 w-4" />
              )}
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </fieldset>
        </form>

        {/* Login link */}
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link
            to="/login"
            className="font-medium text-primary underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  )
}
