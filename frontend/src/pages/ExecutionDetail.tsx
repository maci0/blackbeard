import { useEffect, useCallback, useState, useMemo, useRef, memo } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
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
  RotateCcw,
  MessageCircle,
  Send,
  ChevronRight,
  List,
  GanttChart,
  Layers,
} from 'lucide-react'
import { useDocumentTitle, usePolling } from '@/hooks'
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
import { cn, getErrorMessage } from '@/lib/utils'
import { api } from '@/api/client'
import { CopyButton } from '@/components/ui/CopyButton'

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
              className="mt-1 min-h-[44px] rounded px-1 text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-0"
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
/* Task timeline (Gantt chart)                                         */
/* ------------------------------------------------------------------ */

const STATUS_BAR_COLORS: Record<string, string> = {
  completed: 'bg-emerald-500',
  failed: 'bg-red-500',
  running: 'bg-blue-500',
  pending: 'bg-gray-400',
  queued: 'bg-gray-400',
}

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return `${min}m ${Math.round(rem)}s`
}

const TaskTimeline = memo(function TaskTimeline({
  tasks,
  executionStart,
  executionEnd,
}: {
  tasks: ExecutionTask[]
  executionStart: string | null
  executionEnd: string | null
}) {
  const timelineData = useMemo(() => {
    if (!executionStart || tasks.length === 0) return null

    const startMs = new Date(executionStart).getTime()
    const endMs = executionEnd
      ? new Date(executionEnd).getTime()
      : Math.max(
          Date.now(),
          ...tasks.filter((t) => t.completed_at).map((t) => new Date(t.completed_at!).getTime()),
        )
    const totalMs = Math.max(endMs - startMs, 1)

    const tickCount = 5
    const ticks: { label: string; left: number }[] = []
    for (let i = 0; i <= tickCount; i++) {
      const ms = (totalMs / tickCount) * i
      ticks.push({ label: formatDurationMs(ms), left: (i / tickCount) * 100 })
    }

    const bars = tasks.map((task) => {
      const taskStart = task.started_at ? new Date(task.started_at).getTime() : startMs
      const taskEnd = task.completed_at
        ? new Date(task.completed_at).getTime()
        : task.status === 'running'
          ? Date.now()
          : taskStart

      const left = ((taskStart - startMs) / totalMs) * 100
      const width = Math.max(((taskEnd - taskStart) / totalMs) * 100, 0.5)
      const durationMs = taskEnd - taskStart

      return {
        task,
        left: Math.min(left, 100),
        width: Math.min(width, 100 - Math.min(left, 100)),
        durationMs,
      }
    })

    return { bars, ticks }
  }, [tasks, executionStart, executionEnd])

  if (!timelineData) return null

  return (
    <div className="space-y-1">
      {timelineData.bars.map(({ task, left, width, durationMs }) => (
        <div key={task.id} className="group flex items-center gap-3">
          <span
            className="w-28 shrink-0 truncate text-right text-xs text-muted-foreground"
            title={task.task_name}
          >
            {task.task_name}
          </span>
          <div className="relative h-7 flex-1 rounded bg-muted/30">
            <div
              className={cn(
                'absolute bottom-0.5 top-0.5 flex items-center overflow-hidden rounded-sm px-1.5 text-[10px] font-medium text-white transition-all',
                STATUS_BAR_COLORS[task.status] ?? 'bg-gray-400',
                task.status === 'running' && 'animate-pulse motion-reduce:animate-none',
              )}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                minWidth: '2px',
              }}
              title={`${task.task_name} — ${formatDurationMs(durationMs)}`}
            >
              <span className="truncate">{width > 8 ? task.task_name : ''}</span>
            </div>
          </div>
          <span className="w-16 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
            {durationMs > 0 ? formatDurationMs(durationMs) : '—'}
          </span>
        </div>
      ))}
      <div className="flex items-center gap-3">
        <span className="w-28 shrink-0" />
        <div className="relative h-5 flex-1">
          {timelineData.ticks.map((tick, i) => (
            <span
              key={i}
              className="absolute top-0 text-[10px] tabular-nums text-muted-foreground/60"
              style={{
                left: `${tick.left}%`,
                transform:
                  i === timelineData.ticks.length - 1
                    ? 'translateX(-100%)'
                    : i > 0
                      ? 'translateX(-50%)'
                      : undefined,
              }}
            >
              {tick.label}
            </span>
          ))}
        </div>
        <span className="w-16 shrink-0" />
      </div>
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
  hitl_request: 'text-yellow-400',
  hitl_response: 'text-yellow-400',
}

