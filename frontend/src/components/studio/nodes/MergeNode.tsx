import { memo } from 'react'
import { type NodeProps, Handle, Position } from '@xyflow/react'
import { Combine } from 'lucide-react'
import { cn } from '@/lib/utils'

export default memo(function MergeNode({ data, selected }: NodeProps) {
  const inputCount = (data['input_count'] as number | undefined) ?? 2
  const strategy = (data['strategy'] as string | undefined) ?? 'wait_all'

  return (
    <div aria-label={`Merge: ${inputCount} inputs, ${strategy}`} className="relative w-[150px]">
      {Array.from({ length: inputCount }).map((_, i) => (
        <Handle
          key={i}
          type="target"
          position={Position.Left}
          className="!h-2 !w-2 !border-[1.5px] !border-indigo-400 !bg-white"
          id={`in-${i}`}
          style={{ top: `${25 + (i * 50) / Math.max(inputCount - 1, 1)}%` }}
        />
      ))}

      <div
        className={cn(
          'overflow-hidden rounded-3xl border bg-card shadow-sm transition-all duration-150',
          selected
            ? 'border-indigo-400 shadow-[0_0_15px_rgba(99,102,241,0.25)] ring-2 ring-indigo-300 ring-offset-1 dark:shadow-[0_0_15px_rgba(99,102,241,0.15)] dark:ring-offset-slate-900'
            : 'border-slate-200 hover:border-indigo-200 hover:shadow-md dark:border-slate-700',
        )}
      >
        <div className="flex items-center justify-center gap-1.5 bg-gradient-to-r from-indigo-600 to-indigo-400 px-2 py-1.5">
          <Combine className="h-3.5 w-3.5 text-white/90" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">
            Merge
          </span>
        </div>

        <div className="px-2 py-1.5 text-center">
          <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300">
            {inputCount} inputs → 1
          </span>
          <p className="mt-1 text-[9px] text-muted-foreground">
            {strategy === 'wait_all'
              ? 'Wait for all'
              : strategy === 'first'
                ? 'First wins'
                : strategy}
          </p>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-[1.5px] !border-indigo-400 !bg-white"
        id="output"
      />
    </div>
  )
})
