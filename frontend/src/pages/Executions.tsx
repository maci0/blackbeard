import { useEffect, useMemo, useCallback, useState, useRef, useDeferredValue } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  ChevronRight,
  RefreshCw,
  Search,
  X,
  ArrowUpDown,
  Activity,
  Coins,
  Hash,
  Cpu,
  GitCompareArrows,
} from 'lucide-react'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useNotifications } from '@/hooks/useNotifications'
import { usePolling } from '@/hooks/usePolling'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { useShallow } from 'zustand/react/shallow'
import { useExecutionStore } from '@/stores/executionStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { TERMINAL_STATUSES } from '@/lib/types'
import type { Execution } from '@/lib/types'
import { caseFold, cn, compareStrings } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { getDuration, formatCost, formatCostZero, parseCost } from '@/lib/formatters'
import { SmartTime } from '@/components/ui/SmartTime'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 25

const TABLE_HEADERS = [
  '',
  'Status',
  'Crew',
  'Type',
  'Tokens',
  'Cost',
  'Created',
  'Duration',
] as const

const STATUS_OPTIONS = ['all', 'running', 'completed', 'failed', 'cancelled', 'queued'] as const
type StatusFilter = (typeof STATUS_OPTIONS)[number]

const TYPE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'All', value: 'all' },
  { label: 'Kickoff', value: 'kickoff' },
  { label: 'Train', value: 'train' },
  { label: 'Test', value: 'test' },
  { label: 'Flow', value: 'flow' },
]

type SortField = 'created_at' | 'status' | 'crew_name'
type SortDir = 'asc' | 'desc'

const SORT_FIELD_MAP: Partial<Record<(typeof TABLE_HEADERS)[number], SortField>> = {
  Status: 'status',
  Crew: 'crew_name',
  Created: 'created_at',
}

function compareExecutions(a: Execution, b: Execution, field: SortField, dir: SortDir): number {
  let cmp = 0
  switch (field) {
    case 'created_at':
      cmp = a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0
      break
    case 'status':
      cmp = compareStrings(a.status, b.status)
      break
    case 'crew_name':
      cmp = compareStrings(a.crew_name, b.crew_name)
      break
  }
  return dir === 'asc' ? cmp : -cmp
}

