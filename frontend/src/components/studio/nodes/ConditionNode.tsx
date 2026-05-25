import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { GitBranch } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NodeShell } from './NodeShell'

export default memo(function ConditionNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const condition = data['condition'] as string | undefined
  const trueBranch = data['true_branch'] as string | undefined
  const falseBranch = data['false_branch'] as string | undefined

  return (
    <NodeShell
      color="amber"
      icon={GitBranch}
      label="Condition"
      ariaLabel={`Condition: ${name || 'Unnamed Condition'}`}
      selected={!!selected}
      width="w-[160px]"
      headerGradientTo="to-yellow-500"
    >
      <p
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Condition'}
      >
        {name || 'Unnamed Condition'}
      </p>

      <div className="flex items-center gap-1 pt-0.5">
        <span
          className={cn(
            'inline-flex h-4 w-4 items-center justify-center text-[9px] font-bold',
            'rotate-45 rounded-sm border border-amber-200 bg-amber-50 text-amber-700',
            'dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300',
          )}
          aria-hidden="true"
        >
          <span className="-rotate-45">?</span>
        </span>
        <span className="text-[10px] font-semibold text-amber-700 dark:text-amber-300">
          if / else
        </span>
      </div>

      {condition ? (
        <p
          className="truncate text-[10px] leading-snug text-muted-foreground"
          title={`Condition: ${condition}`}
        >
          {condition}
        </p>
      ) : (
        <p className="text-[10px] italic text-muted-foreground/60">No condition set</p>
      )}

      {(trueBranch || falseBranch) && (
        <div className="flex flex-wrap gap-0.5 pt-0.5">
          {trueBranch && (
            <span
              className="inline-flex items-center rounded border border-emerald-100 bg-emerald-50 px-1 py-px text-[9px] font-medium text-emerald-600 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-400"
              title={`True: ${trueBranch}`}
            >
              T: {trueBranch.slice(0, 10)}
            </span>
          )}
          {falseBranch && (
            <span
              className="inline-flex items-center rounded border border-red-100 bg-red-50 px-1 py-px text-[9px] font-medium text-red-600 dark:border-red-800 dark:bg-red-950 dark:text-red-400"
              title={`False: ${falseBranch}`}
            >
              F: {falseBranch.slice(0, 10)}
            </span>
          )}
        </div>
      )}
    </NodeShell>
  )
})
