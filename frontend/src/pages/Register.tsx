import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Anchor, UserPlus } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useDocumentTitle } from '@/lib/hooks'
import { Spinner } from '@/components/ui/Spinner'

export default function Register() {
  const navigate = useNavigate()
  const register = useAuthStore((s) => s.register)
  const loading = useAuthStore((s) => s.loading)
  const storeError = useAuthStore((s) => s.error)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const error = localError ?? storeError

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
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900">
            <Anchor className="h-7 w-7 text-indigo-400" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">Get started with Blackbeard</p>
        </div>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div>
            <label htmlFor="register-display-name" className="mb-1.5 block text-sm font-medium">
              Display name
            </label>
            <input
              id="register-display-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
              autoFocus
              required
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Your name"
            />
          </div>

          <div>
            <label htmlFor="register-email" className="mb-1.5 block text-sm font-medium">
              Email
            </label>
            <input
              id="register-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="register-password" className="mb-1.5 block text-sm font-medium">
              Password
            </label>
            <input
              id="register-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Min 8 characters"
            />
            {password.length > 0 && password.length < 8 && (
              <p className="mt-1 text-xs text-muted-foreground" aria-live="polite">
                {8 - password.length} more character{password.length === 7 ? '' : 's'} needed
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {loading ? (
              <Spinner size="sm" className="text-current" />
            ) : (
              <UserPlus className="h-4 w-4" />
            )}
            Create account
          </button>
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
    </div>
  )
}