export default function Executions() {
  const navigate = useNavigate()
  const { executions, executionsTotal, loading, error, fetchExecutions } = useExecutionStore(
    useShallow((s) => ({
      executions: s.executions,
      executionsTotal: s.executionsTotal,
      loading: s.loading,
      error: s.error,
      fetchExecutions: s.fetchExecutions,
    })),
  )

  const [page, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil(executionsTotal / PAGE_SIZE))

  const loadExecutions = useCallback(
    () => void fetchExecutions(undefined, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    [fetchExecutions, page],
  )

  useEffect(() => {
    void fetchExecutions(undefined, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
  }, [fetchExecutions, page])

  const hasRunning = useMemo(
    () => executions.some((e) => !TERMINAL_STATUSES.has(e.status)),
    [executions],
  )

  const pollExecutions = useExecutionStore((state) => state.pollExecutions)
  const doPoll = useCallback(
    () => pollExecutions(undefined, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    [pollExecutions, page],
  )
  usePolling(doPoll, 5000, hasRunning)

  const { notify } = useNotifications()
  const addNotification = useNotificationStore((s) => s.add)

  const prevStatuses = useRef(new Map<string, string>())
  useEffect(() => {
    for (const e of executions) {
      const prev = prevStatuses.current.get(e.id)
      if (prev && !TERMINAL_STATUSES.has(prev) && TERMINAL_STATUSES.has(e.status)) {
        const title =
          e.status === 'completed'
            ? `Crew "${e.crew_name}" completed`
            : `Crew "${e.crew_name}" ${e.status}`
        const body =
          e.status === 'completed'
            ? `Used ${e.total_tokens.toLocaleString()} tokens`
            : (e.error ?? `Execution ${e.status}`)
        notify(title, body)
        addNotification(title, body)
      }
      prevStatuses.current.set(e.id, e.status)
    }
  }, [executions, notify, addNotification])

  useDocumentTitle('Executions')

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [crewSearch, setCrewSearch] = useState('')
  const deferredCrewSearch = useDeferredValue(crewSearch)
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const crewSearchRef = useRef<HTMLInputElement>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])

  const toggleCompare = useCallback((id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 2) return [prev[1]!, id]
      return [...prev, id]
    })
  }, [])

  const activeFilterCount = useMemo(() => {
    let count = 0
    if (statusFilter !== 'all') count++
    if (typeFilter !== 'all') count++
    if (crewSearch) count++
    return count
  }, [statusFilter, typeFilter, crewSearch])

  function clearFilters() {
    setStatusFilter('all')
    setTypeFilter('all')
    setCrewSearch('')
    setPage(1)
    crewSearchRef.current?.focus()
  }

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir(field === 'created_at' ? 'desc' : 'asc')
    }
  }

  const stats = useMemo(() => {
    let runningQueued = 0
    let totalCost = 0
    let totalTokens = 0
    for (const e of executions) {
      if (e.status === 'running' || e.status === 'queued') runningQueued++
      totalCost += parseCost(e.cost_usd)
      totalTokens += e.total_tokens
    }
    return { runningQueued, totalCost, totalTokens }
  }, [executions])

  const filtered = useMemo(() => {
    const searchLower = deferredCrewSearch ? caseFold(deferredCrewSearch) : ''
    const result = executions.filter((e) => {
      if (statusFilter !== 'all' && e.status !== statusFilter) return false
      if (typeFilter !== 'all' && e.execution_type !== typeFilter) return false
      if (searchLower && !caseFold(e.crew_name).includes(searchLower)) return false
      return true
    })
    result.sort((a, b) => compareExecutions(a, b, sortField, sortDir))
    return result
  }, [executions, statusFilter, typeFilter, deferredCrewSearch, sortField, sortDir])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Executions"
            description={
              executionsTotal > 0
                ? `${executionsTotal} execution${executionsTotal !== 1 ? 's' : ''}`
                : 'Crew run history and status'
            }
            actions={
              <button
                type="button"
                onClick={loadExecutions}
                disabled={loading}
                aria-label="Refresh executions"
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
            }
          />
          {hasRunning && (
            <p className="mt-1 text-sm" role="status" aria-live="polite">
              <span className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500 motion-reduce:animate-none"
                />
                Auto-refreshing every 5s
              </span>
            </p>
          )}
        </div>

        {executions.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-3" role="region" aria-label="Execution summary">
            <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-sm">
              <Hash className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              <span className="text-sm text-muted-foreground">Total</span>
              <span className="text-sm font-semibold tabular-nums">{executions.length}</span>
            </div>
            <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-sm">
              <Activity className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
              <span className="text-sm text-muted-foreground">Active</span>
              <span className="text-sm font-semibold tabular-nums">{stats.runningQueued}</span>
            </div>
            <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-sm">
              <Coins className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
              <span className="text-sm text-muted-foreground">Spend</span>
              <span className="font-mono text-sm font-semibold tabular-nums">
                {formatCost(stats.totalCost) === '—'
                  ? formatCostZero()
                  : formatCost(stats.totalCost)}
              </span>
            </div>
            <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 shadow-sm">
              <Cpu className="h-3.5 w-3.5 text-purple-500" aria-hidden="true" />
              <span className="text-sm text-muted-foreground">Tokens</span>
              <span className="text-sm font-semibold tabular-nums">
                {stats.totalTokens.toLocaleString()}
              </span>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={loadExecutions}
            ariaLabel="Retry loading executions"
            className="mb-4"
          />
        )}

        {executions.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[180px] max-w-xs flex-1">
              <label htmlFor="executions-crew-search" className="sr-only">
                Search by crew name
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                ref={crewSearchRef}
                id="executions-crew-search"
                type="search"
                placeholder="Filter by crew name…"
                value={crewSearch}
                onChange={(e) => setCrewSearch(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <label htmlFor="executions-status-filter" className="sr-only">
              Filter by status
            </label>
            <select
              id="executions-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === 'all' ? 'All statuses' : s.charAt(0).toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>
            <label htmlFor="executions-type-filter" className="sr-only">
              Filter by type
            </label>
            <select
              id="executions-type-filter"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {TYPE_OPTIONS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.value === 'all' ? 'All types' : t.label}
                </option>
              ))}
            </select>
            <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {filtered.length} of {executions.length}
            </span>
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={clearFilters}
                aria-label="Clear all filters"
                className="inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-3.5 w-3.5" />
                Clear filters ({activeFilterCount})
              </button>
            )}
            <div className="ml-auto flex items-center gap-2">
              {compareIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setCompareIds([])}
                  aria-label="Clear comparison selection"
                  className="text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Clear ({compareIds.length})
                </button>
              )}
              <button
                type="button"
                disabled={compareIds.length !== 2}
                onClick={() =>
                  void navigate(`/executions/compare?a=${compareIds[0]}&b=${compareIds[1]}`)
                }
                aria-label="Compare selected executions"
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  compareIds.length === 2
                    ? 'bg-primary text-primary-foreground hover:opacity-90'
                    : 'border bg-background text-muted-foreground opacity-50',
                )}
              >
                <GitCompareArrows className="h-3.5 w-3.5" />
                Compare{compareIds.length > 0 ? ` (${compareIds.length}/2)` : ''}
              </button>
            </div>
          </div>
        )}

        {loading && executions.length === 0 ? (
          <TableSkeleton />
        ) : executions.length === 0 ? (
          <EmptyState
            icon={<Play />}
            title="No executions yet"
            description="Run a crew from the Studio to see results here"
            action={{ label: 'Go to Studio', href: '/studio' }}
          />
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
              <div className="max-h-[calc(100vh-16rem)] overflow-auto">
                <table className="w-full min-w-[640px] text-sm" aria-label="Executions">
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b bg-muted/60">
                      {TABLE_HEADERS.map((h, hi) => {
                        if (hi === 0) {
                          return (
                            <th key="compare" scope="col" className="w-10 px-2 py-3">
                              <span className="sr-only">Select for comparison</span>
                            </th>
                          )
                        }
                        const field = SORT_FIELD_MAP[h]
                        const isSorted = field && sortField === field
                        return (
                          <th
                            key={h}
                            scope="col"
                            className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                          >
                            {field ? (
                              <button
                                type="button"
                                onClick={() => toggleSort(field)}
                                aria-label={`Sort by ${h}${isSorted ? (sortDir === 'asc' ? ', currently ascending' : ', currently descending') : ''}`}
                                className="inline-flex items-center gap-1 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              >
                                {h}
                                <ArrowUpDown
                                  className={cn(
                                    'h-3 w-3',
                                    isSorted ? 'text-foreground' : 'text-muted-foreground/40',
                                  )}
                                />
                              </button>
                            ) : (
                              h
                            )}
                          </th>
                        )
                      })}
                      <th scope="col" className="w-8 px-4 py-3">
                        <span className="sr-only">Details</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filtered.length === 0 ? (
                      <tr>
                        <td
                          colSpan={TABLE_HEADERS.length + 1}
                          className="px-4 py-12 text-center text-sm text-muted-foreground"
                        >
                          No executions match your filters.{' '}
                          <button
                            type="button"
                            onClick={clearFilters}
                            className="text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            Clear filters
                          </button>
                        </td>
                      </tr>
                    ) : (
                      filtered.map((execution) => (
                        <tr
                          key={execution.id}
                          onClick={() => void navigate(`/executions/${execution.id}`)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              void navigate(`/executions/${execution.id}`)
                            }
                          }}
                          tabIndex={0}
                          role="row"
                          aria-label={`${execution.crew_name} — ${execution.status} — press Enter to view details`}
                          className={cn(
                            'group cursor-pointer border-l-2 border-l-transparent transition-all duration-150 hover:border-l-primary hover:bg-accent/50 focus-visible:border-l-primary focus-visible:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                            compareIds.includes(execution.id) && 'bg-primary/5',
                          )}
                        >
                          <td className="px-2 py-3">
                            <input
                              type="checkbox"
                              checked={compareIds.includes(execution.id)}
                              onChange={() => toggleCompare(execution.id)}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`Select ${execution.crew_name} for comparison`}
                              className="h-4 w-4 rounded border-gray-300 text-primary accent-primary focus-visible:ring-2 focus-visible:ring-ring"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <StatusBadge status={execution.status} />
                          </td>
                          <td className="px-4 py-3 font-medium">{execution.crew_name}</td>
                          <td className="px-4 py-3 text-xs capitalize text-muted-foreground">
                            {execution.execution_type}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {execution.total_tokens > 0 ? (
                              execution.total_tokens.toLocaleString()
                            ) : (
                              <>
                                <span aria-hidden="true">--</span>
                                <span className="sr-only">No tokens recorded</span>
                              </>
                            )}
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                            {Number(execution.cost_usd) > 0 ? (
                              formatCost(execution.cost_usd)
                            ) : (
                              <>
                                <span aria-hidden="true">--</span>
                                <span className="sr-only">No cost recorded</span>
                              </>
                            )}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">
                            <SmartTime date={execution.created_at} />
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                            {execution.started_at ? (
                              getDuration(execution.started_at, execution.completed_at)
                            ) : (
                              <>
                                <span aria-hidden="true">--</span>
                                <span className="sr-only">Not started</span>
                              </>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <ChevronRight
                              aria-hidden="true"
                              className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
                            />
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        )}
      </div>
    </div>
  )
}
