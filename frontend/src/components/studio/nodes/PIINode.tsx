import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'

const ACTION_LABELS: Record<string, { text: string; color: string }> = {
  redact: {
    text: 'redact',
    color:
      'bg-rose-50 text-rose-700 border-rose-100 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800',
  },
  reject: {
    text: 'reject',
    color:
      'bg-red-50 text-red-700 border-red-100 dark:bg-red-950 dark:text-red-300 dark:border-red-800',
  },
  warn: {
    text: 'warn',
    color:
      'bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800',
  },
}

export default memo(function PIINode({ data, selected }: NodeProps) {
  const entities = (data['entities'] as string[] | undefined) ?? []
  const action = (data['action'] as string | undefined) ?? 'redact'
  const actionMeta = ACTION_LABELS[action] ?? ACTION_LABELS['redact']!

  return (
    <div
      aria-label={`PII Redaction: ${action}, ${entities.length} entit${entities.length === 1 ? 'y' : 'ies'}`}
      className={cn(
        'w-[140px] overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-150',
        selected
          ? 'border-rose-400 shadow-md shadow-rose-100 ring-2 ring-rose-300 ring-offset-1 dark:shadow-rose-950 dark:ring-offset-slate-900'
          : 'border-slate-200 hover:border-rose-200 hover:shadow-md dark:border-slate-700',
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !border-2 !border-rose-400 !bg-white"
      />

      {/* Header strip */}
      <div className="flex items-center gap-1.5 bg-gradient-to-r from-rose-600 to-red-500 px-2 py-1">
        <ShieldCheck className="h-3 w-3 text-white/90" />
        <span className="text-2xs font-bold uppercase tracking-wider text-white/90">
          PII Redaction
        </span>
      </div>

      {/* Body */}
      <div className="space-y-0.5 px-2 py-1.5">
        {/* Action badge */}
        <div className="pt-0.5">
          <span
            className={cn(
              'inline-flex items-center rounded border px-1 py-px text-[10px] font-semibold',
              actionMeta.color,
            )}
          >
            {actionMeta.text}
          </span>
        </div>

        {/* Entity badges */}
        {entities.length > 0 ? (
          <div className="flex flex-wrap gap-0.5 pt-0.5">
            {entities.slice(0, 3).map((entity) => (
              <span
                key={entity}
                className="inline-flex items-center rounded border border-rose-100 bg-rose-50 px-1 py-px text-[9px] font-medium text-rose-600 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-400"
                title={entity}
              >
                {entity.replace(/_/g, ' ').slice(0, 8)}
              </span>
            ))}
            {entities.length > 3 && (
              <span
                className="inline-flex items-center rounded border border-slate-100 bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
                title={entities.slice(3).join(', ')}
              >
                +{entities.length - 3}
              </span>
            )}
          </div>
        ) : (
          <p className="text-2xs italic text-muted-foreground/60">No entities</p>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !border-2 !border-rose-400 !bg-white"
      />
    </div>
  )
})
