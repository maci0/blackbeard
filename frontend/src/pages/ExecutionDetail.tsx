import { useEffect, useCallback, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  ExternalLink,
  XCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Coins,
  DollarSign,
  Activity,
} from 'lucide-react'
import { useExecutionStore, type ExecutionTask } from '@/stores/executionStore'
import { StatusBadge, statusLabel } from '@/components/ui/StatusBadge'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { getDuration, formatDate } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import { TERMINAL_STATUSES } from '@/lib/kinds'

/* ------------------------------------------------------------------ */
/* Summary card                                                        */
/* ------------------------------------------------------------------ */

function SummaryCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="border rounded-lg bg-card p-4 flex items-start gap-3">
      <div className="p-2 rounded-md bg-muted">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
        <p className="text-lg font-semibold mt-0.5 tabular-nums">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Task row                                                            */
/* ------------------------------------------------------------------ */

function TaskRow({ task, index }: { task: ExecutionTask; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const needsExpand =
    (task.output?.split('\n').length ?? 0) > 4 || (task.output?.length ?? 0) > 400

  return (
    <div className="border rounded-lg bg-card overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-muted/20">
        <span className="w-6 h-6 rounded-full border text-xs font-semibold flex items-center justify-center text-muted-foreground bg-background shrink-0">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{task.task_name}</p>
          {task.agent_name && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Agent: <span className="font-medium">{task.agent_name}</span>
            </p>
          )}
        </div>
        <StatusBadge status={task.status} />
      </div>

      {task.output && (
        <div className="px-4 py-3">
          <p className="text-xs font-medium text-muted-foreground mb-1.5">Output</p>
          <p
            className={cn(
              'text-sm text-muted-foreground whitespace-pre-wrap',
              !expanded && 'line-clamp-4',
            )}
          >
            {task.output}
          </p>
          {needsExpand && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-xs text-primary hover:underline mt-1"
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {task.error && (
        <div className="px-4 py-3 bg-destructive/5 border-t border-destructive/20">
          <p className="text-xs font-medium text-destructive mb-1">Error</p>
          <p className="text-sm text-destructive/80 font-mono whitespace-pre-wrap">{task.error}</p>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function ExecutionDetail() {
  const { id = '' } = useParams<{ id: string }>()
  const { currentExecution, loading, error, fetchExecution, cancelExecution } =
    useExecutionStore()
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)

  const load = useCallback(async () => {
    await fetchExecution(id)
  }, [id, fetchExecution])

  useEffect(() => {
    fetchExecution(id)

    intervalRef.current = setInterval(async () => {
      await fetchExecution(id)
      const exec = useExecutionStore.getState().currentExecution
      if (exec && TERMINAL_STATUSES.has(exec.status)) {
        clearInterval(intervalRef.current!)
      }
    }, 2000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- Document title ---- */
  useEffect(() => {
    document.title = currentExecution
      ? `${currentExecution.crew_name} run | Blackbeard`
      : 'Execution | Blackbeard'
    return () => { document.title = 'Blackbeard' }
  }, [currentExecution])

  /* ---- Loading ---- */
  if (loading && !currentExecution) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="sm" className="text-muted-foreground" />
          <span className="text-sm">Loading execution…</span>
        </div>
      </div>
    )
  }

  if (error || !currentExecution) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-3" />
          <p className="font-medium">{error ?? 'Execution not found'}</p>
          <div className="flex items-center gap-2 justify-center mt-4">
            <button
              onClick={load}
              className="px-4 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
            >
              Retry
            </button>
            <Link
              to="/executions"
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 transition-opacity"
            >
              Back to Executions
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const execution = currentExecution
  const isActive = !TERMINAL_STATUSES.has(execution.status)
  const sortedTasks = [...(execution.tasks ?? [])].sort((a, b) => a.order - b.order)

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-4xl mx-auto">

        {/* Back */}
        <Link
          to="/executions"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-5"
        >
          <ArrowLeft className="h-4 w-4" />
          Executions
        </Link>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-3 flex-wrap mb-1.5">
              <StatusBadge status={execution.status} />
              <h1 className="text-2xl font-semibold tracking-tight">
                <Link
                  to={`/resources/crews/${execution.crew_name}`}
                  className="hover:underline"
                >
                  {execution.crew_name}
                </Link>
              </h1>
            </div>
            <p className="text-xs font-mono text-muted-foreground">{execution.id}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {execution.langfuse_trace_url && (
              <a
                href={execution.langfuse_trace_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View in Langfuse
              </a>
            )}
            {isActive && (
              <button
                onClick={() => setShowCancelConfirm(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border border-destructive/30 text-destructive rounded-md hover:bg-destructive/10 transition-colors"
              >
                <XCircle className="h-3.5 w-3.5" />
                Cancel
              </button>
            )}
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <SummaryCard
            icon={Activity}
            label="Status"
            value={statusLabel(execution.status)}
            sub={formatDate(execution.started_at)}
          />
          <SummaryCard
            icon={Coins}
            label="Total tokens"
            value={execution.total_tokens > 0 ? execution.total_tokens.toLocaleString() : '—'}
          />
          <SummaryCard
            icon={DollarSign}
            label="Cost"
            value={
              execution.cost_usd > 0 ? `$${execution.cost_usd.toFixed(4)}` : '—'
            }
          />
          <SummaryCard
            icon={Clock}
            label="Duration"
            value={getDuration(execution.started_at, execution.completed_at)}
            sub={isActive ? 'In progress' : undefined}
          />
        </div>

        {/* Error banner */}
        {execution.status === 'failed' && execution.error && (
          <div role="alert" className="mb-6 border border-destructive/30 rounded-lg bg-destructive/5 p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-destructive">Execution failed</p>
                <p className="text-sm text-destructive/80 mt-1 font-mono whitespace-pre-wrap">
                  {execution.error}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tasks */}
        {sortedTasks.length > 0 && (
          <div>
            <h2 className="text-base font-semibold mb-3 flex items-center gap-2">
              Tasks
              <span className="text-xs font-normal text-muted-foreground">
                ({sortedTasks.length})
              </span>
            </h2>
            <div className="space-y-3">
              {sortedTasks.map((task, idx) => (
                <TaskRow key={task.id} task={task} index={idx} />
              ))}
            </div>
          </div>
        )}

        {/* Outputs */}
        {execution.outputs && Object.keys(execution.outputs).length > 0 && (
          <div className="mt-6">
            <h2 className="text-base font-semibold mb-3 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Outputs
            </h2>
            <div className="border rounded-lg bg-muted/20 p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">
                {JSON.stringify(execution.outputs, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Footer meta */}
        <div className="mt-8 pt-4 border-t flex items-center gap-6 text-xs text-muted-foreground">
          <span>Created: {formatDate(execution.created_at)}</span>
          {execution.completed_at && <span>Completed: {formatDate(execution.completed_at)}</span>}
          {execution.crew_namespace && execution.crew_namespace !== 'default' && (
            <span>Namespace: {execution.crew_namespace}</span>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title="Cancel execution?"
        description="The crew run will be stopped and cannot be resumed."
        confirmLabel="Cancel Execution"
        confirmVariant="destructive"
        onConfirm={async () => {
          await cancelExecution(id)
          setShowCancelConfirm(false)
        }}
      />
    </div>
  )
}
