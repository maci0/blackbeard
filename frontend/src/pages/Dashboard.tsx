import { memo, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Database,
  Play,
  Cpu,
  Timer,
  ChevronRight,
  PenTool,
  Store,
  ArrowRight,
  DollarSign,
  BarChart3,
  TrendingUp,
} from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useResourceStore } from '@/stores/resourceStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useDocumentTitle } from '@/hooks'
import { PageHeader } from '@/components/ui/PageHeader'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { KindBadge } from '@/components/ui/KindBadge'
import { Skeleton } from '@/components/ui/Skeleton'
import { getDuration, formatCost, parseCost } from '@/lib/formatters'
import { SmartTime } from '@/components/ui/SmartTime'
import { PLURAL_TO_KIND } from '@/lib/kinds'
import { cn } from '@/lib/utils'
import type { Resource, Execution } from '@/lib/types'

const STAT_ACCENT = {
  blue: 'bg-blue-100 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400',
  green: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400',
  amber: 'bg-amber-100 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400',
  violet: 'bg-violet-100 text-violet-600 dark:bg-violet-950/60 dark:text-violet-400',
  rose: 'bg-rose-100 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400',
} as const

type StatAccent = keyof typeof STAT_ACCENT

const StatCard = memo(function StatCard({
  label,
  value,
  icon: Icon,
  loading,
  href,
  accent = 'blue',
}: {
  label: string
  value: number | string
  icon: React.ComponentType<{ className?: string }>
  loading: boolean
  href: string
  accent?: StatAccent
}) {
  return (
    <Link
      to={href}
      className="group flex items-center gap-4 rounded-lg border bg-card p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-accent/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`${label}: ${loading ? 'loading' : value}`}
    >
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
          STAT_ACCENT[accent],
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        {loading ? (
          <Skeleton className="h-7 w-16" />
        ) : (
          <p className="text-2xl font-semibold tracking-tight">{value}</p>
        )}
      </div>
      <ChevronRight
        aria-hidden="true"
        className="h-4 w-4 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
      />
    </Link>
  )
})

