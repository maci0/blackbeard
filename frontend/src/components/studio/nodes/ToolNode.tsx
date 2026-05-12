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
      className={cn(
        'w-[160px] rounded-xl border bg-card shadow-sm overflow-hidden transition-all duration-150',
        selected
          ? 'border-emerald-400 ring-2 ring-emerald-300 ring-offset-1 shadow-emerald-100 shadow-md'
          : 'border-slate-200 hover:border-emerald-200 hover:shadow-md',
      )}
    >
      {/* Header strip */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gradient-to-r from-emerald-600 to-emerald-500">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-white/20 text-white">
          <Wrench className="w-3 h-3" />
        </div>
        <span className="text-[10px] font-bold text-white/90 uppercase tracking-widest">
          Tool
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-2.5 space-y-1.5">
        <p className="font-semibold text-sm text-foreground truncate leading-tight">
          {name ?? 'Unnamed Tool'}
        </p>
        {description && (
          <p className="text-[11px] text-muted-foreground line-clamp-1 leading-snug">{description}</p>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {toolType && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">
              {toolType}
            </span>
          )}
          {sandboxLabel && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-100">
              {sandboxLabel}
            </span>
          )}
        </div>
      </div>

      {/* Source handle on the right — tools connect to agents */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !border-2 !border-emerald-400 !bg-white"
      />
    </div>
  )
})
