import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Workflow } from 'lucide-react'
import { cn, parseRef } from '@/lib/utils'

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
    <div
      aria-label={`Flow step: ${name || 'Unnamed Step'}`}
      className={cn(
        'w-[140px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-amber-400 shadow-md shadow-amber-100 ring-2 ring-amber-300 ring-offset-1 dark:shadow-amber-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-amber-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !border-2 !border-amber-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-1.5 bg-gradient-to-r from-amber-600 to-amber-500 px-2 py-1">
        <Workflow className="h-3 w-3 text-white/90" />
        <span className="text-2xs font-bold uppercase tracking-wider text-white/90">Step</span>
      </div>

      {/* Body */}
      <div className="space-y-0.5 px-2 py-1.5">
        <p
          className="text-2xs truncate font-semibold leading-tight text-foreground"
          title={name || 'Unnamed Step'}
        >
          {name || 'Unnamed Step'}
        </p>

        {/* Type badge */}
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

        {/* Crew ref for crew type */}
        {stepType === 'crew' && crew && (
          <p
            className="truncate text-[10px] leading-snug text-muted-foreground"
            title={`Crew: ${parseRef(crew)}`}
          >
            crew: {parseRef(crew)}
          </p>
        )}

        {/* Function path for function type */}
        {stepType === 'function' && functionPath && (
          <p
            className="truncate text-[10px] leading-snug text-muted-foreground"
            title={`fn: ${functionPath}`}
          >
            fn: {functionPath}
          </p>
        )}

        {/* Listen-to indicators */}
        {listenTo && listenTo.length > 0 && (
          <p
            className="truncate text-[10px] leading-snug text-muted-foreground/70"
            title={`Listens to: ${listenTo.join(', ')}`}
          >
            listens: {listenTo.length}
          </p>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !border-2 !border-amber-400 !bg-white"
      />
    </div>
  )
})
