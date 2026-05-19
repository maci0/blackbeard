import { useEffect, useCallback, useState, useMemo, useRef, memo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
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
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { useShallow } from 'zustand/react/shallow'
import { useExecutionStore } from '@/stores/executionStore'
import { TERMINAL_STATUSES } from '@/lib/types'
import type { Execution, ExecutionTask, ExecutionEvent } from '@/lib/types'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { statusLabel } from '@/lib/formatters'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { CodeBlock } from '@/components/ui/CodeBlock'
import { getDuration, formatDate, formatCost } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import { api } from '@/api/client'

/* ------------------------------------------------------------------ */
/* Summary card                                                        */
/* ------------------------------------------------------------------ */

function SummaryCard({
  icon: Icon,
  label,
  value,
  valueLabel,
  sub,
  borderColor,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  valueLabel?: string
  sub?: string
  borderColor?: string
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border bg-card p-4',
        borderColor && 'border-t-2',
        borderColor,
      )}
    >
      <div className="rounded-md bg-muted p-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <p className="mt-0.5 text-xl font-bold tabular-nums">
          {valueLabel ? (
            <>
              <span aria-hidden="true">{value}</span>
              <span className="sr-only">{valueLabel}</span>
            </>
          ) : (
            value
          )}
        </p>
        {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Task row                                                            */
/* ------------------------------------------------------------------ */

const TaskRow = memo(function TaskRow({ task, index }: { task: ExecutionTask; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const needsExpand = (task.output?.split('\n').length ?? 0) > 4 || (task.output?.length ?? 0) > 400

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-3 border-b bg-muted/20 px-4 py-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-background text-xs font-semibold text-muted-foreground">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={task.task_name}>
            {task.task_name}
          </p>
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
              aria-label={
                expanded
                  ? `Collapse output for ${task.task_name}`
                  : `Expand output for ${task.task_name}`
              }
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
})

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

const eventTimeFmt = new Intl.DateTimeFormat('en-US', {
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function formatEventTime(timestamp: string): string {
  return eventTimeFmt.format(new Date(timestamp))
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

const EventRow = memo(function EventRow({ event }: { event: ExecutionEvent }) {
  return (
    <div className="flex gap-2">
      <span className="shrink-0 text-gray-400">[{formatEventTime(event.timestamp)}]</span>
      <span className={cn('break-all', EVENT_COLORS[event.event_type] ?? 'text-gray-400')}>
        {formatEventMessage(event)}
      </span>
    </div>
  )
})

const EventLog = memo(function EventLog({ events }: { events: ExecutionEvent[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const rafRef = useRef(0)

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      cancelAnimationFrame(rafRef.current)
      const el = containerRef.current
      rafRef.current = requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight
      })
    }
  }, [events.length, autoScroll])

  useEffect(() => () => cancelAnimationFrame(rafRef.current), [])

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }, [])

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
        role="log"
        aria-label="Execution event log"
        className="max-h-[400px] overflow-y-auto rounded-lg border bg-[#0d1117] p-4"
      >
        <div className="space-y-0.5 font-mono text-xs leading-relaxed">
          {events.map((event) => (
            <EventRow key={event.sequence} event={event} />
          ))}
        </div>
      </div>
    </div>
  )
})

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
        <table className="w-full text-sm" aria-label="LLM spend breakdown">
          <thead>
            <tr className="border-b bg-muted/30 text-left">
              <th scope="col" className="px-4 py-2 font-medium text-muted-foreground">
                Model
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium text-muted-foreground">
                Prompt tokens
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium text-muted-foreground">
                Completion tokens
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium text-muted-foreground">
                Cost
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium text-muted-foreground">
                Time
              </th>
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
        <summary className="cursor-pointer rounded text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
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
  } = useExecutionStore(
    useShallow((s) => ({
      currentExecution: s.currentExecution,
      loading: s.loading,
      error: s.error,
      events: s.events,
      spendData: s.spendData,
      fetchExecution: s.fetchExecution,
      cancelExecution: s.cancelExecution,
      pollExecution: s.pollExecution,
      addEvents: s.addEvents,
      clearEvents: s.clearEvents,
      fetchEvents: s.fetchEvents,
      fetchSpend: s.fetchSpend,
    })),
  )
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
    void fetchExecution(id)
  }, [id, fetchExecution, clearEvents])

  const isActive = currentExecution ? !TERMINAL_STATUSES.has(currentExecution.status) : false
  const isTerminal = currentExecution ? TERMINAL_STATUSES.has(currentExecution.status) : false

  // SSE connection for live events when execution is active
  useEffect(() => {
    if (!id || !isActive) return

    let reconnectCount = 0
    setSseDisconnected(false)

    const apiKey = api.getApiKey()
    const token = api.getToken()
    const sseParams = new URLSearchParams()
    if (token) {
      sseParams.set('token', token)
    } else if (apiKey) {
      sseParams.set('api_key', apiKey)
    }
    const qs = sseParams.toString()
    const sseUrl = `/api/v1/executions/${id}/stream${qs ? `?${qs}` : ''}`
    const es = new EventSource(sseUrl)

    const eventTypes = Object.keys(EVENT_COLORS)

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
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" aria-hidden="true" />
          <p className="font-medium">{error ?? 'Execution not found'}</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              onClick={() => void load()}
              className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Retry
            </button>
            <Link
              to="/executions"
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <li aria-current="page">
              <span className="font-medium text-foreground">{execution.crew_name}</span>
            </li>
          </ol>
        </nav>

        {/* Header */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="mb-1.5 flex flex-wrap items-center gap-3">
              <StatusBadge status={execution.status} live />
              {execution.execution_type && execution.execution_type !== 'kickoff' && (
                <span
                  className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                    execution.execution_type === 'train'
                      ? 'bg-violet-100 text-violet-700 dark:bg-violet-900 dark:text-violet-300'
                      : execution.execution_type === 'test'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'
                  }`}
                >
                  {execution.execution_type}
                  {execution.n_iterations != null &&
                    ` (${execution.n_iterations} iter${execution.n_iterations !== 1 ? 's' : ''})`}
                </span>
              )}
              <h1 className="text-2xl font-semibold tracking-tight">
                <Link to={`/resources/crews/${execution.crew_name}`} className="hover:underline">
                  {execution.crew_name}
                </Link>
              </h1>
            </div>
            <p className="font-mono text-xs text-muted-foreground">{execution.id}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {isActive && (
              <button
                onClick={() => setShowCancelConfirm(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <XCircle className="h-3.5 w-3.5" />
                Cancel Execution
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
            valueLabel={execution.total_tokens > 0 ? undefined : 'No tokens recorded'}
            borderColor="border-t-violet-500"
          />
          <SummaryCard
            icon={DollarSign}
            label="Cost"
            value={formatCost(execution.cost_usd)}
            valueLabel={Number(execution.cost_usd) > 0 ? undefined : 'No cost recorded'}
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
          <ErrorAlert
            message={cancelError}
            actionLabel="Dismiss"
            onAction={() => setCancelError(null)}
            ariaLabel="Dismiss cancel error"
            className="mb-6"
          />
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
            <div
              role="status"
              className="flex items-center justify-center rounded-lg border-2 border-dashed py-12 text-center"
            >
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
        {isTerminal && <SpendSection data={spendData ?? {}} />}

        {/* Outputs */}
        {execution.outputs && Object.keys(execution.outputs).length > 0 && (
          <div className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              Outputs
            </h2>
            <CodeBlock code={JSON.stringify(execution.outputs, null, 2)} language="json" />
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
