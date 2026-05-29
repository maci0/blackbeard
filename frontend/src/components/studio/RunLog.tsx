import { useEffect, useRef, memo } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Info,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ExecutionEvent } from '@/lib/types'

const EVENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  crew_started: Loader2,
  crew_completed: CheckCircle2,
  crew_failed: XCircle,
  task_started: Clock,
  task_completed: CheckCircle2,
  task_failed: XCircle,
  agent_started: Loader2,
  agent_completed: CheckCircle2,
  tool_call: Info,
  hitl_request: Info,
  hitl_response: Info,
  cost_alert: Info,
}

const EVENT_COLORS: Record<string, string> = {
  crew_completed: 'text-emerald-500',
  task_completed: 'text-emerald-500',
  agent_completed: 'text-emerald-500',
  crew_failed: 'text-red-500',
  task_failed: 'text-red-500',
  crew_started: 'text-blue-500',
  task_started: 'text-blue-500',
  agent_started: 'text-blue-500',
  cost_alert: 'text-amber-500',
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString(undefined, { hour12: false, fractionalSecondDigits: 1 })
  } catch {
    return ts
  }
}

function eventMessage(event: ExecutionEvent): string {
  const d = event.data
  if (d.message && typeof d.message === 'string') return d.message
  if (d.output && typeof d.output === 'string') return d.output.slice(0, 200)
  if (d.agent_name) return `Agent: ${d.agent_name as string}`
  if (d.task_name) return `Task: ${d.task_name as string}`
  if (d.crew_name) return `Crew: ${d.crew_name as string}`
  if (d.tool_name) return `Tool: ${d.tool_name as string}`
  return event.event_type.replace(/_/g, ' ')
}

const LogEntry = memo(function LogEntry({ event }: { event: ExecutionEvent }) {
  const Icon = EVENT_ICONS[event.event_type] ?? Info
  const color = EVENT_COLORS[event.event_type] ?? 'text-muted-foreground'

  return (
    <div className="flex items-start gap-2 border-b border-border/40 px-3 py-1 text-xs last:border-0 hover:bg-muted/30">
      <span className="mt-px shrink-0 font-mono text-[10px] text-muted-foreground/70">
        {formatTime(event.timestamp)}
      </span>
      <Icon className={cn('mt-0.5 h-3 w-3 shrink-0', color)} />
      <span className="font-mono text-muted-foreground">
        <span className="font-semibold text-foreground/80">{event.event_type}</span>
        {' — '}
        {eventMessage(event)}
      </span>
    </div>
  )
})

interface RunLogProps {
  events: ExecutionEvent[]
  open: boolean
  onToggle: () => void
  onClear: () => void
  executionStatus?: string
}

export function RunLog({ events, open, onToggle, onClear, executionStatus }: RunLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events.length, open])

  const isRunning = executionStatus === 'running' || executionStatus === 'queued'

  return (
    <div
      className={cn(
        'flex shrink-0 flex-col border-t bg-card transition-[height] duration-200 ease-out motion-reduce:transition-none',
        open ? 'h-[200px]' : 'h-8',
      )}
    >
      {/* Header bar */}
      <div className="flex h-8 shrink-0 items-center border-b">
        <button
          type="button"
          onClick={onToggle}
          className="flex flex-1 items-center gap-2 px-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          aria-expanded={open}
          aria-label={open ? 'Collapse run log' : 'Expand run log'}
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
          <span>Run Log</span>
          {events.length > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold">
              {events.length}
            </span>
          )}
          {isRunning && (
            <Loader2 className="h-3 w-3 animate-spin text-blue-500 motion-reduce:animate-none" />
          )}
        </button>
        {events.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="mr-2 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Clear log"
          >
            <Trash2 className="h-2.5 w-2.5" />
            Clear
          </button>
        )}
      </div>

      {/* Log entries */}
      {open && (
        <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono">
          {events.length === 0 ? (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground/60">
              No events yet. Run a crew to see logs here.
            </div>
          ) : (
            events.map((event) => <LogEntry key={event.sequence} event={event} />)
          )}
        </div>
      )}
    </div>
  )
}
