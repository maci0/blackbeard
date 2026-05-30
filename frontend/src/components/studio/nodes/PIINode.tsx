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

const PRESET_LABELS: Record<string, { text: string; color: string }> = {
  hipaa: {
    text: 'HIPAA',
    color:
      'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
  },
  gdpr: {
    text: 'GDPR',
    color:
      'bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950 dark:text-violet-300 dark:border-violet-800',
  },
  'pci-dss': {
    text: 'PCI-DSS',
    color:
      'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800',
  },
  ccpa: {
    text: 'CCPA',
    color:
      'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800',
  },
  custom: {
    text: 'Custom',
    color:
      'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:border-slate-700',
  },
}

export default memo(function PIINode({ data, selected }: NodeProps) {
  const entities = (data['entities'] as string[] | undefined) ?? []
  const action = (data['action'] as string | undefined) ?? 'redact'
  const preset = (data['preset'] as string | undefined) ?? 'custom'
  const actionMeta = ACTION_LABELS[action] ?? ACTION_LABELS['redact']!
  const presetMeta = PRESET_LABELS[preset] ?? PRESET_LABELS['custom']!

  return (
    <NodeShell
      color="rose"
      icon={ShieldCheck}
      label="PII Redaction"
      ariaLabel={`PII Redaction: ${preset} preset, ${action}, ${entities.length} entit${entities.length === 1 ? 'y' : 'ies'}`}
      selected={!!selected}
      width="w-[160px]"
      headerGradientTo="to-red-500"
    >
      <div className="flex items-center gap-1 pt-0.5">
        <span
          className={cn(
            'inline-flex items-center rounded border px-1 py-px text-[10px] font-semibold',
            presetMeta.color,
          )}
        >
          {presetMeta.text}
        </span>
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
          {entities.slice(0, 4).map((entity) => (
            <span
              key={entity}
              className="inline-flex items-center rounded border border-rose-100 bg-rose-50 px-1 py-px text-[9px] font-medium text-rose-600 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-400"
              title={entity}
            >
              {entity.replace(/_/g, ' ').slice(0, 10)}
            </span>
          ))}
          {entities.length > 4 && (
            <span
              className="inline-flex items-center rounded border border-slate-100 bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
              title={entities.slice(4).join(', ')}
            >
              +{entities.length - 4}
            </span>
          )}
        </div>
      ) : preset !== 'custom' ? (
        <p className="text-[10px] text-muted-foreground/80">{preset.toUpperCase()} defaults</p>
      ) : (
        <p className="text-[10px] italic text-muted-foreground/60">No entities</p>
      )}
    </NodeShell>
  )
})
