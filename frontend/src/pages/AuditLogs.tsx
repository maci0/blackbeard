import { useState, useEffect, useCallback, useRef } from 'react'
import { ScrollText, RefreshCw, X, Search } from 'lucide-react'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle, usePolling } from '@/hooks'
import { SmartTime } from '@/components/ui/SmartTime'
import { Pagination } from '@/components/ui/Pagination'

interface AuditLogItem {
  id: string
  timestamp: string
  actor_type: string
  actor_id: string
  action: string
  resource_type: string | null
  resource_id: string | null
  detail: Record<string, unknown> | null
  request_id: string | null
}

interface AuditLogListResponse {
  items: AuditLogItem[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const ACTION_OPTIONS = [
  'resource_created',
  'resource_updated',
  'resource_deleted',
  'user_login',
] as const

const RESOURCE_TYPE_OPTIONS = [
  'Agent',
  'Task',
  'Crew',
  'Tool',
  'LLMConnection',
  'AgentPolicy',
  'Guardrail',
  'Flow',
  'KnowledgeSource',
  'Role',
  'RoleBinding',
  'Automation',
  'Project',
] as const

const PAGE_SIZE = 25

const TABLE_HEADERS = ['Timestamp', 'Action', 'Actor', 'Resource Type', 'Resource ID'] as const

const ACTION_LABELS: Record<string, string> = {
  resource_created: 'Created',
  resource_updated: 'Updated',
  resource_deleted: 'Deleted',
  user_login: 'Login',
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    resource_created: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
    resource_updated: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    resource_deleted: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    user_login: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  }
  const label =
    ACTION_LABELS[action] ?? action.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <span
      className={cn(
        'inline-flex rounded px-1.5 py-0.5 text-xs font-medium',
        colors[action] ?? 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200',
      )}
    >
      {label}
    </span>
  )
}