const eventTimeFmt = new Intl.DateTimeFormat(undefined, {
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
    case 'hitl_request':
      return `⏸ Human input requested: "${str(d.prompt, 'Awaiting response…')}"`
    case 'hitl_response':
      return `✓ Human responded (${str(d.response_length, '?')} chars)`
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

interface EventGroup {
  name: string
  status: 'completed' | 'failed' | 'running' | 'pending'
  events: ExecutionEvent[]
  startTime: string | null
  endTime: string | null
  durationMs: number | null
}

function buildEventGroups(events: ExecutionEvent[]): EventGroup[] {
  const groups: EventGroup[] = []
  let current: EventGroup | null = null

  for (const event of events) {
    if (event.event_type === 'task_started') {
      if (current) {
        groups.push(current)
      }
      current = {
        name: str(event.data.task_name, 'Unnamed Task'),
        status: 'running',
        events: [event],
        startTime: event.timestamp,
        endTime: null,
        durationMs: null,
      }
    } else if (event.event_type === 'task_completed' && current) {
      current.events.push(event)
      current.status = 'completed'
      current.endTime = event.timestamp
      if (current.startTime) {
        current.durationMs =
          new Date(event.timestamp).getTime() - new Date(current.startTime).getTime()
      }
      groups.push(current)
      current = null
    } else if (current) {
      current.events.push(event)
    } else {
      if (groups.length === 0 || groups[groups.length - 1]!.status !== 'pending') {
        groups.push({
          name: groups.length === 0 ? 'Setup' : 'Between Tasks',
          status: 'pending',
          events: [event],
          startTime: event.timestamp,
          endTime: null,
          durationMs: null,
        })
      } else {
        groups[groups.length - 1]!.events.push(event)
      }
    }
  }

  if (current) {
    groups.push(current)
  }

  return groups
}

const GROUP_STATUS_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  completed: CheckCircle2,
  failed: XCircle,
  running: Clock,
  pending: Clock,
}

const GROUP_STATUS_COLOR: Record<string, string> = {
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  running: 'text-blue-400',
  pending: 'text-gray-500',
}

const EventGroupSection = memo(function EventGroupSection({
  group,
  defaultOpen,
}: {
  group: EventGroup
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const Icon = GROUP_STATUS_ICON[group.status] ?? Clock

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        aria-label={`${group.name} — ${group.events.length} events`}
      >
        <ChevronRight
          className={cn('h-3 w-3 shrink-0 text-gray-500 transition-transform', open && 'rotate-90')}
        />
        <Icon className={cn('h-3.5 w-3.5 shrink-0', GROUP_STATUS_COLOR[group.status])} />
        <span className="flex-1 truncate text-xs font-medium text-gray-200">{group.name}</span>
        {group.durationMs != null && (
          <span className="shrink-0 text-[10px] tabular-nums text-gray-500">
            {formatDurationMs(group.durationMs)}
          </span>
        )}
        <span className="shrink-0 rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] tabular-nums text-gray-400">
          {group.events.length}
        </span>
      </button>
      {open && (
        <div className="ml-5 border-l border-white/10 pl-3 pt-0.5">
          <div className="space-y-0.5">
            {group.events.map((event) => (
              <EventRow key={event.sequence} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
})

const EventLog = memo(function EventLog({ events }: { events: ExecutionEvent[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [grouped, setGrouped] = useState(true)
  const rafRef = useRef(0)

  const groups = useMemo(() => buildEventGroups(events), [events])

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
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          Event Log
          <span className="text-xs font-normal text-muted-foreground">({events.length})</span>
        </h2>
        <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
          <button
            onClick={() => setGrouped(true)}
            className={cn(
              'inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              grouped
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            aria-pressed={grouped}
            aria-label="Group events by task"
          >
            <Layers className="h-3 w-3" />
            Grouped
          </button>
          <button
            onClick={() => setGrouped(false)}
            className={cn(
              'inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              !grouped
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            aria-pressed={!grouped}
            aria-label="Flat event list"
          >
            <List className="h-3 w-3" />
            Flat
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        role="log"
        aria-label="Execution event log"
        className="max-h-[400px] overflow-y-auto rounded-lg border bg-[#0d1117] p-4"
      >
        {grouped ? (
          <div className="space-y-1">
            {groups.map((group, idx) => (
              <EventGroupSection
                key={`${group.name}-${idx}`}
                group={group}
                defaultOpen={
                  group.status === 'running' ||
                  group.status === 'failed' ||
                  idx === groups.length - 1
                }
              />
            ))}
          </div>
        ) : (
          <div className="space-y-0.5 font-mono text-xs leading-relaxed">
            {events.map((event) => (
              <EventRow key={event.sequence} event={event} />
            ))}
          </div>
        )}
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
  endTime?: string
  api_call_start_time?: string
}

function SpendSection({ data }: { data: Record<string, unknown> }) {
  const calls = useMemo(() => {
    const raw = Array.isArray(data) ? data : Array.isArray(data.response) ? data.response : null
    if (!raw || raw.length === 0) return null
    return raw as SpendCall[]
  }, [data])

  const totalCost = useMemo(
    () => (calls ? calls.reduce((sum, c) => sum + (c.spend ?? 0), 0) : 0),
    [calls],
  )

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
                tok/s
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
                <td className="px-4 py-2 text-right text-xs tabular-nums">
                  {(() => {
                    const start = call.startTime || call['api_call_start_time']
                    const end = call.endTime
                    if (start && end) {
                      const ms = new Date(end).getTime() - new Date(start).getTime()
                      if (ms > 0 && (call.completion_tokens ?? 0) > 0) {
                        return `${((call.completion_tokens ?? 0) / (ms / 1000)).toFixed(1)}`
                      }
                    }
                    return '—'
                  })()}
                </td>
                <td className="px-4 py-2 text-right text-xs text-muted-foreground">
                  {call.startTime ? formatEventTime(call.startTime) : '--'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="mt-2">
        <summary className="inline-flex min-h-[44px] cursor-pointer items-center rounded px-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-0">
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
/* HITL response panel                                                 */
/* ------------------------------------------------------------------ */

function HITLPanel({
  executionId,
  events,
  onResponded,
}: {
  executionId: string
  events: ExecutionEvent[]
  onResponded: () => void
}) {
  const [response, setResponse] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const pendingRequest = useMemo(() => {
    let requestCount = 0
    let responseCount = 0
    let lastRequest: ExecutionEvent | null = null
    for (const e of events) {
      if (e.event_type === 'hitl_request') {
        requestCount++
        lastRequest = e
      } else if (e.event_type === 'hitl_response') {
        responseCount++
      }
    }
    return requestCount > responseCount ? lastRequest : null
  }, [events])

  if (!pendingRequest) return null

  const prompt =
    typeof pendingRequest.data.prompt === 'string'
      ? pendingRequest.data.prompt
      : 'The crew is waiting for your input.'

  const handleSubmit = async () => {
    if (!response.trim()) return
    setSubmitting(true)
    try {
      await api.post(`/api/v1/executions/${executionId}/respond`, {
        response: response.trim(),
      })
      setResponse('')
      onResponded()
    } catch {
      // Error handled by toast in parent
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      role="alert"
      className="mb-6 rounded-lg border-2 border-yellow-400/50 bg-yellow-50 p-4 dark:border-yellow-500/30 dark:bg-yellow-950/20"
    >
      <div className="mb-3 flex items-start gap-2">
        <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-600 dark:text-yellow-400" />
        <div>
          <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
            Human Input Required
          </p>
          <p className="mt-1 text-sm text-yellow-700 dark:text-yellow-300">{prompt}</p>
        </div>
      </div>
      <div className="flex gap-2">
        <textarea
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault()
              void handleSubmit()
            }
          }}
          placeholder="Type your response…"
          rows={2}
          className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          disabled={submitting}
        />
        <button
          onClick={() => void handleSubmit()}
          disabled={!response.trim() || submitting}
          className="flex shrink-0 items-center gap-1.5 self-end rounded-md bg-yellow-600 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? <Spinner size="sm" /> : <Send className="h-3.5 w-3.5" />}
          Respond
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Tasks section with list/timeline toggle                             */
/* ------------------------------------------------------------------ */

function TasksSection({
  tasks,
  isActive,
  executionStart,
  executionEnd,
}: {
  tasks: ExecutionTask[]
  isActive: boolean
  executionStart: string | null
  executionEnd: string | null
}) {
  const [view, setView] = useState<'list' | 'timeline'>('list')
  const hasTimingData = tasks.some((t) => t.started_at)

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          Tasks
          <span className="text-xs font-normal text-muted-foreground">({tasks.length})</span>
        </h2>
        {tasks.length > 0 && hasTimingData && (
          <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
            <button
              onClick={() => setView('list')}
              className={cn(
                'inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                view === 'list'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              aria-pressed={view === 'list'}
              aria-label="List view"
            >
              <List className="h-3 w-3" />
              List
            </button>
            <button
              onClick={() => setView('timeline')}
              className={cn(
                'inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                view === 'timeline'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              aria-pressed={view === 'timeline'}
              aria-label="Timeline view"
            >
              <GanttChart className="h-3 w-3" />
              Timeline
            </button>
          </div>
        )}
      </div>
      {tasks.length > 0 ? (
        view === 'timeline' && hasTimingData ? (
          <div className="rounded-lg border bg-card p-4">
            <TaskTimeline
              tasks={tasks}
              executionStart={executionStart}
              executionEnd={executionEnd}
            />
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task, idx) => (
              <TaskRow key={task.id} task={task} index={idx} />
            ))}
          </div>
        )
      ) : (
        <div
          role="status"
          className="flex items-center justify-center rounded-lg border-2 border-dashed py-12 text-center"
        >
          <div>
            <Clock aria-hidden="true" className="mx-auto mb-2 h-6 w-6 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">
              {isActive ? 'Waiting for tasks to start…' : 'No tasks recorded for this execution'}
            </p>
          </div>
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
  const navigate = useNavigate()
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [sseDisconnected, setSseDisconnected] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const handleRetry = useCallback(async () => {
    setRetrying(true)
    try {
      const result = await api.post<{ id: string }>(`/api/v1/executions/${id}/retry`, {})
      void navigate(`/executions/${result.id}`)
    } catch (err) {
      setCancelError(getErrorMessage(err, 'Failed to retry execution'))
    } finally {
      setRetrying(false)
    }
  }, [id, navigate])

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
      } catch (err) {
        console.debug('[SSE] Failed to parse event:', e.type, err)
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
      } catch (err) {
        console.debug('[SSE] Failed to parse status update:', err)
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
        <div role="status" className="flex items-center gap-2 text-muted-foreground">
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
              <Link
                to="/executions"
                className="rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Executions
              </Link>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">
              ›
            </li>
            <li>
              <span className="text-foreground/80">{execution.crew_name}</span>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">
              ›
            </li>
            <li aria-current="page">
              <span className="font-medium text-foreground" title={execution.id}>
                {execution.id.slice(0, 8)}
              </span>
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
                <Link
                  to={`/resources/crews/${execution.crew_name}`}
                  className="rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {execution.crew_name}
                </Link>
              </h1>
            </div>
            <div className="flex items-center gap-1">
              <p className="font-mono text-xs text-muted-foreground">{execution.id}</p>
              <CopyButton text={execution.id} label="Copy execution ID" />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {isTerminal && (
              <button
                onClick={() => void handleRetry()}
                disabled={retrying}
                aria-busy={retrying || undefined}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {retrying ? <Spinner size="sm" /> : <RotateCcw className="h-3.5 w-3.5" />}
                Retry
              </button>
            )}
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
            value={execution.total_tokens > 0 ? execution.total_tokens.toLocaleString() : '—'}
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
            valueLabel={execution.started_at ? undefined : 'No duration recorded'}
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

        {/* HITL */}
        {isActive && (
          <HITLPanel executionId={id} events={events} onResponded={() => void fetchEvents(id)} />
        )}

        {/* Tasks */}
        <TasksSection
          tasks={sortedTasks}
          isActive={isActive}
          executionStart={execution.started_at}
          executionEnd={execution.completed_at}
        />

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
              setCancelError(getErrorMessage(err, 'Failed to cancel execution'))
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
