import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { User } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function AgentNode({ data, selected }: NodeProps) {
  const role = data['role'] as string | undefined
  const goal = data['goal'] as string | undefined
  const llm = data['llm'] as string | undefined
  const llmDisplay = llm?.startsWith('ref:') ? llm.split('/').pop() || llm : llm
  const tools = Array.isArray(data['tools']) ? (data['tools'] as unknown[]) : []

  return (
    <div
      className={cn(
        'w-[200px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-violet-400 shadow-md shadow-violet-100 ring-2 ring-violet-300 ring-offset-1'
          : 'border-slate-200 hover:border-violet-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !border-2 !border-violet-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-violet-500 px-3 py-2">
        <div className="flex h-5 w-5 items-center justify-center rounded-md bg-white/20 text-white">
          <User className="h-3 w-3" />
        </div>
        <span className="text-2xs font-bold uppercase tracking-widest text-white/90">Agent</span>
      </div>

      {/* Body */}
      <div className="space-y-1.5 px-3 py-2.5">
        <p
          className="truncate text-sm font-semibold leading-tight text-foreground"
          title={role ?? 'Unnamed Agent'}
        >
          {role ?? 'Unnamed Agent'}
        </p>
        {goal ? (
          <p className="text-2xs line-clamp-2 leading-snug text-muted-foreground">{goal}</p>
        ) : (
          <p className="text-2xs italic text-muted-foreground/60">No goal set</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {llmDisplay && (
            <span className="text-2xs inline-flex items-center rounded-md border border-violet-100 bg-violet-50 px-1.5 py-0.5 font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300">
              {llmDisplay}
            </span>
          )}
          {tools.length > 0 && (
            <span className="text-2xs inline-flex items-center rounded-md border border-slate-100 bg-slate-50 px-1.5 py-0.5 font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {tools.length} tool{tools.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !border-2 !border-violet-400 !bg-white"
      />
    </div>
  )
})
