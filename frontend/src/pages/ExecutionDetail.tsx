import { useEffect, useCallback, useState, useMemo, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ExternalLink,
  XCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Coins,
  DollarSign,
  Activity,
  Terminal,
  BarChart3,
} from 'lucide-react'
import { useDocumentTitle, usePolling } from '@/lib/hooks'
import {
  useExecutionStore,
  TERMINAL_STATUSES,
  type Execution,
  type ExecutionTask,
  type ExecutionEvent,
} from '@/stores/executionStore'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { statusLabel } from '@/lib/status'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { CodeBlock } from '@/components/ui/CodeBlock'
import { getDuration, formatDate, formatCost } from '@/lib/formatters'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Summary card                                                        */
/* ------------------------------------------------------------------ */

function SummaryCard({
  icon: Icon,
  label,
  value,
  sub,
  borderColor,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  sub?: string
  borderColor?: string
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border bg-card p-4',
        borderColor && `border-t-2 ${borderColor}`,
      )}
    >
      <div className="rounded-md bg-muted p-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <p className="mt-0.5 text-xl font-bold tabular-nums">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Task row                                                            */
/* ------------------------------------------------------------------ */

function TaskRow({ task, index }: { task: ExecutionTask; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const needsExpand = (task.output?.split('\n').length ?? 0) > 4 || (task.output?.length ?? 0) > 400

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-3 border-b bg-muted/20 px-4 py-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-background text-xs font-semibold text-muted-foreground">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{task.task_name}</p>
          {task.agent_name && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Agent: <span className="font-medium">{task.agent_name}</span>
            </p>
          )}
        </div>
        <StatusBadge status={task.status} />
      </div>

      {task.output && (
        <div className="px-4 py-3">
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Output</p>
          <p
            className={cn(
              'whitespace-pre-wrap text-sm text-muted-foreground',
              !expanded && 'line-clamp-4',
            )}
          >
            {task.output}
          </p>
          {needsExpand && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-1 text-xs text-primary hover:underline"
              aria-expanded={expanded}
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      {task.error && (
        <div className="border-t border-destructive/20 bg-destructive/5 px-4 py-3">
          <p className="mb-1 text-xs font-medium text-destructive">Error</p>
          <p className="whitespace-pre-wrap font-mono text-sm text-destructive/80">{task.error}</p>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Event log                                                           */
/* ------------------------------------------------------------------ */

const EVENT_COLORS: Record<string, string> = {
  crew_started: 'text-white',
  crew_completed: 'text-white',
  task_started: 'text-blue-400',
  task_completed: 'text-blue-400',
  tool_started: 'text-emerald-400',
  tool_finished: 'text-emerald-400',
  llm_started: 'text-violet-400',
  llm_completed: 'text-violet-400',
}

function formatEventTime(timestamp: string): string {
  const d = new Date(timestamp)
  return d.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function str(v: unknown, fallback = 'unknown'): string {
  return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : fallback
}

function formatEventMessage(event: ExecutionEvent): string {
  const d = event.data
  switch (event.event_type) {
    case 'crew_started':
      return `Crew "${str(d.crew_name)}" started`
    case 'crew_completed':
      return `Crew completed (tokens: ${str(d.total_tokens, '0')})`
    case 'task_started':
      return `Task "${str(d.task_name)}" started${d.agent_role ? ` (agent: ${str(d.agent_role)})` : ''}`
    case 'task_completed':
      return `Task "${str(d.task_name)}" completed`
    case 'tool_started':
      return `Tool "${str(d.tool_name)}" called${d.agent_role ? ` by ${str(d.agent_role)}` : ''}`
    case 'tool_finished':
      return `Tool "${str(d.tool_name)}" finished${d.duration_ms != null ? ` (${str(d.duration_ms)}ms)` : ''}${d.from_cache ? ' [cached]' : ''}`
    case 'llm_started':
      return `LLM call started (${str(d.model)})${d.agent_role ? ` for ${str(d.agent_role)}` : ''}`
    case 'llm_completed':
      return `LLM call completed (${str(d.model)})`
    default:
      return `${event.event_type}: ${JSON.stringify(d)}`
  }
}

function EventLog({ events }: { events: ExecutionEvent[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [events.length, autoScroll])

  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    // If user scrolled up more than 40px from bottom, disable auto-scroll
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  if (events.length === 0) return null

  return (
    <div className="mt-6">
      <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <Terminal className="h-4 w-4 text-muted-foreground" />
        Event Log
        <span className="text-xs font-normal text-muted-foreground">({events.length})</span>
      </h2>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="max-h-[400px] overflow-y-auto rounded-lg border bg-[#0d1117] p-4"
      >
        <div className="space-y-0.5 font-mono text-xs leading-relaxed">
          {events.map((event) => (
            <div key={event.sequence} className="flex gap-2">
              <span className="shrink-0 text-gray-500">[{formatEventTime(event.timestamp)}]</span>
              <span className={cn('break-all', EVENT_COLORS[event.event_type] ?? 'text-gray-400')}>
                {formatEventMessage(event)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Spend section                                                       */
/* ------------------------------------------------------------------ */

interface SpendCall {
  model: string
  prompt_tokens: number
  completion_tokens: number
  spend: number
  startTime: string
}

function SpendSection({ data }: { data: Record<string, unknown> }) {
  const calls = useMemo(() => {
    const raw = Array.isArray(data) ? data : Array.isArray(data.response) ? data.response : null
    if (!raw || raw.length === 0) return null
    return raw as SpendCall[]
  }, [data])

  if (!calls) {
    return (
      <div className="mt-6">
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          Spend
        </h2>
        <p className="text-sm text-muted-foreground">No spend data available</p>
      </div>
    )
  }

  const totalCost = calls.reduce((sum, c) => sum + (c.spend ?? 0), 0)

  return (
    <div className="mt-6">
      <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <BarChart3 className="h-4 w-4 text-muted-foreground" />
        Spend
        <span className="text-xs font-normal text-muted-foreground">
          ({calls.length} call{calls.length !== 1 ? 's' : ''}, total {formatCost(totalCost)})
        </span>
      </h2>
      <div className="overflow-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/30 text-left">
              <th className="px-4 py-2 font-medium text-muted-foreground">Model</th>
              <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                Prompt tokens
              </th>
              <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                Completion tokens
              </th>
              <th className="px-4 py-2 text-right font-medium text-muted-foreground">Cost</th>
              <th className="px-4 py-2 text-right font-medium text-muted-foreground">Time</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((call, idx) => (
              <tr key={idx} className="border-b transition-colors last:border-0 hover:bg-muted/10">
                <td className="px-4 py-2 font-mono text-xs">{call.model ?? 'unknown'}</td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {(call.prompt_tokens ?? 0).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {(call.completion_tokens ?? 0).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{formatCost(call.spend)}</td>
                <td className="px-4 py-2 text-right text-xs text-muted-foreground">
                  {call.startTime ? formatEventTime(call.startTime) : '--'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
          Raw JSON
        </summary>
        <div className="mt-2">
          <CodeBlock code={JSON.stringify(data, null, 2)} language="json" />
        </div>
      </details>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function ExecutionDetail() {
  const { id = '' } = useParams<{ id: string }>()
  const {
    currentExecution,
    loading,
    error,
    events,
    spendData,
    fetchExecution,
    cancelExecution,
    pollExecution,
    addEvents,
    clearEvents,
    fetchEvents,
    fetchSpend,
  } = useExecutionStore()
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [sseDisconnected, setSseDisconnected] = useState(false)

  const load = useCallback(async () => {
    await fetchExecution(id)
  }, [id, fetchExecution])

  // Initial load + clear events
  useEffect(() => {
    clearEvents()
    let cancelled = false
    void fetchExecution(id).then(() => {
      if (cancelled) return
    })
    return () => {
      cancelled = true
    }
  }, [id, fetchExecution, clearEvents])

  const isActive = currentExecution ? !TERMINAL_STATUSES.has(currentExecution.status) : false
  const isTerminal = currentExecution ? TERMINAL_STATUSES.has(currentExecution.status) : false

  // SSE connection for live events when execution is active
  useEffect(() => {
    if (!id || !isActive) return

    let reconnectCount = 0
    setSseDisconnected(false)

    const es = new EventSource(`/api/v1/executions/${id}/stream`)

    const eventTypes = [
      'crew_started',
      'task_started',
      'task_completed',
      'tool_started',
      'tool_finished',
      'llm_started',
      'llm_completed',
      'crew_completed',
    ]

    const handleEvent = (e: MessageEvent<string>) => {
      try {
        const raw = String(e.data)
        const data = JSON.parse(raw) as Record<string, unknown>
        addEvents([
          {
            sequence: data.sequence as number,
            event_type: e.type,
            timestamp: data.timestamp as string,
            data,
          },
        ])
      } catch {
        // Ignore malformed events
      }
    }

    for (const type of eventTypes) {
      es.addEventListener(type, handleEvent)
    }

    es.addEventListener('status', (e: MessageEvent<string>) => {
      try {
        const raw = String(e.data)
        const exec = JSON.parse(raw) as Execution
        useExecutionStore.setState({ currentExecution: exec })
        // If status update brings us to terminal, do a final full fetch
        if (TERMINAL_STATUSES.has(exec.status)) {
          void fetchExecution(id)
          void fetchEvents(id)
        }
      } catch {
        // Ignore malformed status
      }
    })

    es.onopen = () => {
      reconnectCount = 0
      setSseDisconnected(false)
    }

    es.onerror = () => {
      reconnectCount += 1
      // EventSource auto-reconnects, but log for visibility
      console.warn(`[SSE] Connection error for execution ${id} (reconnect #${reconnectCount})`)
      if (reconnectCount >= 3) {
        setSseDisconnected(true)
      }
    }

    return () => {
      es.close()
      // After SSE closes, fetch events to catch anything missed
      void fetchEvents(id)
    }
  }, [id, isActive, addEvents, fetchExecution, fetchEvents])

  // When execution reaches terminal status, do a final fetch to get complete data,
  // fetch historical events, and fetch spend data (once per execution)
  const terminalFetchedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!id || !isTerminal) return
    if (terminalFetchedRef.current === id) return
    terminalFetchedRef.current = id
    void fetchExecution(id)
    void fetchEvents(id)
    void fetchSpend(id)
  }, [id, isTerminal, fetchExecution, fetchEvents, fetchSpend])

  // Fallback polling when SSE has disconnected
  const doPoll = useCallback(() => pollExecution(id), [pollExecution, id])
  usePolling(doPoll, 3000, isActive && sseDisconnected)

  // Also poll events when SSE is disconnected to catch missed events
  const doPollEvents = useCallback(() => fetchEvents(id), [fetchEvents, id])
  usePolling(doPollEvents, 5000, isActive && sseDisconnected)

  useDocumentTitle(currentExecution ? `${currentExecution.crew_name} run` : 'Execution')

  const sortedTasks = useMemo(
    () => [...(currentExecution?.tasks ?? [])].sort((a, b) => a.order - b.order),
    [currentExecution?.tasks],
  )

  /* ---- Loading ---- */
  if (loading && !currentExecution) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="sm" className="text-muted-foreground" />
          <span className="text-sm">Loading execution…</span>
        </div>
      </div>
    )
  }

  if (error || !currentExecution) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
          <p className="font-medium">{error ?? 'Execution not found'}</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              onClick={() => void load()}
              className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent"
            >
              Retry
            </button>
            <Link
              to="/executions"
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90"
            >
              Back to Executions
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const execution = currentExecution

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-4xl p-6">
        {/* Breadcrumb */}
        <nav aria-label="Breadcrumb" className="mb-5">
          <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <li>
              <Link to="/executions" className="transition-colors hover:text-foreground">
                Executions
              </Link>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">
              ›
            </li>
            <li>
              <span className="font-medium text-foreground">{execution.crew_name}</span>
            </li>
          </ol>
        </nav>

        {/* Header */}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="mb-1.5 flex flex-wrap items-center gap-3">
              <StatusBadge status={execution.status} />
              <h1 className="text-2xl font-semibold tracking-tight">
                <Link to={`/resources/crews/${execution.crew_name}`} className="hover:underline">
                  {execution.crew_name}
                </Link>
              </h1>
            </div>
            <p className="font-mono text-xs text-muted-foreground">{execution.id}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {execution.langfuse_trace_url && (
              <a
                href={execution.langfuse_trace_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View in Langfuse
              </a>
            )}
            {isActive && (
              <button
                onClick={() => setShowCancelConfirm(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
              >
                <XCircle className="h-3.5 w-3.5" />
                Cancel
              </button>
            )}
          </div>
        </div>

        {/* Summary cards */}
        <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            icon={Activity}
            label="Status"
            value={statusLabel(execution.status)}
            sub={formatDate(execution.started_at)}
            borderColor="border-t-blue-500"
          />
          <SummaryCard
            icon={Coins}
            label="Total tokens"
            value={execution.total_tokens > 0 ? execution.total_tokens.toLocaleString() : '--'}
            borderColor="border-t-violet-500"
          />
          <SummaryCard
            icon={DollarSign}
            label="Cost"
            value={formatCost(execution.cost_usd)}
            borderColor="border-t-emerald-500"
          />
          <SummaryCard
            icon={Clock}
            label="Duration"
            value={getDuration(execution.started_at, execution.completed_at)}
            sub={isActive ? 'In progress' : undefined}
            borderColor="border-t-amber-500"
          />
        </div>

        {/* Error banner */}
        {execution.status === 'failed' && execution.error && (
          <div
            role="alert"
            className="mb-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-medium text-destructive">Execution failed</p>
                <p className="mt-1 whitespace-pre-wrap font-mono text-sm text-destructive/80">
                  {execution.error}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Check your crew configuration and LLM connections, then{' '}
                  <Link to="/studio" className="text-primary underline-offset-2 hover:underline">
                    try running again from the Studio
                  </Link>
                  .
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Cancel error */}
        {cancelError && (
          <div
            role="alert"
            className="mb-6 flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
          >
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {cancelError}
            </span>
            <button
              onClick={() => setCancelError(null)}
              className="text-xs underline underline-offset-2"
              aria-label="Dismiss cancel error"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Tasks */}
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
            Tasks
            <span className="text-xs font-normal text-muted-foreground">
              ({sortedTasks.length})
            </span>
          </h2>
          {sortedTasks.length > 0 ? (
            <div className="space-y-3">
              {sortedTasks.map((task, idx) => (
                <TaskRow key={task.id} task={task} index={idx} />
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-lg border-2 border-dashed py-12 text-center">
              <div>
                <Clock
                  aria-hidden="true"
                  className="mx-auto mb-2 h-6 w-6 text-muted-foreground/40"
                />
                <p className="text-sm text-muted-foreground">
                  {isActive
                    ? 'Waiting for tasks to start…'
                    : 'No tasks recorded for this execution'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Event log */}
        <EventLog events={events} />

        {/* Spend */}
        {isTerminal && spendData && <SpendSection data={spendData} />}
        {isTerminal && !spendData && (
          <div className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              Spend
            </h2>
            <p className="text-sm text-muted-foreground">No spend data available</p>
          </div>
        )}

        {/* Outputs */}
        {execution.outputs && Object.keys(execution.outputs).length > 0 && (
          <div className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Outputs
            </h2>
            <div className="rounded-lg border bg-muted/20 p-4">
              <pre className="whitespace-pre-wrap font-mono text-sm text-foreground">
                {JSON.stringify(execution.outputs, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Footer meta */}
        <div className="mt-8 flex items-center gap-6 border-t pt-4 text-xs text-muted-foreground">
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
        loading={cancelling}
        onConfirm={() => {
          void (async () => {
            setCancelling(true)
            setCancelError(null)
            try {
              await cancelExecution(id)
              setShowCancelConfirm(false)
            } catch (err) {
              setCancelError((err as Error).message)
              setShowCancelConfirm(false)
            } finally {
              setCancelling(false)
            }
          })()
        }}
      />
    </div>
  )
}
