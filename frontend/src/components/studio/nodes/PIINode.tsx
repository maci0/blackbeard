import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NodeShell } from './NodeShell'

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
    <NodeShell
      color="rose"
      icon={ShieldCheck}
      label="PII Redaction"
      ariaLabel={`PII Redaction: ${action}, ${entities.length} entit${entities.length === 1 ? 'y' : 'ies'}`}
      selected={!!selected}
      width="w-[140px]"
      headerGradientTo="to-red-500"
    >
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
    </NodeShell>
  )
})
