import { type ReactNode } from 'react'
import { Handle, Position } from '@xyflow/react'
import { cn } from '@/lib/utils'

type NodeColor = 'violet' | 'blue' | 'emerald' | 'amber' | 'rose' | 'cyan' | 'purple'

interface NodeShellProps {
  color: NodeColor
  icon: React.ComponentType<{ className?: string }>
  label: string
  ariaLabel: string
  selected: boolean
  width?: string
  targetPosition?: Position
  sourcePosition?: Position
  headerGradientTo?: string
  children: ReactNode
}

const COLOR_CLASSES: Record<
  NodeColor,
  { selected: string; unselected: string; handle: string; from: string; to: string }
> = {
  violet: {
    selected:
      'border-violet-400 shadow-md shadow-violet-100 ring-2 ring-violet-300 ring-offset-1 dark:shadow-violet-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-violet-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-violet-400',
    from: 'from-violet-600',
    to: 'to-violet-500',
  },
  blue: {
    selected:
      'border-blue-400 shadow-md shadow-blue-100 ring-2 ring-blue-300 ring-offset-1 dark:shadow-blue-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-blue-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-blue-400',
    from: 'from-blue-600',
    to: 'to-blue-500',
  },
  emerald: {
    selected:
      'border-emerald-400 shadow-md shadow-emerald-100 ring-2 ring-emerald-300 ring-offset-1 dark:shadow-emerald-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-emerald-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-emerald-400',
    from: 'from-emerald-600',
    to: 'to-emerald-500',
  },
  amber: {
    selected:
      'border-amber-400 shadow-md shadow-amber-100 ring-2 ring-amber-300 ring-offset-1 dark:shadow-amber-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-amber-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-amber-400',
    from: 'from-amber-600',
    to: 'to-amber-500',
  },
  rose: {
    selected:
      'border-rose-400 shadow-md shadow-rose-100 ring-2 ring-rose-300 ring-offset-1 dark:shadow-rose-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-rose-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-rose-400',
    from: 'from-rose-600',
    to: 'to-rose-500',
  },
  cyan: {
    selected:
      'border-cyan-400 shadow-md shadow-cyan-100 ring-2 ring-cyan-300 ring-offset-1 dark:shadow-cyan-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-cyan-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-cyan-400',
    from: 'from-cyan-600',
    to: 'to-cyan-500',
  },
  purple: {
    selected:
      'border-purple-400 shadow-md shadow-purple-100 ring-2 ring-purple-300 ring-offset-1 dark:shadow-purple-950 dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-purple-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-purple-400',
    from: 'from-purple-600',
    to: 'to-purple-500',
  },
}

export function NodeShell({
  color,
  icon: Icon,
  label,
  ariaLabel,
  selected,
  width = 'w-[200px]',
  targetPosition = Position.Top,
  sourcePosition = Position.Bottom,
  headerGradientTo,
  children,
}: NodeShellProps) {
  const theme = COLOR_CLASSES[color]
  return (
    <div
      aria-label={ariaLabel}
      className={cn(
        width,
        'overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-150',
        selected ? theme.selected : theme.unselected,
      )}
    >
      <Handle
        type="target"
        position={targetPosition}
        className={cn('!h-2 !w-2 !border-[1.5px] !bg-white', theme.handle)}
      />

      <div
        className={cn(
          'flex h-6 items-center gap-1 bg-gradient-to-r px-1.5',
          theme.from,
          headerGradientTo ?? theme.to,
        )}
      >
        <Icon className="h-3 w-3 shrink-0 text-white/90" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-white/90">
          {label}
        </span>
      </div>

      <div className="space-y-0.5 px-2 py-1.5">{children}</div>

      <Handle
        type="source"
        position={sourcePosition}
        className={cn('!h-2 !w-2 !border-[1.5px] !bg-white', theme.handle)}
      />
    </div>
  )
}
