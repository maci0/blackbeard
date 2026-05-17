import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function ToolNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const toolType = data['type'] as string | undefined
  const description = data['description'] as string | undefined

  return (
    <div
      aria-label={`Tool: ${name || 'Unnamed Tool'}`}
      className={cn(
        'w-[120px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-emerald-400 shadow-md shadow-emerald-100 ring-2 ring-emerald-300 ring-offset-1 dark:shadow-emerald-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-emerald-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border-2 !border-emerald-400 !bg-white"
      />

      <div className="flex items-center gap-1.5 bg-gradient-to-r from-emerald-600 to-emerald-500 px-2 py-1">
        <Wrench className="h-3 w-3 text-white/90" />
        <span className="text-2xs font-bold uppercase tracking-wider text-white/90">Tool</span>
      </div>

      <div className="space-y-0.5 px-2 py-1.5">
        <p
          className="text-2xs truncate font-semibold leading-tight text-foreground"
          title={name || 'Unnamed Tool'}
        >
          {name || 'Unnamed Tool'}
        </p>
        {description ? (
          <p
            className="line-clamp-1 text-[10px] leading-snug text-muted-foreground"
            title={description}
          >
            {description}
          </p>
        ) : null}

        {toolType && (
          <div className="pt-0.5">
            <span className="inline-flex items-center rounded border border-emerald-100 bg-emerald-50 px-1 py-px text-[10px] font-semibold text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              {toolType}
            </span>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border-2 !border-emerald-400 !bg-white"
      />
    </div>
  )
})
