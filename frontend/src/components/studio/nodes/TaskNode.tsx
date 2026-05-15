import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ListChecks } from 'lucide-react'
import { cn, parseRef } from '@/lib/utils'

export default memo(function TaskNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const description = data['description'] as string | undefined
  const expectedOutput = data['expected_output'] as string | undefined
  const agent = data['agent'] as string | undefined

  return (
    <div
      aria-label={`Task: ${name ?? 'Unnamed Task'}`}
      className={cn(
        'w-[140px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-blue-400 shadow-md shadow-blue-100 ring-2 ring-blue-300 ring-offset-1 dark:shadow-blue-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-blue-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-3.5 !w-3.5 !border-2 !border-blue-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-blue-500 px-3 py-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded-md bg-white/20 text-white">
          <ListChecks className="h-3 w-3" />
        </div>
        <span className="text-2xs font-bold uppercase tracking-widest text-white/90">Task</span>
      </div>

      {/* Body */}
      <div className="space-y-1 px-2.5 py-2">
        <p
          className="truncate text-xs font-semibold leading-tight text-foreground"
          title={name ?? 'Unnamed Task'}
        >
          {name ?? 'Unnamed Task'}
        </p>
        {description ? (
          <p className="text-2xs line-clamp-2 leading-snug text-muted-foreground">{description}</p>
        ) : (
          <p className="text-2xs italic text-muted-foreground/60">No description</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {agent && (
            <span className="text-2xs inline-flex items-center rounded-md border border-blue-100 bg-blue-50 px-1.5 py-0.5 font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300">
              → {parseRef(agent)}
            </span>
          )}
          {expectedOutput && (
            <span
              className="text-2xs inline-flex max-w-full items-center truncate rounded-md border border-slate-100 bg-slate-50 px-1.5 py-0.5 font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
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
        className="!h-3.5 !w-3.5 !border-2 !border-blue-400 !bg-white"
      />
    </div>
  )
})