function DetailPopover({ detail }: { detail: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        aria-label="View details"
        aria-expanded={open}
        aria-haspopup="true"
        className="rounded px-1.5 py-0.5 text-xs text-muted-foreground underline underline-offset-2 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        details
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Entry details"
          className="absolute right-0 top-full z-20 mt-1 max-h-60 w-72 overflow-auto rounded-md border bg-card p-3 shadow-lg"
        >
          <pre className="whitespace-pre-wrap text-xs text-muted-foreground">
            {JSON.stringify(detail, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [actionFilter, setActionFilter] = useState('')
  const [resourceTypeFilter, setResourceTypeFilter] = useState('')
  const [actorSearch, setActorSearch] = useState('')
  const [debouncedActorSearch, setDebouncedActorSearch] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedActorSearch(actorSearch), 300)
    return () => clearTimeout(timer)
  }, [actorSearch])

  useDocumentTitle('Audit Logs')

  const loadLogs = useCallback(async () => {
    const params = new URLSearchParams()
    params.set('limit', String(PAGE_SIZE))
    params.set('offset', String(offset))
    if (actionFilter) params.set('action', actionFilter)
    if (resourceTypeFilter) params.set('resource_type', resourceTypeFilter)
    if (debouncedActorSearch.trim()) params.set('actor_id', debouncedActorSearch.trim())
    const result = await api.get<AuditLogListResponse>(`/api/v1/audit-logs?${params.toString()}`)
    setLogs(result.items)
    setTotal(result.total)
  }, [offset, actionFilter, resourceTypeFilter, debouncedActorSearch])

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await loadLogs()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load audit logs'))
    } finally {
      setLoading(false)
    }
  }, [loadLogs])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  const pollLogs = useCallback(async () => {
    try {
      await loadLogs()
    } catch (err) {
      console.warn('[audit-logs] polling failed:', err)
    }
  }, [loadLogs])

  usePolling(pollLogs, 10_000, autoRefresh)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  const handlePageChange = (newPage: number) => {
    setOffset((newPage - 1) * PAGE_SIZE)
  }

  const resetFilters = () => {
    setActionFilter('')
    setResourceTypeFilter('')
    setActorSearch('')
    setOffset(0)
  }

  const hasFilters = actionFilter !== '' || resourceTypeFilter !== '' || actorSearch.trim() !== ''

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <PageHeader
            title="Audit Logs"
            description={
              total > 0
                ? `${total.toLocaleString()} log ${total !== 1 ? 'entries' : 'entry'}`
                : 'Security audit trail'
            }
            actions={
              <>
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    className="h-3.5 w-3.5 accent-primary"
                  />
                  Auto-refresh
                </label>
                <button
                  type="button"
                  onClick={() => void fetchLogs()}
                  disabled={loading}
                  aria-label="Refresh audit logs"
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
              </>
            }
          />
          {autoRefresh && (
            <p className="mt-1 text-sm" role="status" aria-live="polite">
              <span className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500 motion-reduce:animate-none"
                />
                Auto-refreshing every 10s
              </span>
            </p>
          )}
        </div>

        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchLogs()}
            ariaLabel="Retry loading audit logs"
            className="mb-4"
          />
        )}

        <div className="mb-5 flex flex-wrap items-center gap-3">
          <div>
            <label htmlFor="audit-action-filter" className="sr-only">
              Filter by action
            </label>
            <select
              id="audit-action-filter"
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value)
                setOffset(0)
              }}
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">All actions</option>
              {ACTION_OPTIONS.map((a) => (
                <option key={a} value={a}>
                  {ACTION_LABELS[a] ?? a}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="audit-resource-type-filter" className="sr-only">
              Filter by resource type
            </label>
            <select
              id="audit-resource-type-filter"
              value={resourceTypeFilter}
              onChange={(e) => {
                setResourceTypeFilter(e.target.value)
                setOffset(0)
              }}
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">All resource types</option>
              {RESOURCE_TYPE_OPTIONS.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </select>
          </div>

          <div className="relative min-w-[180px]">
            <label htmlFor="audit-actor-search" className="sr-only">
              Search by actor ID
            </label>
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id="audit-actor-search"
              type="search"
              placeholder="Actor ID..."
              value={actorSearch}
              onChange={(e) => {
                setActorSearch(e.target.value)
                setOffset(0)
              }}
              autoComplete="off"
              className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          {hasFilters && (
            <button
              type="button"
              onClick={resetFilters}
              aria-label="Clear all filters"
              className="inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          )}
        </div>

        {loading && logs.length === 0 ? (
          <TableSkeleton />
        ) : logs.length === 0 ? (
          <EmptyState
            icon={<ScrollText />}
            title={hasFilters ? 'No matching audit logs' : 'No audit logs yet'}
            description={
              hasFilters
                ? 'Try adjusting your filters'
                : 'Audit entries will appear as actions are performed'
            }
            action={hasFilters ? { label: 'Clear filters', onClick: resetFilters } : undefined}
          />
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
              <div className="max-h-[calc(100vh-20rem)] overflow-auto">
                <table className="w-full min-w-[700px] text-sm" aria-label="Audit logs">
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
                      <th scope="col" className="w-16 px-4 py-3">
                        <span className="sr-only">Details</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {logs.map((entry) => (
                      <tr
                        key={entry.id}
                        className="border-l-2 border-l-transparent transition-colors duration-150 hover:border-l-primary hover:bg-accent/50"
                      >
                        <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                          <SmartTime date={entry.timestamp} />
                        </td>
                        <td className="px-4 py-3">
                          <ActionBadge action={entry.action} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col">
                            <span className="text-xs text-muted-foreground">
                              {entry.actor_type}
                            </span>
                            <span
                              className="max-w-[200px] truncate font-mono text-xs"
                              title={entry.actor_id}
                            >
                              {entry.actor_id}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {entry.resource_type ?? (
                            <>
                              <span aria-hidden="true">--</span>
                              <span className="sr-only">None</span>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {entry.resource_id ? (
                            <span
                              className="max-w-[200px] truncate font-mono text-xs"
                              title={entry.resource_id}
                            >
                              {entry.resource_id}
                            </span>
                          ) : (
                            <>
                              <span aria-hidden="true" className="text-muted-foreground">
                                --
                              </span>
                              <span className="sr-only">None</span>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {entry.detail && Object.keys(entry.detail).length > 0 && (
                            <DetailPopover detail={entry.detail} />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <Pagination
              page={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
            />
          </>
        )}
      </div>
    </div>
  )
}
