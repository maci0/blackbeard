import { useEffect, useState, useMemo, useCallback } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  AlertTriangle,
  Coins,
  Clock,
  Activity,
  RefreshCw,
  GitCompareArrows,
} from 'lucide-react'
import { api } from '@/api/client'
import { useDocumentTitle } from '@/hooks'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { SmartTime } from '@/components/ui/SmartTime'
import { Spinner } from '@/components/ui/Spinner'
import { cn, getErrorMessage } from '@/lib/utils'
import { getDuration, formatCost, formatPercent, parseCost } from '@/lib/formatters'
import type { Execution, ExecutionTask } from '@/lib/types'

function MetricCard({
  label,
  icon: Icon,
  valueA,
  valueB,
  formatFn,
  betterWhen,
}: {
  label: string
  icon: React.ComponentType<{ className?: string }>
  valueA: number
  valueB: number
  formatFn: (v: number) => string
  betterWhen: 'lower' | 'higher'
}) {
  const diff = valueB - valueA
  const pctChange = valueA !== 0 ? Math.abs(diff / valueA) * 100 : valueB !== 0 ? 100 : 0
  const significantDiff = pctChange > 10

  let diffColor = 'text-muted-foreground'
  let DiffIcon = Minus
  if (diff !== 0 && significantDiff) {
    const isBetter = (betterWhen === 'lower' && diff < 0) || (betterWhen === 'higher' && diff > 0)
    diffColor = isBetter
      ? 'text-emerald-600 dark:text-emerald-400'
      : 'text-red-600 dark:text-red-400'
    DiffIcon = diff > 0 ? ArrowUpRight : ArrowDownRight
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-muted-foreground">Run A</p>
          <p className="mt-0.5 text-lg font-bold tabular-nums">{formatFn(valueA)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Run B</p>
          <p className="mt-0.5 text-lg font-bold tabular-nums">{formatFn(valueB)}</p>
        </div>
      </div>
      {diff !== 0 && (
        <div className={cn('mt-2 flex items-center gap-1 text-xs font-medium', diffColor)}>
          <DiffIcon className="h-3 w-3" aria-hidden="true" />
          <span>
            {diff > 0 ? '+' : ''}
            {formatFn(diff)} ({formatPercent(pctChange)})
          </span>
        </div>
      )}
    </div>
  )
}

function TaskCompareRow({
  taskA,
  taskB,
  index,
}: {
  taskA: ExecutionTask | null
  taskB: ExecutionTask | null
  index: number
}) {
  const taskName = taskA?.task_name ?? taskB?.task_name ?? 'Unknown'

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-3 border-b bg-muted/20 px-4 py-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-background text-xs font-semibold text-muted-foreground">
          {index + 1}
        </span>
        <p className="min-w-0 flex-1 truncate text-sm font-medium" title={taskName}>
          {taskName}
        </p>
      </div>
      <div className="grid grid-cols-2 divide-x divide-border">
        <TaskColumn task={taskA} side="A" />
        <TaskColumn task={taskB} side="B" />
      </div>
    </div>
  )
}

