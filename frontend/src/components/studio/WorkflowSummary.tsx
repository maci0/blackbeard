import { useMemo } from 'react'
import {
  User,
  ListChecks,
  Wrench,
  Workflow,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Node } from '@xyflow/react'

interface WorkflowSummaryProps {
  nodes: Node[]
  executionStatus?: string
}

const NODE_TYPE_LABELS: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }> }
> = {
  agent: { label: 'Agents', icon: User },
  task: { label: 'Tasks', icon: ListChecks },
  tool: { label: 'Tools', icon: Wrench },
  flowStep: { label: 'Steps', icon: Workflow },
}

const EXEC_STATUS_CONFIG: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; color: string }
> = {
  success: { label: 'Complete', icon: CheckCircle2, color: 'text-emerald-500' },
  error: { label: 'Failed', icon: XCircle, color: 'text-red-500' },
  running: { label: 'Running', icon: Loader2, color: 'text-blue-500' },
  pending: { label: 'Pending', icon: Clock, color: 'text-muted-foreground' },
}

export function WorkflowSummary({ nodes, executionStatus }: WorkflowSummaryProps) {
  const stats = useMemo(() => {
    const typeCounts: Record<string, number> = {}
    const statusCounts: Record<string, number> = { success: 0, error: 0, running: 0, pending: 0 }
    let hasExecData = false

    for (const node of nodes) {
      if (node.type === 'crewGroup' || node.type === 'stickyNote') continue
      const t = node.type ?? 'unknown'
      typeCounts[t] = (typeCounts[t] ?? 0) + 1

      const execStatus = node.data?.['_execStatus'] as string | undefined
      if (execStatus) {
        hasExecData = true
        if (execStatus in statusCounts) {
          statusCounts[execStatus]!++
        }
      }
    }

    return { typeCounts, statusCounts, hasExecData }
  }, [nodes])

  const typeEntries = Object.entries(stats.typeCounts)
    .filter(([type]) => type in NODE_TYPE_LABELS)
    .sort(([a], [b]) => {
      const order = ['agent', 'task', 'tool', 'flowStep']
      return order.indexOf(a) - order.indexOf(b)
    })

  if (typeEntries.length === 0) return null

  return (
    <div className="flex shrink-0 items-center gap-3 border-b bg-card/80 px-3 py-1 text-[11px] text-muted-foreground">
      {typeEntries.map(([type, count]) => {
        const config = NODE_TYPE_LABELS[type]!
        const Icon = config.icon
        return (
          <span key={type} className="inline-flex items-center gap-1">
            <Icon className="h-3 w-3" />
            <span className="font-medium text-foreground/80">{count}</span>
            <span>{config.label}</span>
          </span>
        )
      })}

      {(stats.hasExecData || executionStatus) && (
        <>
          <span className="text-border">|</span>
          {Object.entries(stats.statusCounts)
            .filter(([, count]) => count > 0)
            .map(([status, count]) => {
              const config = EXEC_STATUS_CONFIG[status]!
              const Icon = config.icon
              return (
                <span key={status} className="inline-flex items-center gap-1">
                  <Icon
                    className={cn(
                      'h-3 w-3',
                      config.color,
                      status === 'running' && 'animate-spin motion-reduce:animate-none',
                    )}
                  />
                  <span className="font-medium">{count}</span>
                  <span>{config.label}</span>
                </span>
              )
            })}
        </>
      )}
    </div>
  )
}
