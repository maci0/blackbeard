import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { User, CheckCircle2, XCircle } from 'lucide-react'
import { parseRef } from '@/lib/utils'
import { NodeShell } from './NodeShell'
import { ExecStatusBadge } from './ExecStatusBadge'

export default memo(function AgentNode({ data, selected }: NodeProps) {
  const role = data['role'] as string | undefined
  const goal = data['goal'] as string | undefined
  const llm = data['llm'] as string | undefined
  const tools = data['tools'] as string[] | undefined
  const llmDisplay = llm ? parseRef(llm) : undefined
  const execStatus = data['_execStatus'] as string | undefined
  const toolCount = tools?.length ?? 0

  return (
    <NodeShell
      color="violet"
      icon={execStatus === 'completed' ? CheckCircle2 : execStatus === 'failed' ? XCircle : User}
      label="Agent"
      ariaLabel={`Agent: ${role || 'Unnamed Agent'}`}
      selected={!!selected}
      shape="rectangle"
      width="w-[220px]"
    >
      <p
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={role || 'Unnamed Agent'}
      >
        {role || 'Unnamed Agent'}
      </p>
      {goal ? (
        <p className="line-clamp-2 text-xs leading-snug text-muted-foreground" title={goal}>
          {goal}
        </p>
      ) : (
        <p className="text-xs italic text-muted-foreground/60">No goal set</p>
      )}

      <div className="flex flex-wrap gap-1 pt-0.5">
        {llmDisplay && (
          <span
            className="inline-flex max-w-full items-center truncate rounded border border-violet-100 bg-violet-50 px-1 py-px text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300"
            title={llmDisplay}
          >
            {llmDisplay}
          </span>
        )}
        {toolCount > 0 && (
          <span className="inline-flex items-center rounded border border-violet-100 bg-violet-50 px-1 py-px text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300">
            {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
          </span>
        )}
      </div>

      {execStatus && <ExecStatusBadge status={execStatus} />}
    </NodeShell>
  )
})
