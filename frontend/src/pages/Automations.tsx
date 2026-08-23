import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard'
import {
  Timer,
  Search,
  RefreshCw,
  Plus,
  X,
  Trash2,
  Play,
  Clock,
  Webhook,
  Terminal,
  Copy,
  Check,
} from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { caseFold, cn, getErrorMessage } from '@/lib/utils'
import { formatDate } from '@/lib/formatters'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useToastStore } from '@/stores/toastStore'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface AutomationSpec {
  target_kind?: string
  target_name?: string
  trigger_type?: string
  schedule?: string
  webhook_url?: string
  webhook_secret?: string
  inputs?: Record<string, unknown>
  enabled?: boolean
}

interface AutomationRecord {
  id: string
  name: string
  spec: AutomationSpec
  created_at: string
  updated_at: string
  version: number
}

interface AutomationListResponse {
  items: Array<{
    id: string
    metadata: { name: string }
    spec: AutomationSpec
    created_at: string
    updated_at: string
    version: number
  }>
  total: number
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const TRIGGER_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  cron: Clock,
  webhook: Webhook,
  api: Terminal,
}

function TriggerBadge({ type }: { type: string }) {
  const Icon = TRIGGER_ICONS[type] ?? Clock
  const colors: Record<string, string> = {
    cron: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    webhook: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    api: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold',
        colors[type] ?? 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {type.charAt(0).toUpperCase() + type.slice(1)}
    </span>
  )
}

function EnabledToggle({
  enabled,
  onChange,
  disabled,
  label,
}: {
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        onChange(!enabled)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.stopPropagation()
        }
      }}
      className="inline-flex min-h-[44px] min-w-[44px] shrink-0 cursor-pointer items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span
        aria-hidden="true"
        className={cn(
          'inline-flex h-5 w-9 items-center rounded-full transition-colors',
          enabled ? 'bg-primary' : 'bg-muted-foreground/30',
        )}
      >
        <span
          className={cn(
            'pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
            enabled ? 'translate-x-[18px]' : 'translate-x-0.5',
          )}
        />
      </span>
    </button>
  )
}

function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

  // Times are stated in UTC to match scheduler semantics (croniter runs on
  // datetime.now(UTC)); without the suffix users assume local time.
  if (minute === '*' && hour === '*') return 'Every minute'
  if (minute === '0' && hour === '*') return 'Every hour'
  if (minute === '0' && hour === '0' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*')
    return 'Daily at midnight UTC'
  if (minute !== '*' && hour !== '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*')
    return `Daily at ${hour}:${minute?.padStart(2, '0')} UTC`
  if (dayOfWeek === '1-5') return `Weekdays at ${hour}:${minute?.padStart(2, '0')} UTC`
  if (minute?.startsWith('*/')) return `Every ${minute.slice(2)} minutes`
  if (hour?.startsWith('*/')) return `Every ${hour.slice(2)} hours`

  return expr
}

/* ------------------------------------------------------------------ */
/* Create Automation Dialog                                            */
/* ------------------------------------------------------------------ */

function CreateAutomationDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const [name, setName] = useState('')
  const [targetKind, setTargetKind] = useState('Crew')
  const [targetName, setTargetName] = useState('')
  const [triggerType, setTriggerType] = useState('cron')
  const [schedule, setSchedule] = useState('')
  const [inputs, setInputs] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toasts = useToastStore()

  const resetForm = useCallback(() => {
    setName('')
    setTargetKind('Crew')
    setTargetName('')
    setTriggerType('cron')
    setSchedule('')
    setInputs('')
    setEnabled(true)
    setError(null)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Automation name is required.')
      return
    }
    if (!targetName.trim()) {
      setError('Target name is required.')
      return
    }
    if (triggerType === 'cron' && !schedule.trim()) {
      setError('Cron schedule is required for cron triggers.')
      return
    }

    let parsedInputs: Record<string, unknown> = {}
    if (inputs.trim()) {
      try {
        parsedInputs = JSON.parse(inputs) as Record<string, unknown>
      } catch {
        setError('Inputs must be valid JSON.')
        return
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      await api.post('/api/v1/automations', {
        apiVersion: 'blackbeard/v1',
        kind: 'Automation',
        metadata: { name: name.toLowerCase().replace(/\s+/g, '-') },
        spec: {
          target: {
            kind: targetKind,
            name: targetName.toLowerCase().replace(/\s+/g, '-'),
          },
          trigger: {
            type: triggerType,
            ...(triggerType === 'cron' ? { cron: schedule } : {}),
          },
          ...(Object.keys(parsedInputs).length > 0 ? { inputs: parsedInputs } : {}),
          enabled,
        },
      })
      toasts.success(`Automation "${name}" created`)
      resetForm()
      onOpenChange(false)
      onCreated()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to create automation')
      setError(message)
      toasts.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  const cronPreview = useMemo(() => {
    if (triggerType !== 'cron' || !schedule.trim()) return null
    return describeCron(schedule)
  }, [triggerType, schedule])

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
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-semibold">Create Automation</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Schedule or trigger crew and flow executions automatically.
          </Dialog.Description>

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} className="mt-4">
            <fieldset disabled={submitting} className="space-y-4">
              {/* Name */}
              <div>
                <label htmlFor="automation-name" className="mb-1.5 block text-sm font-medium">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  id="automation-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  aria-required="true"
                  autoFocus
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="e.g. nightly-research"
                />
              </div>

              {/* Target */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="automation-target-kind"
                    className="mb-1.5 block text-sm font-medium"
                  >
                    Target kind <span className="text-destructive">*</span>
                  </label>
                  <select
                    id="automation-target-kind"
                    value={targetKind}
                    onChange={(e) => setTargetKind(e.target.value)}
                    aria-required="true"
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="Crew">Crew</option>
                    <option value="Flow">Flow</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="automation-target-name"
                    className="mb-1.5 block text-sm font-medium"
                  >
                    Target name <span className="text-destructive">*</span>
                  </label>
                  <input
                    id="automation-target-name"
                    type="text"
                    value={targetName}
                    onChange={(e) => setTargetName(e.target.value)}
                    required
                    aria-required="true"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    placeholder="e.g. research-crew"
                  />
                </div>
              </div>

              {/* Trigger type */}
              <div>
                <label htmlFor="automation-trigger" className="mb-1.5 block text-sm font-medium">
                  Trigger type <span className="text-destructive">*</span>
                </label>
                <select
                  id="automation-trigger"
                  value={triggerType}
                  onChange={(e) => setTriggerType(e.target.value)}
                  aria-required="true"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="cron">Cron (scheduled)</option>
                  <option value="webhook">Webhook</option>
                  <option value="api">API</option>
                </select>
              </div>

              {/* Cron schedule */}
              {triggerType === 'cron' && (
                <div>
                  <label htmlFor="automation-schedule" className="mb-1.5 block text-sm font-medium">
                    Cron expression <span className="text-destructive">*</span>
                  </label>
                  <input
                    id="automation-schedule"
                    type="text"
                    value={schedule}
                    onChange={(e) => setSchedule(e.target.value)}
                    required
                    aria-required="true"
                    autoComplete="off"
                    spellCheck={false}
                    aria-describedby={
                      cronPreview && cronPreview !== schedule
                        ? 'automation-schedule-preview'
                        : undefined
                    }
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    placeholder="0 9 * * 1-5"
                  />
                  <p id="automation-schedule-tz" className="mt-1.5 text-xs text-muted-foreground">
                    Cron expressions are evaluated in UTC.
                  </p>
                  {cronPreview && cronPreview !== schedule && (
                    <p
                      id="automation-schedule-preview"
                      className="mt-1.5 text-xs text-muted-foreground"
                      aria-live="polite"
                    >
                      Runs: {cronPreview}
                    </p>
                  )}
                </div>
              )}

              {/* Webhook info */}
              {triggerType === 'webhook' && (
                <div className="rounded-md border bg-muted/20 px-3 py-2.5 text-sm text-muted-foreground">
                  <p>
                    A webhook URL and secret will be generated after creation. Use them to trigger
                    this automation from external services.
                  </p>
                </div>
              )}

              {/* API info */}
              {triggerType === 'api' && (
                <div className="rounded-md border bg-muted/20 px-3 py-2.5 text-sm text-muted-foreground">
                  <p>
                    Trigger this automation via the API using{' '}
                    <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                      POST /api/v1/automations/&#123;name&#125;/trigger
                    </code>
                  </p>
                </div>
              )}

              {/* Inputs */}
              <div>
                <label htmlFor="automation-inputs" className="mb-1.5 block text-sm font-medium">
                  Default inputs (JSON)
                </label>
                <textarea
                  id="automation-inputs"
                  value={inputs}
                  onChange={(e) => setInputs(e.target.value)}
                  rows={3}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder='{"topic": "AI safety"}'
                />
              </div>

              {/* Enabled */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Enabled</span>
                <EnabledToggle
                  enabled={enabled}
                  onChange={setEnabled}
                  label="Enable automation on creation"
                />
              </div>

              {/* Actions */}
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
                  Create Automation
                </button>
              </div>
            </fieldset>
          </form>

          <Dialog.Close asChild>
            <button
              type="button"
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/* ------------------------------------------------------------------ */
/* Webhook details (inline expandable)                                 */
/* ------------------------------------------------------------------ */

function WebhookDetails({ url, secret }: { url?: string; secret?: string }) {
  const { copied: copiedUrl, copy: copyUrl } = useCopyToClipboard()
  const { copied: copiedSecret, copy: copySecret } = useCopyToClipboard()

  if (!url && !secret) return null

  return (
    <div className="mt-2 space-y-1.5">
      <span className="sr-only" role="status" aria-live="polite">
        {copiedUrl ? 'Webhook URL copied' : copiedSecret ? 'Webhook secret copied' : ''}
      </span>
      {url && (
        <div className="flex items-center gap-2">
          <code
            className="flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-xs"
            title={url}
          >
            {url}
          </code>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              void copyUrl(url)
            }}
            aria-label={copiedUrl ? 'Webhook URL copied' : 'Copy webhook URL'}
            className="flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {copiedUrl ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      )}
      {secret && (
        <div className="flex items-center gap-2">
          <code
            className="flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-xs"
            title={secret}
          >
            {secret}
          </code>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              void copySecret(secret)
            }}
            aria-label={copiedSecret ? 'Webhook secret copied' : 'Copy webhook secret'}
            className="flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {copiedSecret ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

const TABLE_HEADERS = [
  'Name',
  'Target',
  'Trigger',
  'Schedule',
  'Status',
  'Updated',
  'Actions',
] as const

export default function Automations() {
  const [automations, setAutomations] = useState<AutomationRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AutomationRecord | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [triggeringName, setTriggeringName] = useState<string | null>(null)
  const [togglingName, setTogglingName] = useState<string | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const toasts = useToastStore()

  useDocumentTitle('Automations')

  const fetchAutomations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<AutomationListResponse>('/api/v1/automations')
      setAutomations(
        result.items.map((r) => ({
          id: r.id,
          name: r.metadata.name,
          spec: r.spec,
          created_at: r.created_at,
          updated_at: r.updated_at,
          version: r.version,
        })),
      )
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load automations'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchAutomations()
  }, [fetchAutomations])

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/api/v1/automations/${deleteTarget.name}`)
      toasts.success(`Automation "${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      void fetchAutomations()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to delete automation')
      toasts.error(message)
    } finally {
      setDeleting(false)
    }
  }

  const handleTrigger = async (name: string) => {
    setTriggeringName(name)
    try {
      await api.post(`/api/v1/automations/${name}/trigger`, {})
      toasts.info(`Automation "${name}" started — view results in Executions`)
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to trigger automation')
      toasts.error(message)
    } finally {
      setTriggeringName(null)
    }
  }

  const handleToggleEnabled = async (automation: AutomationRecord) => {
    setTogglingName(automation.name)
    try {
      await api.put(`/api/v1/automations/${automation.name}`, {
        metadata: { name: automation.name },
        spec: {
          ...automation.spec,
          enabled: !automation.spec.enabled,
        },
        version: automation.version,
      })
      toasts.success(
        `Automation "${automation.name}" ${automation.spec.enabled ? 'disabled' : 'enabled'}`,
      )
      void fetchAutomations()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to update automation status')
      toasts.error(message)
    } finally {
      setTogglingName(null)
    }
  }

  const filtered = useMemo(() => {
    if (!search.trim()) return automations
    const q = caseFold(search)
    return automations.filter(
      (a) =>
        caseFold(a.name).includes(q) ||
        caseFold(a.spec.target_name ?? '').includes(q) ||
        caseFold(a.spec.trigger_type ?? '').includes(q),
    )
  }, [automations, search])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Automations"
            description="Scheduled and triggered crew/flow executions"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => void fetchAutomations()}
                  disabled={loading}
                  aria-label="Refresh automations"
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
                  onClick={() => setCreateOpen(true)}
                  className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-4 w-4" />
                  Create Automation
                </button>
              </>
            }
          />
        </div>

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchAutomations()}
            ariaLabel="Retry loading automations"
            className="mb-4"
          />
        )}

        {/* Search */}
        {automations.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <label htmlFor="automations-search" className="sr-only">
                Search automations
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                ref={searchRef}
                id="automations-search"
                type="search"
                placeholder="Search automations…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            {search && (
              <>
                <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
                  {filtered.length} of {automations.length} automations
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setSearch('')
                    searchRef.current?.focus()
                  }}
                  aria-label="Clear search"
                  className="inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                  Clear search
                </button>
              </>
            )}
          </div>
        )}

        {/* Content */}
        {loading && automations.length === 0 ? (
          <TableSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Timer />}
            title={search ? 'No automations match your search' : 'No automations yet'}
            description={
              search ? 'Try a different search term' : 'Create one to schedule crew executions'
            }
            action={
              !search
                ? { label: 'Create Automation', onClick: () => setCreateOpen(true) }
                : undefined
            }
          />
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="max-h-[calc(100vh-16rem)] overflow-auto">
              <table className="w-full min-w-[640px] text-sm" aria-label="Automations">
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
                  {filtered.map((automation) => {
                    const isToggling = togglingName === automation.name
                    const isTriggering = triggeringName === automation.name
                    return (
                      <tr
                        key={automation.id}
                        className="group border-l-2 border-l-transparent transition-colors duration-150 hover:border-l-primary hover:bg-accent/50"
                      >
                        {/* Name */}
                        <td className="px-4 py-3 font-medium">{automation.name}</td>

                        {/* Target */}
                        <td className="px-4 py-3 text-muted-foreground">
                          <span className="inline-flex items-center gap-1">
                            <span className="text-xs font-medium uppercase text-muted-foreground/60">
                              {automation.spec.target_kind ?? 'Crew'}
                            </span>
                            <span>/</span>
                            <span>{automation.spec.target_name ?? '—'}</span>
                          </span>
                        </td>

                        {/* Trigger */}
                        <td className="px-4 py-3">
                          <TriggerBadge type={automation.spec.trigger_type ?? 'cron'} />
                        </td>

                        {/* Schedule */}
                        <td className="px-4 py-3 text-muted-foreground">
                          {automation.spec.trigger_type === 'cron' && automation.spec.schedule ? (
                            <span title={automation.spec.schedule}>
                              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                                {automation.spec.schedule}
                              </code>
                              <span className="ml-1.5 text-xs text-muted-foreground/70">
                                ({describeCron(automation.spec.schedule)})
                              </span>
                            </span>
                          ) : automation.spec.trigger_type === 'webhook' ? (
                            <WebhookDetails
                              url={automation.spec.webhook_url}
                              secret={automation.spec.webhook_secret}
                            />
                          ) : (
                            <>
                              <span aria-hidden="true">{'—'}</span>
                              <span className="sr-only">Not applicable</span>
                            </>
                          )}
                        </td>

                        {/* Status (enabled toggle) */}
                        <td className="px-4 py-3">
                          <EnabledToggle
                            enabled={automation.spec.enabled !== false}
                            onChange={() => void handleToggleEnabled(automation)}
                            disabled={isToggling}
                            label={`${automation.spec.enabled !== false ? 'Disable' : 'Enable'} automation ${automation.name}`}
                          />
                        </td>

                        {/* Updated */}
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDate(automation.updated_at)}
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                void handleTrigger(automation.name)
                              }}
                              disabled={isTriggering}
                              aria-label={`Trigger automation ${automation.name} now`}
                              aria-busy={isTriggering || undefined}
                              title="Trigger now"
                              className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isTriggering ? (
                                <Spinner size="sm" label="Triggering" />
                              ) : (
                                <Play className="h-3.5 w-3.5" />
                              )}
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteTarget(automation)
                              }}
                              aria-label={`Delete automation ${automation.name}`}
                              title="Delete"
                              className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Create dialog */}
        <CreateAutomationDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={() => void fetchAutomations()}
        />

        {/* Delete confirmation */}
        <ConfirmDialog
          open={deleteTarget !== null}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null)
          }}
          title="Delete automation"
          description={`Are you sure you want to delete the automation "${deleteTarget?.name ?? ''}"? This action cannot be undone.`}
          confirmLabel="Delete"
          confirmVariant="destructive"
          onConfirm={() => void handleDelete()}
          loading={deleting}
        />
      </div>
    </div>
  )
}
