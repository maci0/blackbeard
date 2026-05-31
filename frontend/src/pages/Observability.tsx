import { memo, useEffect, useMemo, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  DollarSign,
  Activity,
  TrendingUp,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  ShieldAlert,
  Ban,
  ChevronRight,
  BarChart3,
  Cpu,
  AlertTriangle,
  RefreshCw,
  Hash,
  Gauge,
} from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useExecutionStore } from '@/stores/executionStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useDocumentTitle } from '@/hooks'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatCost, parseCost } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import { api } from '@/api/client'
import type { Execution } from '@/lib/types'

// ── Stat accent palette (matches Dashboard) ──

const STAT_ACCENT = {
  blue: 'bg-blue-100 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400',
  green: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400',
  amber: 'bg-amber-100 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400',
  violet: 'bg-violet-100 text-violet-600 dark:bg-violet-950/60 dark:text-violet-400',
  rose: 'bg-rose-100 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400',
  cyan: 'bg-cyan-100 text-cyan-600 dark:bg-cyan-950/60 dark:text-cyan-400',
} as const

type StatAccent = keyof typeof STAT_ACCENT

// ── Reusable stat card ──

const StatCard = memo(function StatCard({
  label,
  value,
  icon: Icon,
  loading,
  href,
  accent = 'blue',
  subtitle,
}: {
  label: string
  value: number | string
  icon: React.ComponentType<{ className?: string }>
  loading: boolean
  href?: string
  accent?: StatAccent
  subtitle?: string
}) {
  const content = (
    <>
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
        {subtitle && !loading && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {href && (
        <ChevronRight
          aria-hidden="true"
          className="h-4 w-4 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
        />
      )}
    </>
  )

  if (href) {
    return (
      <Link
        to={href}
        className="group flex items-center gap-4 rounded-lg border bg-card p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-accent/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`${label}: ${loading ? 'loading' : value}`}
      >
        {content}
      </Link>
    )
  }

  return (
    <div
      className="flex items-center gap-4 rounded-lg border bg-card p-5 shadow-sm"
      aria-label={`${label}: ${loading ? 'loading' : value}`}
    >
      {content}
    </div>
  )
})

// ── Section heading ──

function SectionHeading({
  id,
  icon: Icon,
  title,
}: {
  id: string
  icon: React.ComponentType<{ className?: string }>
  title: string
}) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
      <h2 id={id} className="text-base font-semibold">
        {title}
      </h2>
    </div>
  )
}

// ── Status breakdown chart ──

const STATUS_COLORS: Record<string, string> = {
  completed: 'bg-emerald-500/70',
  failed: 'bg-red-500/70',
  running: 'bg-blue-500/70',
  cancelled: 'bg-amber-500/70',
  queued: 'bg-gray-400/70',
}

const STATUS_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  completed: CheckCircle2,
  failed: XCircle,
  running: Activity,
  cancelled: Ban,
  queued: Clock,
}

