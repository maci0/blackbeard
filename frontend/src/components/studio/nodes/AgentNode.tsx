import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { User } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function AgentNode({ data, selected }: NodeProps) {
  const role = data['role'] as string | undefined
  const goal = data['goal'] as string | undefined
  const llm = data['llm'] as string | undefined
  const tools = Array.isArray(data['tools']) ? (data['tools'] as unknown[]) : []

  return (
    <div
      className={cn(
        'w-[200px] rounded-xl border bg-card shadow-sm overflow-hidden transition-all duration-150',
        selected
          ? 'border-violet-400 ring-2 ring-violet-300 ring-offset-1 shadow-violet-100 shadow-md'
          : 'border-slate-200 hover:border-violet-200 hover:shadow-md',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !border-2 !border-violet-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-violet-600 to-violet-500">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-white/20 text-white">
          <User className="w-3 h-3" />
        </div>
        <span className="text-[10px] font-bold text-white/90 uppercase tracking-widest">
          Agent
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-2.5 space-y-1.5">
        <p className="font-semibold text-sm text-foreground truncate leading-tight">
          {role ?? 'Unnamed Agent'}
        </p>
        {goal ? (
          <p className="text-[11px] text-muted-foreground line-clamp-2 leading-snug">{goal}</p>
        ) : (
          <p className="text-[11px] text-slate-300 italic">No goal set</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {llm && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-violet-50 text-violet-700 border border-violet-100">
              {llm}
            </span>
          )}
          {tools.length > 0 && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-slate-50 text-slate-600 border border-slate-100">
              {tools.length} tool{tools.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !border-2 !border-violet-400 !bg-white"
      />
    </div>
  )
})
