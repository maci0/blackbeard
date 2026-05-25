import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { ListChecks, CheckCircle2, XCircle } from 'lucide-react'
import { parseRef } from '@/lib/utils'
import { NodeShell } from './NodeShell'
import { ExecStatusBadge } from './ExecStatusBadge'

export default memo(function TaskNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const description = data['description'] as string | undefined
  const agent = data['agent'] as string | undefined
  const execStatus = data['_execStatus'] as string | undefined
  const execOutput = data['_execOutput'] as string | undefined

  return (
    <NodeShell
      color="blue"
      icon={
        execStatus === 'completed' ? CheckCircle2 : execStatus === 'failed' ? XCircle : ListChecks
      }
      label="Task"
      ariaLabel={`Task: ${name || 'Unnamed Task'}`}
      selected={!!selected}
    >
      <p
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Task'}
      >
        {name || 'Unnamed Task'}
      </p>
      {description ? (
        <p className="truncate text-[10px] leading-snug text-muted-foreground" title={description}>
          {description}
        </p>
      ) : (
        <p className="text-[10px] italic text-muted-foreground/60">No description</p>
      )}

      <div className="flex flex-wrap gap-0.5 pt-0.5">
        {agent && (
          <span
            className="inline-flex max-w-full items-center truncate rounded border border-blue-100 bg-blue-50 px-1 py-px text-[10px] font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300"
            title={`Agent: ${parseRef(agent)}`}
          >
            → {parseRef(agent)}
          </span>
        )}
      </div>

      {execStatus && <ExecStatusBadge status={execStatus} output={execOutput} />}
    </NodeShell>
  )
})
