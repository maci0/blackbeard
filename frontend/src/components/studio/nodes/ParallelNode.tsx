import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { Columns3 } from 'lucide-react'
import { parseRef } from '@/lib/refs'
import { NodeShell } from './NodeShell'

export default memo(function ParallelNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const branches = (data['branches'] as string[] | undefined) ?? []

  return (
    <NodeShell
      color="purple"
      icon={Columns3}
      label="Parallel"
      ariaLabel={`Parallel: ${name || 'Unnamed Parallel'}`}
      selected={!!selected}
      shape="pill"
      width="w-[180px]"
    >
      <p
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Parallel'}
      >
        {name || 'Unnamed Parallel'}
      </p>

      <div className="pt-0.5">
        <span className="inline-flex items-center rounded border border-purple-100 bg-purple-50 px-1 py-px text-[10px] font-semibold text-purple-700 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300">
          {branches.length} branch{branches.length !== 1 ? 'es' : ''}
        </span>
      </div>

      {branches.length > 0 ? (
        <div className="flex flex-wrap gap-0.5 pt-0.5">
          {branches.slice(0, 4).map((branch) => (
            <span
              key={branch}
              className="inline-flex items-center rounded border border-purple-100 bg-purple-50 px-1 py-px text-[9px] font-medium text-purple-600 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-400"
              title={parseRef(branch)}
            >
              {parseRef(branch).slice(0, 8)}
            </span>
          ))}
          {branches.length > 4 && (
            <span
              className="inline-flex items-center rounded border border-slate-100 bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
              title={branches.slice(4).map(parseRef).join(', ')}
            >
              +{branches.length - 4}
            </span>
          )}
        </div>
      ) : (
        <p className="text-[10px] italic text-muted-foreground/60">No branches defined</p>
      )}
    </NodeShell>
  )
})
