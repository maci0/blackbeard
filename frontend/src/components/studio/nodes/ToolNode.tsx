import { memo } from 'react'
import { Position, type NodeProps } from '@xyflow/react'
import { Wrench } from 'lucide-react'
import { NodeShell } from './NodeShell'

export default memo(function ToolNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const toolType = data['type'] as string | undefined
  const description = data['description'] as string | undefined

  return (
    <NodeShell
      color="emerald"
      icon={Wrench}
      label="Tool"
      ariaLabel={`Tool: ${name || 'Unnamed Tool'}`}
      selected={!!selected}
      targetPosition={Position.Left}
      sourcePosition={Position.Right}
    >
      <p
        className="text-2xs truncate font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Tool'}
      >
        {name || 'Unnamed Tool'}
      </p>
      {description ? (
        <p
          className="line-clamp-1 text-[10px] leading-snug text-muted-foreground"
          title={description}
        >
          {description}
        </p>
      ) : null}

      {toolType && (
        <div className="pt-0.5">
          <span className="inline-flex items-center rounded border border-emerald-100 bg-emerald-50 px-1 py-px text-[10px] font-semibold text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
            {toolType}
          </span>
        </div>
      )}
    </NodeShell>
  )
})