const RecentExecutions = memo(function RecentExecutions({
  executions,
  loading,
}: {
  executions: Execution[]
  loading: boolean
}) {
  const navigate = useNavigate()
  const recent = useMemo(() => executions.slice(0, 5), [executions])

  return (
    <section aria-labelledby="recent-executions-heading">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="recent-executions-heading" className="text-base font-semibold">
          Recent Executions
        </h2>
        <Link
          to="/executions"
          className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          View all
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
      <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
        {loading && recent.length === 0 ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
        ) : recent.length === 0 ? (
          <div className="py-12 text-center">
            <Play className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">No executions yet</p>
          </div>
        ) : (
          <table className="w-full text-sm" aria-label="Recent executions">
            <thead>
              <tr className="border-b bg-muted/60">
                {(['Status', 'Crew', 'Duration', 'Created'] as const).map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    {h}
                  </th>
                ))}
                <th scope="col" className="w-8 px-4 py-2.5">
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {recent.map((execution) => (
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
                  aria-label={`${execution.crew_name} - ${execution.status} - press Enter to view`}
                  className="group cursor-pointer border-l-2 border-l-transparent transition-all duration-150 hover:border-l-primary hover:bg-accent/50 focus-visible:border-l-primary focus-visible:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  <td className="px-4 py-2.5">
                    <StatusBadge status={execution.status} />
                  </td>
                  <td className="px-4 py-2.5 font-medium">{execution.crew_name}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                    {execution.started_at ? (
                      getDuration(execution.started_at, execution.completed_at)
                    ) : (
                      <>
                        <span aria-hidden="true">--</span>
                        <span className="sr-only">Not started</span>
                      </>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    <SmartTime date={execution.created_at} />
                  </td>
                  <td className="px-4 py-2.5">
                    <ChevronRight
                      aria-hidden="true"
                      className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
})

const ResourcesByKind = memo(function ResourcesByKind({
  resources,
  loading,
}: {
  resources: Record<string, Resource[]>
  loading: boolean
}) {
  const kindCounts = useMemo(() => {
    const counts: Array<{ kind: string; plural: string; count: number }> = []
    for (const [plural, items] of Object.entries(resources)) {
      if (items.length > 0) {
        const kind = PLURAL_TO_KIND[plural] ?? plural
        counts.push({ kind, plural, count: items.length })
      }
    }
    return counts.sort((a, b) => b.count - a.count)
  }, [resources])

  const maxCount = useMemo(() => Math.max(1, ...kindCounts.map((k) => k.count)), [kindCounts])

  return (
    <section aria-labelledby="resources-by-kind-heading">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="resources-by-kind-heading" className="text-base font-semibold">
          Resources by Kind
        </h2>
        <Link
          to="/resources"
          className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          View all
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
      <div className="rounded-lg border bg-card p-4 shadow-sm">
        {loading && kindCounts.length === 0 ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-2 flex-1 rounded-full" />
                <Skeleton className="h-4 w-6" />
              </div>
            ))}
          </div>
        ) : kindCounts.length === 0 ? (
          <div className="py-8 text-center">
            <Database
              className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40"
              aria-hidden="true"
            />
            <p className="text-sm text-muted-foreground">No resources created yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {kindCounts.map(({ kind, count }) => (
              <div key={kind} className="flex items-center gap-3">
                <div className="w-28 shrink-0">
                  <KindBadge kind={kind} />
                </div>
                <div className="flex-1">
                  <div
                    className="h-2 overflow-hidden rounded-full bg-muted"
                    role="meter"
                    aria-label={`${kind}: ${count}`}
                    aria-valuenow={count}
                    aria-valuemin={0}
                    aria-valuemax={maxCount}
                  >
                    <div
                      className="h-full rounded-full bg-primary/60 transition-all"
                      style={{ width: `${(count / maxCount) * 100}%` }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-sm font-medium tabular-nums">{count}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
})

const SpendByCrew = memo(function SpendByCrew({
  executions,
  loading,
}: {
  executions: Execution[]
  loading: boolean
}) {
  const crewSpend = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of executions) {
      const cost = parseCost(e.cost_usd)
      if (cost > 0) {
        map.set(e.crew_name, (map.get(e.crew_name) ?? 0) + cost)
      }
    }
    return Array.from(map.entries())
      .map(([name, spend]) => ({ name, spend }))
      .sort((a, b) => b.spend - a.spend)
      .slice(0, 10)
  }, [executions])

  const maxSpend = useMemo(() => Math.max(0.001, ...crewSpend.map((c) => c.spend)), [crewSpend])

  return (
    <section aria-labelledby="spend-by-crew-heading">
      <div className="mb-3 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-primary" aria-hidden="true" />
        <h2 id="spend-by-crew-heading" className="text-base font-semibold">
          Spend by Crew
        </h2>
      </div>
      <div className="rounded-lg border bg-card p-4 shadow-sm">
        {loading && crewSpend.length === 0 ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-2 flex-1 rounded-full" />
                <Skeleton className="h-4 w-12" />
              </div>
            ))}
          </div>
        ) : crewSpend.length === 0 ? (
          <div className="py-8 text-center">
            <DollarSign
              className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40"
              aria-hidden="true"
            />
            <p className="text-sm text-muted-foreground">No spend data yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {crewSpend.map(({ name, spend }) => (
              <div key={name} className="flex items-center gap-3">
                <span className="w-28 shrink-0 truncate text-sm font-medium" title={name}>
                  {name}
                </span>
                <div className="flex-1">
                  <div
                    className="h-2 overflow-hidden rounded-full bg-muted"
                    role="meter"
                    aria-label={`${name}: ${formatCost(spend)}`}
                    aria-valuenow={spend}
                    aria-valuemin={0}
                    aria-valuemax={maxSpend}
                  >
                    <div
                      className={cn(
                        'h-full rounded-full transition-all',
                        spend / maxSpend > 0.75 ? 'bg-amber-500/70' : 'bg-primary/60',
                      )}
                      style={{ width: `${(spend / maxSpend) * 100}%` }}
                      title={spend / maxSpend > 0.75 ? 'High spend' : undefined}
                    />
                  </div>
                </div>
                <span className="w-16 text-right text-sm tabular-nums text-muted-foreground">
                  {formatCost(spend)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
})

const SpendOverTime = memo(function SpendOverTime({
  executions,
  loading,
}: {
  executions: Execution[]
  loading: boolean
}) {
  const dailySpend = useMemo(() => {
    const now = new Date()
    const days: Array<{ label: string; date: string; spend: number }> = []
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(d.getDate() - i)
      const dateStr = d.toISOString().slice(0, 10)
      const dayLabel =
        i === 0
          ? 'Today'
          : i === 1
            ? 'Yesterday'
            : d.toLocaleDateString(undefined, { weekday: 'short' })
      days.push({ label: dayLabel, date: dateStr, spend: 0 })
    }

    const daysByDate = new Map(days.map((d) => [d.date, d]))
    for (const e of executions) {
      if (!e.created_at) continue
      const eDate = e.created_at.slice(0, 10)
      const cost = parseCost(e.cost_usd)
      if (cost > 0) {
        const day = daysByDate.get(eDate)
        if (day) day.spend += cost
      }
    }

    return days
  }, [executions])

  const maxDailySpend = useMemo(
    () => Math.max(0.001, ...dailySpend.map((d) => d.spend)),
    [dailySpend],
  )

  const totalWeekSpend = useMemo(
    () => dailySpend.reduce((sum, d) => sum + d.spend, 0),
    [dailySpend],
  )

  return (
    <section aria-labelledby="spend-over-time-heading">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-primary" aria-hidden="true" />
        <h2 id="spend-over-time-heading" className="text-base font-semibold">
          Spend Over Time
        </h2>
        {totalWeekSpend > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            7-day total: {formatCost(totalWeekSpend)}
          </span>
        )}
      </div>
      <div className="rounded-lg border bg-card p-4 shadow-sm">
        {loading && totalWeekSpend === 0 ? (
          <div className="flex items-end gap-2" style={{ height: 120 }}>
            {[20, 45, 12, 60, 35, 50, 28].map((h, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <Skeleton className="h-3 w-8" />
                <div className="flex w-full flex-1 items-end justify-center">
                  <div
                    className="w-full max-w-8 animate-pulse rounded-t bg-muted/60 motion-reduce:animate-none"
                    style={{ height: `${h}px` }}
                  />
                </div>
                <Skeleton className="h-3 w-8" />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-end gap-2" style={{ height: 120 }}>
            {dailySpend.map(({ label, date, spend }) => (
              <div key={date} className="flex flex-1 flex-col items-center gap-1">
                <span
                  className={cn(
                    'text-[10px] tabular-nums',
                    spend > 0 ? 'text-foreground' : 'text-muted-foreground/50',
                  )}
                >
                  {spend > 0 ? formatCost(spend) : ''}
                </span>
                <div className="flex w-full flex-1 items-end justify-center">
                  <div
                    className={cn(
                      'w-full max-w-8 rounded-t transition-all',
                      spend > 0 ? 'bg-primary/60' : 'bg-muted',
                    )}
                    style={{
                      height: spend > 0 ? `${Math.max(4, (spend / maxDailySpend) * 80)}px` : '4px',
                    }}
                    role="meter"
                    aria-label={`${label}: ${formatCost(spend)}`}
                    aria-valuenow={spend}
                    aria-valuemin={0}
                    aria-valuemax={maxDailySpend}
                  />
                </div>
                <span className="text-[10px] text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
})

function QuickActions() {
  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="mb-3 text-base font-semibold">
        Quick Actions
      </h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <Link
          to="/studio"
          className="flex items-center gap-3 rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <PenTool className="h-5 w-5 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium">Open Studio</p>
            <p className="text-xs text-muted-foreground">Visual graph editor</p>
          </div>
        </Link>
        <Link
          to="/marketplace"
          className="flex items-center gap-3 rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Store className="h-5 w-5 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium">Import from Marketplace</p>
            <p className="text-xs text-muted-foreground">Browse starter templates</p>
          </div>
        </Link>
        <Link
          to="/models"
          className="flex items-center gap-3 rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Cpu className="h-5 w-5 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium">Add Model</p>
            <p className="text-xs text-muted-foreground">Configure LLM connections</p>
          </div>
        </Link>
      </div>
    </section>
  )
}

export default function Dashboard() {
  useDocumentTitle('Dashboard')

  const {
    resources,
    loading: resourcesLoading,
    fetchAllResources,
  } = useResourceStore(
    useShallow((s) => ({
      resources: s.resources,
      loading: s.loading,
      fetchAllResources: s.fetchAllResources,
    })),
  )

  const {
    executions,
    loading: executionsLoading,
    fetchExecutions,
  } = useExecutionStore(
    useShallow((s) => ({
      executions: s.executions,
      loading: s.loading,
      fetchExecutions: s.fetchExecutions,
    })),
  )

  useEffect(() => {
    void fetchAllResources()
  }, [fetchAllResources])

  useEffect(() => {
    void fetchExecutions()
  }, [fetchExecutions])

  const totalResources = useMemo(
    () => Object.values(resources).reduce((sum, items) => sum + items.length, 0),
    [resources],
  )

  const totalModels = useMemo(() => (resources['llm-connections'] ?? []).length, [resources])

  const totalAutomations = useMemo(() => (resources['automations'] ?? []).length, [resources])

  const { activeExecutions, totalSpend } = useMemo(() => {
    let active = 0
    let spend = 0
    for (const e of executions) {
      if (e.status === 'running' || e.status === 'queued') active++
      spend += parseCost(e.cost_usd)
    }
    return { activeExecutions: active, totalSpend: spend }
  }, [executions])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <PageHeader title="Dashboard" description="Overview of your agent management platform" />
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard
            label="Total Resources"
            value={totalResources}
            icon={Database}
            loading={resourcesLoading && totalResources === 0}
            href="/resources"
            accent="blue"
          />
          <StatCard
            label="Active Executions"
            value={activeExecutions}
            icon={Play}
            loading={executionsLoading && executions.length === 0}
            href="/executions"
            accent="green"
          />
          <StatCard
            label="LLM Spend"
            value={totalSpend > 0 ? formatCost(totalSpend) : '$0.00'}
            icon={DollarSign}
            loading={executionsLoading && executions.length === 0}
            href="/executions"
            accent="amber"
          />
          <StatCard
            label="Total Models"
            value={totalModels}
            icon={Cpu}
            loading={resourcesLoading && totalResources === 0}
            href="/models"
            accent="violet"
          />
          <StatCard
            label="Automations"
            value={totalAutomations}
            icon={Timer}
            loading={resourcesLoading && totalResources === 0}
            href="/automations"
            accent="rose"
          />
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <RecentExecutions executions={executions} loading={executionsLoading} />
          </div>
          <div className="lg:col-span-2">
            <ResourcesByKind resources={resources} loading={resourcesLoading} />
          </div>
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          <SpendByCrew executions={executions} loading={executionsLoading} />
          <SpendOverTime executions={executions} loading={executionsLoading} />
        </div>

        <div className="mt-8">
          <QuickActions />
        </div>
      </div>
    </div>
  )
}
