import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ListChecks } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function TaskNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const description = data['description'] as string | undefined
  const expectedOutput = data['expected_output'] as string | undefined
  const agent = data['agent'] as string | undefined

  return (
    <div
      className={cn(
        'w-[200px] rounded-xl border bg-card shadow-sm overflow-hidden transition-all duration-150',
        selected
          ? 'border-blue-400 ring-2 ring-blue-300 ring-offset-1 shadow-blue-100 shadow-md'
          : 'border-slate-200 dark:border-slate-700 hover:border-blue-200 hover:shadow-md',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !border-2 !border-blue-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-blue-600 to-blue-500">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-white/20 text-white">
          <ListChecks className="w-3 h-3" />
        </div>
        <span className="text-[11px] font-bold text-white/90 uppercase tracking-widest">
          Task
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-2.5 space-y-1.5">
        <p className="font-semibold text-sm text-foreground truncate leading-tight" title={name ?? 'Unnamed Task'}>
          {name ?? 'Unnamed Task'}
        </p>
        {description ? (
          <p className="text-[11px] text-muted-foreground line-clamp-2 leading-snug">{description}</p>
        ) : (
          <p className="text-[11px] text-muted-foreground/60 italic">No description</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {agent && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-100 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800">
              → {agent.startsWith('ref:') ? agent.split('/').pop() || agent : agent}
            </span>
          )}
          {expectedOutput && (
            <span
              className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[11px] font-semibold bg-slate-50 text-slate-500 border border-slate-100 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700 max-w-full truncate"
              title={expectedOutput}
            >
              out: {expectedOutput}
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !border-2 !border-blue-400 !bg-white"
      />
    </div>
  )
})
