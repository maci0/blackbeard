import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { Repeat } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function LoopNode({ data, selected }: NodeProps) {
  const itemsExpr = (data['items_expr'] as string | undefined) ?? ''
  const maxIterations = (data['max_iterations'] as number | undefined) ?? 100
  const parallel = (data['parallel'] as boolean | undefined) ?? false

  return (
    <div
      aria-label={`Loop: ${itemsExpr || 'no items'}, max ${maxIterations}`}
      className="relative w-[165px]"
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-[1.5px] !border-pink-400 !bg-white"
        id="items"
      />

      <div
        className={cn(
          'overflow-hidden rounded-2xl border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-pink-400 shadow-[0_0_15px_rgba(236,72,153,0.25)] ring-2 ring-pink-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(236,72,153,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-pink-200 hover:shadow-md dark:border-slate-700',
        )}
      >
        <div className="flex items-center gap-1.5 bg-gradient-to-r from-pink-500 to-pink-400 px-2 py-1.5">
          <Repeat className="h-3.5 w-3.5 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">Loop</span>
        </div>

        <div className="space-y-1 px-2 py-1.5">
          {itemsExpr ? (
            <p className="truncate font-mono text-[10px] text-foreground/80" title={itemsExpr}>
              {itemsExpr}
            </p>
          ) : (
            <p className="text-[10px] italic text-muted-foreground/60">No items expression</p>
          )}

          <div className="flex items-center gap-1.5 text-[9px]">
            <span className="rounded bg-pink-100 px-1 py-px font-semibold text-pink-700 dark:bg-pink-900 dark:text-pink-300">
              max {maxIterations}
            </span>
            {parallel && (
              <span className="rounded bg-purple-100 px-1 py-px font-semibold text-purple-700 dark:bg-purple-900 dark:text-purple-300">
                parallel
              </span>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-pink-400 !bg-white"
        id="body"
        style={{ top: '40%' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !border-[1.5px] !border-pink-400 !bg-white"
        id="results"
      />
    </div>
  )
})
