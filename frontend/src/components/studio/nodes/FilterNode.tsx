import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { Filter } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CLIP_PATHS } from './shapes'

export default memo(function FilterNode({ data, selected }: NodeProps) {
  const condition = (data['condition'] as string | undefined) ?? ''

  return (
    <div aria-label={`Filter: ${condition || 'no condition'}`} className="relative w-[170px]">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-[1.5px] !border-orange-400 !bg-white"
        id="input"
      />

      <div
        className={cn(
          'overflow-hidden border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-orange-400 shadow-[0_0_15px_rgba(249,115,22,0.25)] ring-2 ring-orange-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(249,115,22,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-orange-200 hover:shadow-md dark:border-slate-700',
        )}
        style={{ clipPath: CLIP_PATHS.diamondTop }}
      >
        <div className="flex items-center gap-1.5 bg-gradient-to-r from-orange-500 to-orange-400 px-2 py-1.5">
          <Filter className="h-3.5 w-3.5 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">
            Filter
          </span>
        </div>

        <div className="space-y-1 px-2 py-1.5">
          {condition ? (
            <p className="truncate font-mono text-[10px] text-foreground/80" title={condition}>
              {condition}
            </p>
          ) : (
            <p className="text-[10px] italic text-muted-foreground/60">No filter condition</p>
          )}
          <div className="flex items-center justify-between text-[9px]">
            <span className="rounded bg-emerald-100 px-1 py-px font-semibold text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
              Passed
            </span>
            <span className="rounded bg-slate-100 px-1 py-px font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              Rejected
            </span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-emerald-400 !bg-white"
        id="passed"
        style={{ top: '40%' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-slate-400 !bg-white"
        id="rejected"
        style={{ top: '70%' }}
      />
    </div>
  )
})
