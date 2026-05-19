import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { cn } from '@/lib/utils'

export default memo(function CrewGroupNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined

  return (
    <div
      aria-label={`Crew group: ${name || 'Unnamed Crew'}`}
      className={cn(
        'h-full w-full rounded-2xl border-2 border-dashed bg-muted/30 transition-all duration-150',
        selected
          ? 'border-slate-400 shadow-md dark:border-slate-500'
          : 'border-muted-foreground/20 hover:border-muted-foreground/30',
      )}
    >
      {/* Header label */}
      <div className="flex items-center gap-1.5 px-3 pb-1 pt-2">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
          Crew
        </span>
        {name && (
          <span className="text-2xs truncate font-semibold text-muted-foreground" title={name}>
            {name}
          </span>
        )}
      </div>
    </div>
  )
})