const StatusBreakdown = memo(function StatusBreakdown({
  executions,
  loading,
}: {
  executions: Execution[]
  loading: boolean
}) {
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {
      completed: 0,
      failed: 0,
      running: 0,
      cancelled: 0,
      queued: 0,
    }
    for (const e of executions) {
      const status = e.status in counts ? e.status : 'queued'
      counts[status] = (counts[status] ?? 0) + 1
    }
    return Object.entries(counts)
      .map(([status, count]) => ({ status, count }))
      .filter(({ count }) => count > 0 || ['completed', 'failed', 'running'].includes(''))
  }, [executions])

  const maxCount = useMemo(() => Math.max(1, ...statusCounts.map((s) => s.count)), [statusCounts])

  const total = executions.length

  return (
    <section aria-labelledby="status-breakdown-heading">
      <SectionHeading id="status-breakdown-heading" icon={BarChart3} title="Status Breakdown" />
      <div className="rounded-lg border bg-card p-4 shadow-sm">
        {loading && total === 0 ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-2 flex-1 rounded-full" />
                <Skeleton className="h-4 w-8" />
              </div>
            ))}
          </div>
        ) : total === 0 ? (
          <div className="py-8 text-center">
            <Activity
              className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40"
              aria-hidden="true"
            />
            <p className="text-sm text-muted-foreground">No executions yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {statusCounts.map(({ status, count }) => {
              const StatusIcon = STATUS_ICONS[status] ?? Clock
              return (
                <div key={status} className="flex items-center gap-3">
                  <div className="flex w-28 shrink-0 items-center gap-1.5">
                    <StatusIcon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                    <span className="text-sm font-medium capitalize">{status}</span>
                  </div>
                  <div className="flex-1">
                    <div
                      className="h-2 overflow-hidden rounded-full bg-muted"
                      role="meter"
                      aria-label={`${status}: ${count}`}
                      aria-valuenow={count}
                      aria-valuemin={0}
                      aria-valuemax={maxCount}
                    >
                      <div
                        className={cn(
                          'h-full rounded-full transition-all',
                          STATUS_COLORS[status] ?? 'bg-gray-400/70',
                        )}
                        style={{ width: `${(count / maxCount) * 100}%` }}
                      />
                    </div>
                  </div>
                  <span className="w-10 text-right text-sm tabular-nums text-muted-foreground">
                    {count}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
})

// ── Spend by crew chart ──

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
    <section aria-labelledby="obs-spend-by-crew-heading">
      <SectionHeading id="obs-spend-by-crew-heading" icon={DollarSign} title="Spend by Crew" />
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

// ── Tokens by model chart ──

const TokensByModel = memo(function TokensByModel({
  executions,
  loading,
}: {
  executions: Execution[]
  loading: boolean
}) {
  const modelTokens = useMemo(() => {
    // Aggregate tokens from execution tasks, which carry agent/model info.
    // Since executions only expose total_tokens at top level without model
    // breakdown, we group by crew_name as a proxy for model usage.
    const map = new Map<string, { prompt: number; completion: number }>()
    for (const e of executions) {
      if (e.prompt_tokens === 0 && e.completion_tokens === 0) continue
      const key = e.crew_name
      const existing = map.get(key) ?? { prompt: 0, completion: 0 }
      existing.prompt += e.prompt_tokens
      existing.completion += e.completion_tokens
      map.set(key, existing)
    }
    return Array.from(map.entries())
      .map(([name, tokens]) => ({
        name,
        total: tokens.prompt + tokens.completion,
        prompt: tokens.prompt,
        completion: tokens.completion,
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10)
  }, [executions])

  const maxTokens = useMemo(() => Math.max(1, ...modelTokens.map((m) => m.total)), [modelTokens])

  return (
    <section aria-labelledby="tokens-by-model-heading">
      <SectionHeading id="tokens-by-model-heading" icon={Cpu} title="Tokens by Crew" />
      <div className="rounded-lg border bg-card p-4 shadow-sm">
        {loading && modelTokens.length === 0 ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-2 flex-1 rounded-full" />
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </div>
        ) : modelTokens.length === 0 ? (
          <div className="py-8 text-center">
            <Hash className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">No token data yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {modelTokens.map(({ name, total, prompt, completion }) => (
              <div key={name} className="flex items-center gap-3">
                <span className="w-28 shrink-0 truncate text-sm font-medium" title={name}>
                  {name}
                </span>
                <div className="flex-1">
                  <div
                    className="flex h-2 overflow-hidden rounded-full bg-muted"
                    role="meter"
                    aria-label={`${name}: ${total.toLocaleString()} tokens`}
                    aria-valuenow={total}
                    aria-valuemin={0}
                    aria-valuemax={maxTokens}
                  >
                    <div
                      className="h-full bg-blue-500/70 transition-all"
                      style={{ width: `${(prompt / maxTokens) * 100}%` }}
                      title={`Prompt: ${prompt.toLocaleString()}`}
                    />
                    <div
                      className="h-full bg-violet-500/70 transition-all"
                      style={{ width: `${(completion / maxTokens) * 100}%` }}
                      title={`Completion: ${completion.toLocaleString()}`}
                    />
                  </div>
                </div>
                <span className="w-20 text-right text-xs tabular-nums text-muted-foreground">
                  {total >= 1_000_000
                    ? `${(total / 1_000_000).toFixed(1)}M`
                    : total >= 1_000
                      ? `${(total / 1_000).toFixed(1)}k`
                      : total.toLocaleString()}
                </span>
              </div>
            ))}
            <div className="flex items-center justify-end gap-4 pt-1 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 rounded-full bg-blue-500/70"
                  aria-hidden="true"
                />
                Prompt
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 rounded-full bg-violet-500/70"
                  aria-hidden="true"
                />
                Completion
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  )
})

// ── Audit log event counts (for policy/safety section) ──

interface AuditLog {
  id: string
  action: string
  resource_kind?: string
  resource_name?: string
  timestamp: string
  details?: Record<string, unknown>
}

function useAuditLogCounts() {
  const [counts, setCounts] = useState({
    policyDenials: 0,
    guardrailTriggers: 0,
    budgetExceeded: 0,
  })
  const [loading, setLoading] = useState(true)

  const fetchCounts = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<{ items: AuditLog[]; total: number }>('/api/v1/audit-logs')
      const logs = result.items
      let policyDenials = 0
      let guardrailTriggers = 0
      let budgetExceeded = 0

      for (const log of logs) {
        const action = log.action.toLowerCase()
        if (action.includes('denied') || action.includes('policy_denied')) {
          policyDenials++
        }
        if (action.includes('guardrail') || action.includes('guard')) {
          guardrailTriggers++
        }
        if (action.includes('budget') || action.includes('exceeded')) {
          budgetExceeded++
        }
      }

      setCounts({ policyDenials, guardrailTriggers, budgetExceeded })
    } catch {
      // If audit logs are unavailable, show zeros rather than errors
      setCounts({ policyDenials: 0, guardrailTriggers: 0, budgetExceeded: 0 })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchCounts()
  }, [fetchCounts])

  return { counts, loading, refetch: fetchCounts }
}

// ── Main page ──

export default function Observability() {
  useDocumentTitle('Observability')

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

  const { counts: auditCounts, loading: auditLoading, refetch: refetchAudit } = useAuditLogCounts()

  useEffect(() => {
    void fetchExecutions()
  }, [fetchExecutions])

  useEffect(() => {
    void fetchAllResources()
  }, [fetchAllResources])

  const handleRefresh = useCallback(() => {
    void fetchExecutions()
    void fetchAllResources()
    void refetchAudit()
  }, [fetchExecutions, fetchAllResources, refetchAudit])

  // ── Budget utilization ──

  const { totalSpend, budgetTotal, spendRate } = useMemo(() => {
    let spend = 0
    let earliestRunning: number | null = null
    let latestRunning: number | null = null

    for (const e of executions) {
      spend += parseCost(e.cost_usd)
      if (e.started_at) {
        const t = new Date(e.started_at).getTime()
        if (!isNaN(t)) {
          if (earliestRunning === null || t < earliestRunning) earliestRunning = t
          if (latestRunning === null || t > latestRunning) latestRunning = t
        }
      }
    }

    // Compute budget from AgentPolicy resources
    const policies = resources['agent-policies'] ?? []
    let budget = 0
    for (const p of policies) {
      const maxUsd = (p.spec as { max_usd?: number }).max_usd
      if (typeof maxUsd === 'number' && maxUsd > 0) {
        budget += maxUsd
      }
      // Also check nested budget object
      const budgetSpec = (p.spec as { budget?: { max_usd?: number } }).budget
      if (typeof budgetSpec?.max_usd === 'number' && budgetSpec.max_usd > 0) {
        budget += budgetSpec.max_usd
      }
    }

    // Spend rate: dollars per hour based on the time span of executions
    let rate = 0
    if (earliestRunning !== null && spend > 0) {
      const now = Date.now()
      const hoursElapsed = (now - earliestRunning) / (1000 * 60 * 60)
      if (hoursElapsed > 0.01) {
        rate = spend / hoursElapsed
      }
    }

    return {
      totalSpend: spend,
      budgetTotal: budget,
      spendRate: rate,
    }
  }, [executions, resources])

  const budgetRemaining = budgetTotal > 0 ? Math.max(0, budgetTotal - totalSpend) : 0

  // ── Execution metrics ──

  const { totalExecs, successRate, avgDurationStr, activeCount } = useMemo(() => {
    const total = executions.length
    const completed = executions.filter((e) => e.status === 'completed').length
    const active = executions.filter((e) => e.status === 'running' || e.status === 'queued').length
    const rate = total > 0 ? Math.round((completed / total) * 100) : 0

    // Average duration of completed executions
    let durationSumMs = 0
    let durationCount = 0
    for (const e of executions) {
      if (e.started_at && e.completed_at) {
        const s = new Date(e.started_at).getTime()
        const c = new Date(e.completed_at).getTime()
        if (!isNaN(s) && !isNaN(c) && c > s) {
          durationSumMs += c - s
          durationCount++
        }
      }
    }
    const avgMs = durationCount > 0 ? durationSumMs / durationCount : 0
    let avgStr = '--'
    if (avgMs > 0) {
      const sec = Math.round(avgMs / 1000)
      if (sec < 60) avgStr = `${sec}s`
      else if (sec < 3600) avgStr = `${Math.floor(sec / 60)}m ${sec % 60}s`
      else avgStr = `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
    }

    return {
      totalExecs: total,
      successRate: rate,
      avgDurationStr: avgStr,
      activeCount: active,
    }
  }, [executions])

  // ── Token totals ──

  const { totalPromptTokens, totalCompletionTokens } = useMemo(() => {
    let prompt = 0
    let completion = 0
    for (const e of executions) {
      prompt += e.prompt_tokens
      completion += e.completion_tokens
    }
    return { totalPromptTokens: prompt, totalCompletionTokens: completion }
  }, [executions])

  function formatTokens(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
    return n.toLocaleString()
  }

  const loading = executionsLoading && executions.length === 0

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <PageHeader
            title="Observability"
            description="Budget, execution, and safety metrics across your platform"
            actions={
              <button
                type="button"
                onClick={handleRefresh}
                className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Refresh data"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </button>
            }
          />
        </div>

        {/* ── Budget Utilization ── */}
        <section aria-labelledby="budget-section-heading" className="mb-8">
          <SectionHeading
            id="budget-section-heading"
            icon={DollarSign}
            title="Budget Utilization"
          />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Total Spend"
              value={totalSpend > 0 ? formatCost(totalSpend) : '$0.00'}
              icon={DollarSign}
              loading={loading}
              href="/executions"
              accent="amber"
            />
            <StatCard
              label="Budget Remaining"
              value={budgetTotal > 0 ? formatCost(budgetRemaining) : 'No limit'}
              icon={Gauge}
              loading={loading || resourcesLoading}
              accent="green"
              subtitle={budgetTotal > 0 ? `of ${formatCost(budgetTotal)} total` : undefined}
            />
            <StatCard
              label="Spend Rate"
              value={spendRate > 0 ? `${formatCost(spendRate)}/hr` : '$0.00/hr'}
              icon={TrendingUp}
              loading={loading}
              accent="blue"
            />
          </div>

          <div className="mt-4">
            <SpendByCrew executions={executions} loading={executionsLoading} />
          </div>
        </section>

        {/* ── Execution Metrics ── */}
        <section aria-labelledby="execution-section-heading" className="mb-8">
          <SectionHeading
            id="execution-section-heading"
            icon={Activity}
            title="Execution Metrics"
          />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total Executions"
              value={totalExecs}
              icon={Activity}
              loading={loading}
              href="/executions"
              accent="blue"
            />
            <StatCard
              label="Success Rate"
              value={`${successRate}%`}
              icon={CheckCircle2}
              loading={loading}
              accent="green"
            />
            <StatCard
              label="Avg Duration"
              value={avgDurationStr}
              icon={Clock}
              loading={loading}
              accent="violet"
            />
            <StatCard
              label="Active Now"
              value={activeCount}
              icon={Zap}
              loading={loading}
              href="/executions"
              accent="amber"
            />
          </div>

          <div className="mt-4">
            <StatusBreakdown executions={executions} loading={executionsLoading} />
          </div>
        </section>

        {/* ── Token Usage ── */}
        <section aria-labelledby="token-section-heading" className="mb-8">
          <SectionHeading id="token-section-heading" icon={Hash} title="Token Usage" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Total Tokens"
              value={formatTokens(totalPromptTokens + totalCompletionTokens)}
              icon={Hash}
              loading={loading}
              accent="blue"
            />
            <StatCard
              label="Prompt Tokens"
              value={formatTokens(totalPromptTokens)}
              icon={Hash}
              loading={loading}
              accent="cyan"
            />
            <StatCard
              label="Completion Tokens"
              value={formatTokens(totalCompletionTokens)}
              icon={Hash}
              loading={loading}
              accent="violet"
            />
          </div>

          <div className="mt-4">
            <TokensByModel executions={executions} loading={executionsLoading} />
          </div>
        </section>

        {/* ── Policy & Safety ── */}
        <section aria-labelledby="safety-section-heading">
          <SectionHeading
            id="safety-section-heading"
            icon={ShieldAlert}
            title="Policy and Safety"
          />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Policy Denials"
              value={auditCounts.policyDenials}
              icon={Ban}
              loading={auditLoading}
              href="/audit-logs"
              accent="rose"
            />
            <StatCard
              label="Guardrail Triggers"
              value={auditCounts.guardrailTriggers}
              icon={ShieldAlert}
              loading={auditLoading}
              href="/audit-logs"
              accent="amber"
            />
            <StatCard
              label="Budget Exceeded"
              value={auditCounts.budgetExceeded}
              icon={AlertTriangle}
              loading={auditLoading}
              href="/audit-logs"
              accent="rose"
            />
          </div>
        </section>
      </div>
    </div>
  )
}
