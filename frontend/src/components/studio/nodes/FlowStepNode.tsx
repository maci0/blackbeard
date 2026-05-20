import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { Workflow } from 'lucide-react'
import { cn, parseRef } from '@/lib/utils'
import { NodeShell } from './NodeShell'

const TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  crew: {
    bg: 'bg-amber-50 dark:bg-amber-950',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-100 dark:border-amber-800',
  },
  function: {
    bg: 'bg-cyan-50 dark:bg-cyan-950',
    text: 'text-cyan-700 dark:text-cyan-300',
    border: 'border-cyan-100 dark:border-cyan-800',
  },
  router: {
    bg: 'bg-rose-50 dark:bg-rose-950',
    text: 'text-rose-700 dark:text-rose-300',
    border: 'border-rose-100 dark:border-rose-800',
  },
  condition: {
    bg: 'bg-purple-50 dark:bg-purple-950',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-100 dark:border-purple-800',
  },
}

export default memo(function FlowStepNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const stepType = (data['type'] as string | undefined) ?? 'crew'
  const crew = data['crew'] as string | undefined
  const functionPath = data['function_path'] as string | undefined
  const listenTo = data['listen_to'] as string[] | undefined

  const typeColor = TYPE_COLORS[stepType] ?? TYPE_COLORS['crew']!

  return (
    <NodeShell
      color="amber"
      icon={Workflow}
      label="Step"
      ariaLabel={`Flow step: ${name || 'Unnamed Step'}`}
      selected={!!selected}
      width="w-[140px]"
    >
      <p
        className="text-2xs truncate font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Step'}
      >
        {name || 'Unnamed Step'}
      </p>

      <div className="pt-0.5">
        <span
          className={cn(
            'inline-flex items-center rounded border px-1 py-px text-[10px] font-semibold',
            typeColor.bg,
            typeColor.text,
            typeColor.border,
          )}
        >
          {stepType}
        </span>
      </div>

      {stepType === 'crew' && crew && (
        <p
          className="truncate text-[10px] leading-snug text-muted-foreground"
          title={`Crew: ${parseRef(crew)}`}
        >
          crew: {parseRef(crew)}
        </p>
      )}

      {stepType === 'function' && functionPath && (
        <p
          className="truncate text-[10px] leading-snug text-muted-foreground"
          title={`fn: ${functionPath}`}
        >
          fn: {functionPath}
        </p>
      )}

      {listenTo && listenTo.length > 0 && (
        <p
          className="truncate text-[10px] leading-snug text-muted-foreground/70"
          title={`Listens to: ${listenTo.join(', ')}`}
        >
          listens: {listenTo.length}
        </p>
      )}
    </NodeShell>
  )
})
