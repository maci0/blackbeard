import { useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Play, ChevronRight, RefreshCw, AlertTriangle, ArrowRight } from 'lucide-react'
import { useExecutionStore } from '@/stores/executionStore'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Spinner } from '@/components/ui/Spinner'
import { formatDate, getDuration, formatCost } from '@/lib/formatters'
import { TERMINAL_STATUSES } from '@/lib/kinds'

export default function Executions() {
  const navigate = useNavigate()
  const { executions, loading, error, fetchExecutions } = useExecutionStore()
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadExecutions = () => fetchExecutions()

  useEffect(() => {
    loadExecutions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-refresh every 5s if any execution is still running
  useEffect(() => {
    const hasRunning = executions.some((e) => !TERMINAL_STATUSES.has(e.status))

    if (hasRunning && !intervalRef.current) {
      intervalRef.current = setInterval(() => {
        fetchExecutions()
      }, 5000)
    } else if (!hasRunning && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executions])

  const hasRunning = executions.some((e) => !TERMINAL_STATUSES.has(e.status))

  useEffect(() => {
    document.title = 'Executions | Blackbeard'
    return () => { document.title = 'Blackbeard' }
  }, [])

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Executions</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {executions.length > 0
                ? `${executions.length} execution${executions.length !== 1 ? 's' : ''}`
                : 'Crew run history and status'}
              {hasRunning && (
                <span className="ml-2 inline-flex items-center gap-1 text-blue-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse motion-reduce:animate-none" />
                  Auto-refreshing
                </span>
              )}
            </p>
          </div>
          <button
            onClick={loadExecutions}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md bg-background hover:bg-accent transition-colors"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin motion-reduce:animate-none')} />
            Refresh
          </button>
        </div>

        {/* Error */}
        {error && (
          <div role="alert" className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center justify-between">
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </span>
            <button onClick={loadExecutions} className="text-xs underline underline-offset-2">
              Retry
            </button>
          </div>
        )}

        {/* Table */}
        <div className="border rounded-lg overflow-hidden bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Executions">
              <thead>
                <tr className="border-b bg-muted/40">
                  {['Status', 'Crew', 'Tokens', 'Cost', 'Created', 'Duration'].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading && executions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-16 text-center text-muted-foreground">
                      <div className="flex items-center justify-center gap-2">
                        <Spinner size="sm" className="text-muted-foreground" />
                        <span className="text-sm">Loading executions…</span>
                      </div>
                    </td>
                  </tr>
                ) : executions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-16 text-center">
                      <Play className="h-8 w-8 text-muted-foreground/30 mx-auto mb-3" />
                      <p className="font-medium text-muted-foreground">No executions yet</p>
                      <p className="text-sm text-muted-foreground/70 mt-1">
                        Run a crew from the Studio to see results here
                      </p>
                      <Link
                        to="/studio"
                        className="inline-flex items-center gap-1.5 mt-3 text-sm text-primary hover:underline underline-offset-2"
                      >
                        Go to Studio
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </td>
                  </tr>
                ) : (
                  executions.map((execution) => (
                    <tr
                      key={execution.id}
                      onClick={() => navigate(`/executions/${execution.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          navigate(`/executions/${execution.id}`)
                        }
                      }}
                      tabIndex={0}
                      role="row"
                      className="border-b last:border-0 hover:bg-muted/40 cursor-pointer transition-colors group focus-visible:outline-none focus-visible:bg-muted/60 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    >
                      <td className="px-4 py-3">
                        <StatusBadge status={execution.status} />
                      </td>
                      <td className="px-4 py-3 font-medium">{execution.crew_name}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {execution.total_tokens > 0
                          ? execution.total_tokens.toLocaleString()
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                        {formatCost(execution.cost_usd)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(execution.created_at)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                        {getDuration(execution.started_at, execution.completed_at)}
                      </td>
                      <td className="px-4 py-3">
                        <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