function TaskColumn({ task, side }: { task: ExecutionTask | null; side: string }) {
  if (!task) {
    return (
      <div className="px-4 py-3">
        <p className="text-xs text-muted-foreground">Not present in Run {side}</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <StatusBadge status={task.status} />
        {task.agent_name && (
          <span className="text-xs text-muted-foreground">{task.agent_name}</span>
        )}
      </div>
      {task.output && (
        <p className="line-clamp-4 whitespace-pre-wrap text-xs text-muted-foreground">
          {task.output}
        </p>
      )}
      {task.error && (
        <p className="mt-1 line-clamp-2 whitespace-pre-wrap font-mono text-xs text-destructive/80">
          {task.error}
        </p>
      )}
    </div>
  )
}

function ExecutionHeader({ execution, label }: { execution: Execution; label: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <div className="flex items-center gap-3">
        <StatusBadge status={execution.status} />
        <div className="min-w-0 flex-1">
          <Link
            to={`/executions/${execution.id}`}
            className="text-sm font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {execution.crew_name}
          </Link>
          <p className="font-mono text-xs text-muted-foreground" title={execution.id}>
            {execution.id.slice(0, 8)}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span className="capitalize">{execution.execution_type}</span>
        <span>
          <SmartTime date={execution.created_at} />
        </span>
        {execution.started_at && (
          <span className="font-mono">
            {getDuration(execution.started_at, execution.completed_at)}
          </span>
        )}
      </div>
    </div>
  )
}

export default function ExecutionCompare() {
  const [searchParams] = useSearchParams()
  const idA = searchParams.get('a') ?? ''
  const idB = searchParams.get('b') ?? ''

  const [execA, setExecA] = useState<Execution | null>(null)
  const [execB, setExecB] = useState<Execution | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useDocumentTitle('Compare Executions')

  const fetchBoth = useCallback(async () => {
    if (!idA || !idB) {
      setError('Two execution IDs are required (query params a and b).')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [a, b] = await Promise.all([
        api.get<Execution>(`/api/v1/executions/${idA}`),
        api.get<Execution>(`/api/v1/executions/${idB}`),
      ])
      setExecA(a)
      setExecB(b)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load executions'))
    } finally {
      setLoading(false)
    }
  }, [idA, idB])

  useEffect(() => {
    void fetchBoth()
  }, [fetchBoth])

  const alignedTasks = useMemo(() => {
    if (!execA || !execB) return []
    const tasksA = [...(execA.tasks ?? [])].sort((a, b) => a.order - b.order)
    const tasksB = [...(execB.tasks ?? [])].sort((a, b) => a.order - b.order)

    const taskMapB = new Map<string, ExecutionTask>()
    for (const t of tasksB) {
      taskMapB.set(t.task_name, t)
    }

    const seen = new Set<string>()
    const result: Array<{ a: ExecutionTask | null; b: ExecutionTask | null }> = []

    for (const t of tasksA) {
      seen.add(t.task_name)
      result.push({ a: t, b: taskMapB.get(t.task_name) ?? null })
    }
    for (const t of tasksB) {
      if (!seen.has(t.task_name)) {
        result.push({ a: null, b: t })
      }
    }
    return result
  }, [execA, execB])

  const costA = execA ? parseCost(execA.cost_usd) : 0
  const costB = execB ? parseCost(execB.cost_usd) : 0
  const costDiffPct = costA !== 0 ? Math.abs((costB - costA) / costA) * 100 : 0
  const costDiffSignificant = costDiffPct > 10

  const durationA = execA?.started_at
    ? (execA.completed_at ? new Date(execA.completed_at).getTime() : Date.now()) -
      new Date(execA.started_at).getTime()
    : 0
  const durationB = execB?.started_at
    ? (execB.completed_at ? new Date(execB.completed_at).getTime() : Date.now()) -
      new Date(execB.started_at).getTime()
    : 0

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div role="status" className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="sm" className="text-muted-foreground" />
          <span className="text-sm">Loading executions...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div role="alert" className="text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" aria-hidden="true" />
          <p className="font-medium">{error}</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => void fetchBoth()}
              className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Retry
            </button>
            <Link
              to="/executions"
              className="btn-press rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Back to Executions
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (!execA || !execB) return null

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-6xl p-6">
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
            <li aria-current="page">
              <span className="font-medium text-foreground">Compare</span>
            </li>
          </ol>
        </nav>

        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <GitCompareArrows className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            <h1 className="text-2xl font-semibold tracking-tight">Compare Executions</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void fetchBoth()}
              disabled={loading}
              aria-label="Refresh comparison"
              className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
            <Link
              to="/executions"
              className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back
            </Link>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          <ExecutionHeader execution={execA} label="Run A" />
          <ExecutionHeader execution={execB} label="Run B" />
        </div>

        {costDiffSignificant && (
          <div
            role="alert"
            className="mb-6 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            Cost differs by {formatPercent(costDiffPct)} between runs
          </div>
        )}

        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <MetricCard
            label="Tokens"
            icon={Activity}
            valueA={execA.total_tokens}
            valueB={execB.total_tokens}
            formatFn={(v) => (v === 0 ? '--' : v.toLocaleString())}
            betterWhen="lower"
          />
          <MetricCard
            label="Cost"
            icon={Coins}
            valueA={costA}
            valueB={costB}
            formatFn={(v) => {
              if (v === 0) return '--'
              const abs = Math.abs(v)
              const formatted = formatCost(abs)
              return v < 0 ? `-${formatted}` : formatted
            }}
            betterWhen="lower"
          />
          <MetricCard
            label="Duration"
            icon={Clock}
            valueA={durationA}
            valueB={durationB}
            formatFn={(v) => {
              if (v === 0) return '--'
              const sec = Math.round(Math.abs(v) / 1000)
              if (sec < 60) return `${sec}s`
              const min = Math.floor(sec / 60)
              const rem = sec % 60
              if (min < 60) return `${min}m ${rem}s`
              const hrs = Math.floor(min / 60)
              const remMin = min % 60
              return `${hrs}h ${remMin}m`
            }}
            betterWhen="lower"
          />
        </div>

        <div>
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
            Tasks
            <span className="text-xs font-normal text-muted-foreground">
              ({alignedTasks.length})
            </span>
          </h2>
          {alignedTasks.length > 0 ? (
            <div className="space-y-3">
              {alignedTasks.map((pair, idx) => (
                <TaskCompareRow
                  key={pair.a?.task_name ?? pair.b?.task_name ?? idx}
                  taskA={pair.a}
                  taskB={pair.b}
                  index={idx}
                />
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-lg border-2 border-dashed py-12 text-center">
              <p className="text-sm text-muted-foreground">No tasks recorded in either execution</p>
            </div>
          )}
        </div>

        <div className="mt-8 flex items-center gap-6 border-t pt-4 text-xs text-muted-foreground">
          <span>
            Run A: {execA.id.slice(0, 8)} ({execA.crew_name})
          </span>
          <span>
            Run B: {execB.id.slice(0, 8)} ({execB.crew_name})
          </span>
        </div>
      </div>
    </div>
  )
}
