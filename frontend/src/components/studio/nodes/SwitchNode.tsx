import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { ToggleLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CLIP_PATHS } from './shapes'

export default memo(function SwitchNode({ data, selected }: NodeProps) {
  const expression = (data['expression'] as string | undefined) ?? ''
  const cases = (data['cases'] as string[] | undefined) ?? []

  return (
    <div
      aria-label={`Switch: ${expression || 'no expression'}, ${cases.length} cases`}
      className="relative w-[170px]"
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-[1.5px] !border-cyan-400 !bg-white"
        id="input"
      />

      <div
        className={cn(
          'overflow-hidden border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.25)] ring-2 ring-cyan-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(6,182,212,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-cyan-200 hover:shadow-md dark:border-slate-700',
        )}
        style={{ clipPath: CLIP_PATHS.hexagonal }}
      >
        <div className="flex items-center gap-1.5 bg-gradient-to-r from-cyan-600 to-cyan-400 px-4 py-1.5">
          <ToggleLeft className="h-3.5 w-3.5 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">
            Switch
          </span>
        </div>

        <div className="space-y-1 px-4 py-1.5">
          {expression ? (
            <p className="truncate font-mono text-[10px] text-foreground/80" title={expression}>
              {expression}
            </p>
          ) : (
            <p className="text-[10px] italic text-muted-foreground/60">No expression</p>
          )}

          {cases.length > 0 ? (
            <div className="flex flex-wrap gap-0.5">
              {cases.slice(0, 4).map((c, i) => (
                <span
                  key={i}
                  className="rounded border border-cyan-100 bg-cyan-50 px-1 py-px text-[9px] font-medium text-cyan-700 dark:border-cyan-800 dark:bg-cyan-950 dark:text-cyan-300"
                >
                  {c}
                </span>
              ))}
              {cases.length > 4 && (
                <span className="rounded border border-slate-200 bg-slate-50 px-1 py-px text-[9px] text-slate-500 dark:border-slate-700 dark:bg-slate-800">
                  +{cases.length - 4}
                </span>
              )}
            </div>
          ) : (
            <p className="text-[10px] italic text-muted-foreground/60">No cases</p>
          )}
        </div>
      </div>

      {cases.map((c, i) => (
        <Handle
          key={c}
          type="source"
          position={Position.Right}
          className="!h-2 !w-2 !border-[1.5px] !border-cyan-400 !bg-white"
          id={`case-${c}`}
          style={{ top: `${30 + (i * 50) / Math.max(cases.length, 1)}%` }}
        />
      ))}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-[1.5px] !border-slate-400 !bg-white"
        id="default"
        style={{ top: '85%' }}
      />
    </div>
  )
})
