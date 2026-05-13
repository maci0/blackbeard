import { useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, ChevronRight, RefreshCw, AlertTriangle } from 'lucide-react'
import { useDocumentTitle, usePolling } from '@/lib/hooks'
import { useExecutionStore, TERMINAL_STATUSES } from '@/stores/executionStore'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { formatDate, getDuration, formatCost } from '@/lib/formatters'

export default function Executions() {
  const navigate = useNavigate()
  const { executions, loading, error, fetchExecutions } = useExecutionStore()

  const loadExecutions = () => void fetchExecutions()

  useEffect(() => {
    loadExecutions()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  const hasRunning = useMemo(
    () => executions.some((e) => !TERMINAL_STATUSES.has(e.status)),
    [executions],
  )

  const pollExecutions = useExecutionStore((state) => state.pollExecutions)
  const doPoll = useCallback(() => pollExecutions(), [pollExecutions])
  usePolling(doPoll, 5000, hasRunning)

  useDocumentTitle('Executions')

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Executions"
            description={
              executions.length > 0
                ? `${executions.length} execution${executions.length !== 1 ? 's' : ''}`
                : 'Crew run history and status'
            }
            actions={
              <button
                onClick={loadExecutions}
                aria-label="Refresh executions"
                className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent"
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
            <p className="mt-1 text-sm">
              <span className="inline-flex items-center gap-1 text-blue-600">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500 motion-reduce:animate-none" />
                Auto-refreshing
              </span>
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="mb-4 flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
          >
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </span>
            <button
              onClick={loadExecutions}
              className="text-xs underline underline-offset-2"
              aria-label="Retry loading executions"
            >
              Retry
            </button>
          </div>
        )}

        {/* Table */}
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
          <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="Executions">
                <thead>
                  <tr className="border-b bg-muted/60">
                    {['Status', 'Crew', 'Tokens', 'Cost', 'Created', 'Duration'].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                    <th scope="col" className="w-8 px-4 py-3">
                      <span className="sr-only">Details</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {executions.map((execution) => (
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
                      className="group cursor-pointer transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    >
                      <td className="px-4 py-3">
                        <StatusBadge status={execution.status} />
                      </td>
                      <td className="px-4 py-3 font-medium">{execution.crew_name}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {execution.total_tokens > 0 ? (
                          execution.total_tokens.toLocaleString()
                        ) : (
                          <span aria-label="none">--</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {execution.cost_usd > 0 ? (
                          formatCost(execution.cost_usd)
                        ) : (
                          <span aria-label="none">--</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(execution.created_at)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {getDuration(execution.started_at, execution.completed_at)}
                      </td>
                      <td className="px-4 py-3">
                        <ChevronRight
                          aria-hidden="true"
                          className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
