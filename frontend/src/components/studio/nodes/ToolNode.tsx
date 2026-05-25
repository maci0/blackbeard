import { memo } from 'react'
import { Position, type NodeProps } from '@xyflow/react'
import { Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NodeShell } from './NodeShell'

const TYPE_STYLES: Record<string, string> = {
  python:
    'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300',
  builtin:
    'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300',
  mcp: 'border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300',
}

const DEFAULT_TYPE_STYLE =
  'border-emerald-100 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'

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
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Tool'}
      >
        {name || 'Unnamed Tool'}
      </p>
      {description ? (
        <p className="truncate text-xs leading-snug text-muted-foreground" title={description}>
          {description}
        </p>
      ) : null}

      {toolType && (
        <div className="pt-0.5">
          <span
            className={cn(
              'inline-flex items-center rounded border px-1 py-px text-[10px] font-semibold',
              TYPE_STYLES[toolType] ?? DEFAULT_TYPE_STYLE,
            )}
          >
            {toolType}
          </span>
        </div>
      )}
    </NodeShell>
  )
})
