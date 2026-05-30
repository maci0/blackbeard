import { useEffect, useState, useCallback } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {
  KeyRound,
  Plus,
  Trash2,
  RefreshCw,
  X,
  Eye,
  EyeOff,
  Copy,
  Check,
  Search,
  Shield,
} from 'lucide-react'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { CardSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { SmartTime } from '@/components/ui/SmartTime'
import { cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks'
import { useToastStore } from '@/stores/toastStore'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface Credential {
  id: string
  name: string
  type: string
  description: string
  created_at: string
  updated_at: string
  last_used_at: string | null
  masked_value: string
}

const CREDENTIAL_TYPES = [
  { value: 'api_key', label: 'API Key' },
  { value: 'token', label: 'Bearer Token' },
  { value: 'password', label: 'Password' },
  { value: 'oauth_client', label: 'OAuth Client' },
  { value: 'custom', label: 'Custom Secret' },
] as const

/* ------------------------------------------------------------------ */
/* Type badge                                                          */
/* ------------------------------------------------------------------ */

const TYPE_COLORS: Record<string, string> = {
  api_key:
    'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900 dark:text-violet-300 dark:border-violet-800',
  token:
    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  password:
    'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300 dark:border-amber-800',
  oauth_client:
    'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
  custom:
    'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700',
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold',
        TYPE_COLORS[type] ?? TYPE_COLORS.custom,
      )}
    >
      {type.replace(/_/g, ' ')}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Create dialog                                                       */
/* ------------------------------------------------------------------ */

function CreateCredentialDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState('api_key')
  const [value, setValue] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showValue, setShowValue] = useState(false)
  const toasts = useToastStore()

  const resetForm = useCallback(() => {
    setName('')
    setType('api_key')
    setValue('')
    setDescription('')
    setError(null)
    setShowValue(false)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Credential name is required.')
      return
    }
    if (!value.trim()) {
      setError('Secret value is required.')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await api.post('/api/v1/credentials', {
        name: name.trim().toLowerCase().replace(/\s+/g, '-'),
        type,
        value: value.trim(),
        description: description.trim(),
      })
      toasts.success(`Credential "${name}" created`)
      resetForm()
      onOpenChange(false)
      onCreated()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create credential'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) resetForm()
        onOpenChange(v)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-semibold">Add Credential</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Store a secret for use by tools and integrations. Values are masked and never returned
            in full.
          </Dialog.Description>

          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-4">
            <div>
              <label htmlFor="cred-name" className="mb-1.5 block text-sm font-medium">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                id="cred-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                aria-required="true"
                autoFocus
                pattern="[a-z0-9][a-z0-9\-]*"
                aria-describedby="cred-name-hint"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="my-api-key"
              />
              <p id="cred-name-hint" className="mt-1 text-xs text-muted-foreground">
                Lowercase letters, numbers, and hyphens only
              </p>
            </div>

            <div>
              <label htmlFor="cred-type" className="mb-1.5 block text-sm font-medium">
                Type
              </label>
              <select
                id="cred-type"
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {CREDENTIAL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="cred-value" className="mb-1.5 block text-sm font-medium">
                Secret Value <span className="text-destructive">*</span>
              </label>
              <div className="relative">
                <input
                  id="cred-value"
                  type={showValue ? 'text' : 'password'}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  required
                  aria-required="true"
                  className="w-full rounded-md border bg-background px-3 py-2 pr-10 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="sk-..."
                />
                <button
                  type="button"
                  onClick={() => setShowValue((v) => !v)}
                  aria-label={showValue ? 'Hide value' : 'Show value'}
                  className="absolute right-1 top-1/2 flex h-[44px] w-[44px] -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {showValue ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            <div>
              <label htmlFor="cred-desc" className="mb-1.5 block text-sm font-medium">
                Description
              </label>
              <input
                id="cred-desc"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="OpenAI production key for content team"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                aria-busy={submitting}
                className="btn-press inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-current" />}
                Add Credential
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/* ------------------------------------------------------------------ */
/* Credential card                                                     */
/* ------------------------------------------------------------------ */

function CredentialCard({
  credential,
  onDelete,
}: {
  credential: Credential
  onDelete: (id: string) => void
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    void navigator.clipboard.writeText(credential.masked_value)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-150 hover:shadow-md">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-100 dark:bg-violet-900">
            <KeyRound className="h-4 w-4 text-violet-600 dark:text-violet-400" />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold" title={credential.name}>
              {credential.name}
            </h3>
          </div>
        </div>
        <TypeBadge type={credential.type} />
      </div>

      {/* Body */}
      <div className="space-y-2.5 px-4 py-3">
        {credential.description && (
          <p className="text-xs text-muted-foreground">{credential.description}</p>
        )}

        <div className="flex items-center gap-2">
          <code className="flex-1 truncate rounded bg-muted/60 px-2 py-1 font-mono text-xs text-muted-foreground">
            {credential.masked_value}
          </code>
          <button
            type="button"
            onClick={handleCopy}
            className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Copy masked value"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
          </button>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t bg-muted/10 px-4 py-2.5">
        <span className="text-[11px] text-muted-foreground">
          <SmartTime date={credential.updated_at} />
        </span>
        <button
          type="button"
          onClick={() => onDelete(credential.id)}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Delete ${credential.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function Credentials() {
  useDocumentTitle('Credentials')

  const [credentials, setCredentials] = useState<Credential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const toasts = useToastStore()

  const fetchCredentials = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.get<{ items: Credential[] }>('/api/v1/credentials')
      setCredentials(resp.items)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load credentials'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchCredentials()
  }, [fetchCredentials])

  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/api/v1/credentials/${deleteTarget}`)
      toasts.success('Credential deleted')
      setDeleteTarget(null)
      void fetchCredentials()
    } catch (err) {
      toasts.error(getErrorMessage(err, 'Failed to delete credential'))
    } finally {
      setDeleting(false)
    }
  }

  const filtered = filter
    ? credentials.filter(
        (c) =>
          c.name.toLowerCase().includes(filter.toLowerCase()) ||
          c.type.toLowerCase().includes(filter.toLowerCase()),
      )
    : credentials

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-6xl p-6">
        <PageHeader
          title="Credentials"
          description="Manage secrets and API keys used by tools and integrations"
          actions={
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void fetchCredentials()}
                disabled={loading}
                aria-label="Refresh credentials"
                className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin motion-reduce:animate-none')} />
              </button>
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Plus className="h-4 w-4" />
                Add Credential
              </button>
            </div>
          }
        />

        {/* Search */}
        {credentials.length > 0 && (
          <div className="mt-6 flex items-center gap-3">
            <div className="relative max-w-xs flex-1">
              <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter credentials…"
                autoComplete="off"
                aria-label="Filter credentials by name or type"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
        )}

        {/* Content */}
        <div className="mt-6">
          {error && (
            <ErrorAlert
              message={error}
              onAction={() => void fetchCredentials()}
              actionLabel="Retry"
              onDismiss={() => setError(null)}
              className="mb-4"
            />
          )}

          {loading ? (
            <CardSkeleton count={4} />
          ) : credentials.length === 0 ? (
            <EmptyState
              icon={<Shield className="h-10 w-10" />}
              title="No credentials yet"
              description="Add API keys, tokens, and other secrets that your tools and integrations need."
              action={{ label: 'Add Credential', onClick: () => setCreateOpen(true) }}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Search className="h-10 w-10" />}
              title="No matching credentials"
              description={`No credentials match "${filter}". Try a different search term.`}
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((cred) => (
                <CredentialCard
                  key={cred.id}
                  credential={cred}
                  onDelete={(id) => setDeleteTarget(id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <CreateCredentialDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => void fetchCredentials()}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title="Delete credential?"
        description="This credential will be permanently deleted. Any tools or integrations using it will lose access."
        confirmLabel="Delete"
        confirmVariant="destructive"
        loading={deleting}
        onConfirm={() => void handleDelete()}
      />
    </div>
  )
}
