import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { GitBranch } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CLIP_PATHS } from './shapes'

export default memo(function IfElseNode({ data, selected }: NodeProps) {
  const condition = (data['condition'] as string | undefined) ?? ''
  const trueLabel = (data['true_label'] as string | undefined) ?? 'True'
  const falseLabel = (data['false_label'] as string | undefined) ?? 'False'

  return (
    <div aria-label={`IF/ELSE: ${condition || 'no condition'}`} className="relative w-[170px]">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-[1.5px] !border-amber-400 !bg-white"
        id="input"
      />

      <div
        className={cn(
          'overflow-hidden border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.25)] ring-2 ring-amber-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(245,158,11,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-amber-200 hover:shadow-md dark:border-slate-700',
        )}
        style={{ clipPath: CLIP_PATHS.diamondTop }}
      >
        {/* Diamond-inspired header */}
        <div className="flex items-center gap-1.5 bg-gradient-to-r from-amber-500 to-yellow-400 px-2 py-1.5">
          <GitBranch className="h-3.5 w-3.5 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">
            IF / ELSE
          </span>
        </div>

        <div className="space-y-1 px-2 py-1.5">
          {condition ? (
            <p className="truncate font-mono text-[10px] text-foreground/80" title={condition}>
              {condition}
            </p>
          ) : (
            <p className="text-[10px] italic text-muted-foreground/60">No condition set</p>
          )}

          <div className="flex items-center justify-between text-[9px]">
            <span className="rounded bg-emerald-100 px-1 py-px font-semibold text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
              {trueLabel}
            </span>
            <span className="rounded bg-red-100 px-1 py-px font-semibold text-red-700 dark:bg-red-900 dark:text-red-300">
              {falseLabel}
            </span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-emerald-400 !bg-white"
        id="true"
        style={{ top: '40%' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-red-400 !bg-white"
        id="false"
        style={{ top: '70%' }}
      />
    </div>
  )
})
