import { useEffect, useState, useCallback } from 'react'
import { useCopyToClipboard } from '@/hooks'
import {
  Webhook,
  Plus,
  Trash2,
  RefreshCw,
  X,
  AlertTriangle,
  Copy,
  Check,
  Eye,
  EyeOff,
  Send,
} from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { cn, getErrorMessage } from '@/lib/utils'
import { formatDate, timeAgo } from '@/lib/formatters'
import { useDocumentTitle, useDeleteError } from '@/hooks'
import { useToastStore } from '@/stores/toastStore'

const WEBHOOK_TEST_KEY = 'blackbeard_webhook_tests'

function getWebhookTestRecord(): Record<string, string> {
  try {
    const raw = localStorage.getItem(WEBHOOK_TEST_KEY)
    return raw ? (JSON.parse(raw) as Record<string, string>) : {}
  } catch (err) {
    console.warn('[webhooks] failed to parse test record from localStorage:', err)
    return {}
  }
}

function setWebhookTested(webhookId: string) {
  const record = getWebhookTestRecord()
  record[webhookId] = new Date().toISOString()
  localStorage.setItem(WEBHOOK_TEST_KEY, JSON.stringify(record))
}

interface WebhookRecord {
  id: string
  url: string
  events: string[]
  active: boolean
  created_at: string | null
}

interface WebhookListResponse {
  items: WebhookRecord[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

interface WebhookCreateResponse extends WebhookRecord {
  secret: string
}

const ALL_EVENTS = [
  'crew_started',
  'crew_completed',
  'task_started',
  'task_completed',
  'tool_started',
  'tool_finished',
  'llm_started',
  'llm_completed',
] as const

function truncateUrl(url: string, maxLen = 50): string {
  if (url.length <= maxLen) return url
  return url.slice(0, maxLen) + '…'
}

function EventBadge({ event }: { event: string }) {
  const colors: Record<string, string> = {
    crew_started: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    crew_completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    task_started: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    task_completed: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    tool_started: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    tool_finished: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    llm_started: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    llm_completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold',
        colors[event] ?? 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      )}
    >
      {event.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
    </span>
  )
}

function SecretReveal({ secret }: { secret: string }) {
  const [visible, setVisible] = useState(false)
  const { copied, copy } = useCopyToClipboard()

  const handleCopy = async () => {
    try {
      await copy(secret)
    } catch {
      useToastStore.getState().error('Failed to copy to clipboard')
    }
  }

  return (
    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
      <p className="mb-2 text-xs font-semibold text-amber-800 dark:text-amber-300">
        Signing secret — save this now, it will not be shown again
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded bg-muted px-2 py-1.5 font-mono text-xs">
          {visible ? secret : '••••••••••••••••••••••••••••••••'}
        </code>
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide secret' : 'Reveal secret'}
          className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => void handleCopy()}
          aria-label={copied ? 'Secret copied' : 'Copy secret'}
          className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? 'Secret copied to clipboard' : ''}
      </span>
    </div>
  )
}

function AddWebhookDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const [url, setUrl] = useState('')
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdSecret, setCreatedSecret] = useState<string | null>(null)
  const toasts = useToastStore()

  const resetForm = useCallback(() => {
    setUrl('')
    setSelectedEvents(new Set())
    setError(null)
    setCreatedSecret(null)
  }, [])

  const toggleEvent = (event: string) => {
    setSelectedEvents((prev) => {
      const next = new Set(prev)
      if (next.has(event)) {
        next.delete(event)
      } else {
        next.add(event)
      }
      return next
    })
    setError(null)
  }

  const toggleAll = () => {
    setSelectedEvents((prev) => (prev.size === ALL_EVENTS.length ? new Set() : new Set(ALL_EVENTS)))
    setError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) {
      setError('Webhook URL is required.')
      return
    }
    if (!/^https?:\/\//.test(url.trim())) {
      setError('URL must start with http:// or https://.')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const result = await api.post<WebhookCreateResponse>('/api/v1/webhooks', {
        url: url.trim(),
        events: [...selectedEvents],
      })
      setCreatedSecret(result.secret)
      toasts.success('Webhook created')
      onCreated()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create webhook'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleClose = (v: boolean) => {
    if (!v) resetForm()
    onOpenChange(v)
  }

  if (createdSecret) {
    return (
      <Dialog.Root open={open} onOpenChange={handleClose}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border bg-card shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div>
                <Dialog.Title className="text-base font-semibold">Webhook Created</Dialog.Title>
                <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                  Your webhook has been registered successfully
                </Dialog.Description>
              </div>
              <Dialog.Close
                className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>
            <div className="p-5">
              <SecretReveal secret={createdSecret} />
              <div className="mt-4 flex justify-end">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Done
                  </button>
                </Dialog.Close>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border bg-card shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold">Add Webhook</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                Register a URL to receive execution event notifications
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-4 p-5">
            <fieldset disabled={submitting} aria-busy={submitting} className="space-y-4">
              <div>
                <label htmlFor="webhook-url" className="mb-1.5 block text-xs font-medium">
                  URL <span className="text-destructive">*</span>
                </label>
                <input
                  id="webhook-url"
                  required
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? 'webhook-url-error' : undefined}
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value)
                    setError(null)
                  }}
                  placeholder="https://example.com/webhook"
                  autoComplete="off"
                  autoFocus
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span id="webhook-events-label" className="text-xs font-medium">
                    Events
                  </span>
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="text-xs text-primary transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {selectedEvents.size === ALL_EVENTS.length ? 'Deselect all' : 'Select all'}
                  </button>
                </div>
                <p className="mb-2 text-xs text-muted-foreground">
                  Leave empty to receive all events
                </p>
                <div
                  className="grid grid-cols-2 gap-2"
                  role="group"
                  aria-labelledby="webhook-events-label"
                >
                  {ALL_EVENTS.map((event) => (
                    <label
                      key={event}
                      className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent has-[:checked]:border-primary/30 has-[:checked]:bg-primary/5"
                    >
                      <input
                        type="checkbox"
                        checked={selectedEvents.has(event)}
                        onChange={() => toggleEvent(event)}
                        className="h-4 w-4 rounded border-gray-300 text-primary accent-primary focus-visible:ring-2 focus-visible:ring-ring"
                      />
                      <span className="text-xs">
                        {event.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </fieldset>

            {error && (
              <div
                id="webhook-url-error"
                role="alert"
                aria-live="assertive"
                className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
              >
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                aria-busy={submitting}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-current" />}
                Add Webhook
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const TABLE_HEADERS = ['URL', 'Events', 'Status', 'Last Tested', 'Created', 'Actions'] as const

export default function Webhooks() {
  const [webhooks, setWebhooks] = useState<WebhookRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WebhookRecord | null>(null)
  const [deleting, setDeleting] = useState(false)
  const { deleteError, showDeleteError, clearDeleteError } = useDeleteError()
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testRecords, setTestRecords] = useState(() => getWebhookTestRecord())
  const toasts = useToastStore()

  const handleTest = useCallback(
    async (webhook: WebhookRecord) => {
      setTestingId(webhook.id)
      try {
        await api.post(`/api/v1/webhooks/${webhook.id}/test`, {})
        setWebhookTested(webhook.id)
        setTestRecords(getWebhookTestRecord())
        toasts.success('Test event sent')
      } catch (err) {
        const msg = getErrorMessage(err, '')
        if (msg.includes('404') || msg.includes('Not Found') || msg.includes('405')) {
          setWebhookTested(webhook.id)
          setTestRecords(getWebhookTestRecord())
          toasts.info('Test recorded locally (backend test endpoint not available)')
        } else {
          toasts.error(getErrorMessage(err, 'Failed to send test event'))
        }
      } finally {
        setTestingId(null)
      }
    },
    [toasts],
  )

  useDocumentTitle('Webhooks')

  const fetchWebhooks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<WebhookListResponse>('/api/v1/webhooks')
      setWebhooks(result.items)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load webhooks'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchWebhooks()
  }, [fetchWebhooks])

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/api/v1/webhooks/${deleteTarget.id}`)
      toasts.success('Webhook deleted')
      setDeleteTarget(null)
      void fetchWebhooks()
    } catch (err) {
      setDeleteTarget(null)
      showDeleteError(getErrorMessage(err, 'Failed to delete webhook'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <PageHeader
            title="Webhooks"
            description="HTTP endpoints that receive execution event notifications"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => void fetchWebhooks()}
                  disabled={loading}
                  aria-label="Refresh webhooks"
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCw
                    className={cn(
                      'h-3.5 w-3.5',
                      loading && 'animate-spin motion-reduce:animate-none',
                    )}
                  />
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => setAddOpen(true)}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-4 w-4" />
                  Add Webhook
                </button>
              </>
            }
          />
        </div>

        {deleteError && (
          <ErrorAlert
            message={deleteError}
            actionLabel="Dismiss"
            onAction={() => clearDeleteError()}
            ariaLabel="Dismiss error"
            className="mb-4"
          />
        )}

        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchWebhooks()}
            ariaLabel="Retry loading webhooks"
            className="mb-4"
          />
        )}

        {loading && webhooks.length === 0 ? (
          <TableSkeleton />
        ) : webhooks.length === 0 ? (
          <EmptyState
            icon={<Webhook />}
            title="No webhooks registered"
            description="Add a webhook to receive execution event notifications"
            action={{
              label: 'Add Webhook',
              onClick: () => setAddOpen(true),
            }}
          />
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="max-h-[calc(100vh-16rem)] overflow-auto">
              <table className="w-full min-w-[640px] text-sm" aria-label="Webhooks">
                <thead className="sticky top-0 z-10">
                  <tr className="border-b bg-muted/60">
                    {TABLE_HEADERS.map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {webhooks.map((webhook) => (
                    <tr
                      key={webhook.id}
                      tabIndex={0}
                      role="row"
                      aria-label={`Webhook ${truncateUrl(webhook.url, 30)} — ${webhook.active ? 'active' : 'inactive'}`}
                      className="group border-l-2 border-l-transparent transition-colors duration-150 hover:border-l-primary hover:bg-accent/50 focus-visible:border-l-primary focus-visible:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    >
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs font-medium" title={webhook.url}>
                          {truncateUrl(webhook.url)}
                        </span>
                      </td>

                      <td className="px-4 py-3">
                        {webhook.events.length === 0 ? (
                          <span className="text-xs text-muted-foreground">All events</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {webhook.events.map((event) => (
                              <EventBadge key={event} event={event} />
                            ))}
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold',
                            webhook.active
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
                          )}
                        >
                          <span
                            className={cn(
                              'h-1.5 w-1.5 rounded-full',
                              webhook.active ? 'bg-emerald-500' : 'bg-gray-400',
                            )}
                            aria-hidden="true"
                          />
                          {webhook.active ? 'Active' : 'Inactive'}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-muted-foreground">
                        {(() => {
                          const lastTested = testRecords[webhook.id] ?? null
                          if (!lastTested) {
                            return (
                              <span className="text-xs text-muted-foreground/60">Not tested</span>
                            )
                          }
                          return (
                            <span className="text-xs" title={formatDate(lastTested)}>
                              {timeAgo(lastTested)}
                            </span>
                          )
                        })()}
                      </td>

                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(webhook.created_at)}
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            disabled={testingId === webhook.id}
                            onClick={(e) => {
                              e.stopPropagation()
                              void handleTest(webhook)
                            }}
                            aria-label={`Send test event to ${truncateUrl(webhook.url, 30)}`}
                            title="Send test"
                            className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {testingId === webhook.id ? (
                              <Spinner size="sm" />
                            ) : (
                              <Send className="h-3.5 w-3.5" />
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteTarget(webhook)
                            }}
                            aria-label={`Delete webhook ${truncateUrl(webhook.url, 30)}`}
                            title="Delete"
                            className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <AddWebhookDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          onCreated={() => void fetchWebhooks()}
        />

        <ConfirmDialog
          open={deleteTarget !== null}
          onOpenChange={(v) => {
            if (!v) setDeleteTarget(null)
          }}
          title="Delete webhook"
          description={`Delete webhook for "${deleteTarget?.url ?? ''}"? This cannot be undone.`}
          confirmLabel="Delete"
          confirmVariant="destructive"
          onConfirm={() => void handleDelete()}
          loading={deleting}
        />
      </div>
    </div>
  )
}
