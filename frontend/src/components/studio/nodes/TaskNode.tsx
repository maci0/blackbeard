import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ListChecks } from 'lucide-react'
import { cn, parseRef } from '@/lib/utils'

export default memo(function TaskNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const description = data['description'] as string | undefined
  const agent = data['agent'] as string | undefined

  return (
    <div
      aria-label={`Task: ${name || 'Unnamed Task'}`}
      className={cn(
        'w-[120px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-blue-400 shadow-md shadow-blue-100 ring-2 ring-blue-300 ring-offset-1 dark:shadow-blue-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-blue-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !border-2 !border-blue-400 !bg-white"
      />

      <div className="flex items-center gap-1.5 bg-gradient-to-r from-blue-600 to-blue-500 px-2 py-1">
        <ListChecks className="h-3 w-3 text-white/90" />
        <span className="text-2xs font-bold uppercase tracking-wider text-white/90">Task</span>
      </div>

      <div className="space-y-0.5 px-2 py-1.5">
        <p
          className="text-2xs truncate font-semibold leading-tight text-foreground"
          title={name || 'Unnamed Task'}
        >
          {name || 'Unnamed Task'}
        </p>
        {description ? (
          <p
            className="line-clamp-2 text-[10px] leading-snug text-muted-foreground"
            title={description}
          >
            {description}
          </p>
        ) : (
          <p className="text-[10px] italic text-muted-foreground/60">No description</p>
        )}

        <div className="flex flex-wrap gap-0.5 pt-0.5">
          {agent && (
            <span
              className="inline-flex max-w-full items-center truncate rounded border border-blue-100 bg-blue-50 px-1 py-px text-[10px] font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300"
              title={`Agent: ${parseRef(agent)}`}
            >
              → {parseRef(agent)}
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !border-2 !border-blue-400 !bg-white"
      />
    </div>
  )
})
