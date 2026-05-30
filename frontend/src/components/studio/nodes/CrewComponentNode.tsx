import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { Users, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function CrewComponentNode({ data, selected }: NodeProps) {
  const crewName = (data['crew_name'] as string | undefined) ?? 'unnamed-crew'
  const description = (data['description'] as string | undefined) ?? ''
  const agentCount = (data['agent_count'] as number | undefined) ?? 0
  const taskCount = (data['task_count'] as number | undefined) ?? 0
  const inputs = (data['inputs'] as Array<{ name: string }> | undefined) ?? []

  return (
    <div
      aria-label={`Crew component: ${crewName}, ${agentCount} agents, ${taskCount} tasks`}
      className={cn(
        'w-[200px] overflow-hidden rounded-lg border-2 bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-primary shadow-[0_0_15px_rgba(99,102,241,0.3)] ring-2 ring-primary/30 ring-offset-1 dark:shadow-[0_0_15px_rgba(99,102,241,0.15)] dark:ring-offset-slate-900'
          : 'border-primary/30 hover:border-primary/50 hover:shadow-md',
      )}
    >
      {/* Input ports — one per crew input */}
      {inputs.length > 0 ? (
        inputs.map((input, i) => (
          <Handle
            key={input.name}
            type="target"
            position={Position.Left}
            className="!h-2.5 !w-2.5 !border-[1.5px] !border-primary !bg-white"
            id={`in-${input.name}`}
            style={{ top: `${25 + (i * 50) / Math.max(inputs.length - 1, 1)}%` }}
            title={input.name}
          />
        ))
      ) : (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-[1.5px] !border-primary !bg-white"
          id="input"
        />
      )}

      {/* Header */}
      <div className="flex items-center gap-2 bg-gradient-to-r from-primary to-primary/80 px-2.5 py-2">
        <Users className="h-4 w-4 text-white/90" />
        <span className="flex-1 truncate text-xs font-bold text-white">{crewName}</span>
        <span title="Double-click to drill in">
          <ChevronRight className="h-3 w-3 text-white/60" />
        </span>
      </div>

      {/* Body */}
      <div className="space-y-1.5 px-2.5 py-2">
        {description && (
          <p className="line-clamp-2 text-[10px] text-muted-foreground">{description}</p>
        )}

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded bg-violet-100 px-1.5 py-0.5 text-[9px] font-semibold text-violet-700 dark:bg-violet-900 dark:text-violet-300">
            {agentCount} agent{agentCount !== 1 ? 's' : ''}
          </span>
          <span className="inline-flex items-center gap-1 rounded bg-blue-100 px-1.5 py-0.5 text-[9px] font-semibold text-blue-700 dark:bg-blue-900 dark:text-blue-300">
            {taskCount} task{taskCount !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Input port labels */}
        {inputs.length > 0 && (
          <div className="flex flex-wrap gap-0.5">
            {inputs.slice(0, 3).map((input) => (
              <span
                key={input.name}
                className="rounded border border-primary/20 bg-primary/5 px-1 py-px text-[8px] font-medium text-primary"
              >
                {input.name}
              </span>
            ))}
            {inputs.length > 3 && (
              <span className="rounded border border-slate-200 bg-slate-50 px-1 py-px text-[8px] text-slate-500 dark:border-slate-700 dark:bg-slate-800">
                +{inputs.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Output port */}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-primary !bg-white"
        id="output"
      />
    </div>
  )
})
