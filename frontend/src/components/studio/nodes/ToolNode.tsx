import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function ToolNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const toolType = data['type'] as string | undefined
  const sandbox = data['sandbox'] as string | undefined
  const description = data['description'] as string | undefined

  const sandboxLabel = sandbox && sandbox !== 'none' ? sandbox : null

  return (
    <div
      aria-label={`Tool: ${name || 'Unnamed Tool'}`}
      className={cn(
        'w-[140px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-emerald-400 shadow-md shadow-emerald-100 ring-2 ring-emerald-300 ring-offset-1 dark:shadow-emerald-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-emerald-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      {/* Target handle on the left — agents can assign tools */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3.5 !w-3.5 !border-2 !border-emerald-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-emerald-500 px-3 py-1.5">
        <div className="flex h-5 w-5 items-center justify-center rounded-md bg-white/20 text-white">
          <Wrench className="h-3 w-3" />
        </div>
        <span className="text-2xs font-bold uppercase tracking-widest text-white/90">Tool</span>
      </div>

      {/* Body */}
      <div className="space-y-1 px-2.5 py-2">
        <p
          className="truncate text-xs font-semibold leading-tight text-foreground"
          title={name || 'Unnamed Tool'}
        >
          {name || 'Unnamed Tool'}
        </p>
        {description ? (
          <p
            className="text-2xs line-clamp-1 leading-snug text-muted-foreground"
            title={description}
          >
            {description}
          </p>
        ) : (
          <p className="text-2xs italic text-muted-foreground/60">No description</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {toolType && (
            <span className="text-2xs inline-flex items-center rounded-md border border-emerald-100 bg-emerald-50 px-1.5 py-0.5 font-semibold text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
              {toolType}
            </span>
          )}
          {sandboxLabel && (
            <span className="text-2xs inline-flex items-center rounded-md border border-amber-100 bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {sandboxLabel}
            </span>
          )}
        </div>
      </div>

      {/* Source handle on the right — tools connect to agents */}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3.5 !w-3.5 !border-2 !border-emerald-400 !bg-white"
      />
    </div>
  )
})
