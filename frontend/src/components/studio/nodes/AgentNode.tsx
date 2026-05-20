import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { User } from 'lucide-react'
import { parseRef } from '@/lib/utils'
import { NodeShell } from './NodeShell'

export default memo(function AgentNode({ data, selected }: NodeProps) {
  const role = data['role'] as string | undefined
  const goal = data['goal'] as string | undefined
  const llm = data['llm'] as string | undefined
  const llmDisplay = llm ? parseRef(llm) : undefined

  return (
    <NodeShell
      color="violet"
      icon={User}
      label="Agent"
      ariaLabel={`Agent: ${role || 'Unnamed Agent'}`}
      selected={!!selected}
    >
      <p
        className="text-2xs truncate font-semibold leading-tight text-foreground"
        title={role || 'Unnamed Agent'}
      >
        {role || 'Unnamed Agent'}
      </p>
      {goal ? (
        <p className="line-clamp-2 text-[10px] leading-snug text-muted-foreground" title={goal}>
          {goal}
        </p>
      ) : (
        <p className="text-2xs italic text-muted-foreground/60">No goal set</p>
      )}

      {llmDisplay && (
        <div className="pt-0.5">
          <span
            className="inline-flex max-w-full items-center truncate rounded border border-violet-100 bg-violet-50 px-1 py-px text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300"
            title={llmDisplay}
          >
            {llmDisplay}
          </span>
        </div>
      )}
    </NodeShell>
  )
})
