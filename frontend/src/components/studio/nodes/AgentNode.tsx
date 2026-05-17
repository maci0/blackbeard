import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { User } from 'lucide-react'
import { cn, parseRef } from '@/lib/utils'

export default memo(function AgentNode({ data, selected }: NodeProps) {
  const role = data['role'] as string | undefined
  const goal = data['goal'] as string | undefined
  const llm = data['llm'] as string | undefined
  const llmDisplay = llm ? parseRef(llm) : undefined

  return (
    <div
      aria-label={`Agent: ${role || 'Unnamed Agent'}`}
      className={cn(
        'w-[120px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-violet-400 shadow-md shadow-violet-100 ring-2 ring-violet-300 ring-offset-1 dark:shadow-violet-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-violet-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !border-2 !border-violet-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-1.5 bg-gradient-to-r from-violet-600 to-violet-500 px-2 py-1">
        <User className="h-3 w-3 text-white/90" />
        <span className="text-2xs font-bold uppercase tracking-wider text-white/90">Agent</span>
      </div>

      {/* Body */}
      <div className="space-y-0.5 px-2 py-1.5">
        <p
          className="text-2xs truncate font-semibold leading-tight text-foreground"
          title={role || 'Unnamed Agent'}
        >
          {role || 'Unnamed Agent'}
        </p>
        {goal ? (
          <p className="line-clamp-2 text-[10px] leading-snug text-muted-foreground" title={goal}>
            {goal}
          </p>
        ) : (
          <p className="text-2xs italic text-muted-foreground/60">No goal set</p>
        )}

        {/* Badges */}
        {llmDisplay && (
          <div className="pt-0.5">
            <span
              className="inline-flex max-w-full items-center truncate rounded border border-violet-100 bg-violet-50 px-1 py-px text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300"
              title={llmDisplay}
            >
              {llmDisplay}
            </span>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !border-2 !border-violet-400 !bg-white"
      />
    </div>
  )
})
