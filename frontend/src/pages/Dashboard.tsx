import { useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Database,
  Play,
  Cpu,
  Timer,
  ChevronRight,
  LayoutDashboard,
  Store,
  ArrowRight,
  DollarSign,
} from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useResourceStore } from '@/stores/resourceStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useDocumentTitle } from '@/hooks'
import { PageHeader } from '@/components/ui/PageHeader'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { KindBadge } from '@/components/ui/KindBadge'
import { Spinner } from '@/components/ui/Spinner'
import { getDuration, formatCost } from '@/lib/formatters'
import { SmartTime } from '@/components/ui/SmartTime'
import { PLURAL_TO_KIND } from '@/lib/kinds'
import type { Resource, Execution } from '@/lib/types'

function StatCard({
  label,
  value,
  icon: Icon,
  loading,
  href,
}: {
  label: string
  value: number | string
  icon: React.ComponentType<{ className?: string }>
  loading: boolean
  href: string
}) {
  return (
    <Link
      to={href}
      className="group flex items-center gap-4 rounded-lg border bg-card p-5 shadow-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`${label}: ${loading ? 'loading' : value}`}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        {loading ? (
          <Spinner size="sm" label={`Loading ${label.toLowerCase()}`} />
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
}

function RecentExecutions({ executions, loading }: { executions: Execution[]; loading: boolean }) {
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
          <div className="flex items-center justify-center py-12">
            <Spinner label="Loading executions" />
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
                  className="group cursor-pointer transition-colors hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
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
}

function ResourcesByKind({
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
          <div className="flex items-center justify-center py-8">
            <Spinner label="Loading resources" />
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
}

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
          <LayoutDashboard className="h-5 w-5 text-primary" aria-hidden="true" />
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

  const activeExecutions = useMemo(
    () => executions.filter((e) => e.status === 'running' || e.status === 'queued').length,
    [executions],
  )

  const totalModels = useMemo(() => (resources['llm-connections'] ?? []).length, [resources])

  const totalAutomations = useMemo(() => (resources['automations'] ?? []).length, [resources])

  const totalSpend = useMemo(() => {
    let sum = 0
    for (const e of executions) {
      sum += typeof e.cost_usd === 'string' ? parseFloat(e.cost_usd) || 0 : e.cost_usd || 0
    }
    return sum
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
          />
          <StatCard
            label="Active Executions"
            value={activeExecutions}
            icon={Play}
            loading={executionsLoading && executions.length === 0}
            href="/executions"
          />
          <StatCard
            label="LLM Spend"
            value={totalSpend > 0 ? formatCost(totalSpend) : '$0.00'}
            icon={DollarSign}
            loading={executionsLoading && executions.length === 0}
            href="/executions"
          />
          <StatCard
            label="Total Models"
            value={totalModels}
            icon={Cpu}
            loading={resourcesLoading && totalResources === 0}
            href="/models"
          />
          <StatCard
            label="Automations"
            value={totalAutomations}
            icon={Timer}
            loading={resourcesLoading && totalResources === 0}
            href="/automations"
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

        <div className="mt-8">
          <QuickActions />
        </div>
      </div>
    </div>
  )
}
