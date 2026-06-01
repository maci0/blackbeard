import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { Lock } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function GateNode({ data, selected }: NodeProps) {
  const controlExpr = (data['control'] as string | undefined) ?? ''
  const passWhen = (data['pass_when'] as string | undefined) ?? 'true'

  return (
    <div
      aria-label={`Gate: pass when ${controlExpr || 'control'} is ${passWhen}`}
      className="relative w-[150px]"
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-[1.5px] !border-teal-400 !bg-white"
        id="input"
        style={{ top: '35%' }}
      />
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !border-[1.5px] !border-amber-400 !bg-white"
        id="control"
      />

      <div
        className={cn(
          'overflow-hidden rounded-3xl border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-teal-400 shadow-[0_0_15px_rgba(20,184,166,0.25)] ring-2 ring-teal-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(20,184,166,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-teal-200 hover:shadow-md dark:border-slate-700',
        )}
      >
        <div className="flex items-center justify-center gap-1.5 bg-gradient-to-r from-teal-600 to-teal-400 px-2 py-1.5">
          <Lock className="h-3 w-3 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">Gate</span>
        </div>

        <div className="px-2 py-1.5 text-center">
          <p className="text-[9px] text-muted-foreground">
            Pass when <span className="font-semibold text-foreground">{passWhen}</span>
          </p>
          {controlExpr && (
            <p
              className="mt-0.5 truncate font-mono text-[10px] text-foreground/70"
              title={controlExpr}
            >
              {controlExpr}
            </p>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-teal-400 !bg-white"
        id="output"
      />
    </div>
  )
})
