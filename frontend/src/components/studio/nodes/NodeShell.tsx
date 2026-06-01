import { type CSSProperties, type ReactNode } from 'react'
import { Handle, Position } from '@xyflow/react'
import { cn } from '@/lib/utils'

type NodeColor = 'violet' | 'blue' | 'emerald' | 'amber' | 'rose' | 'cyan' | 'purple'

export type NodeShape =
  | 'rectangle'
  | 'chamfered'
  | 'diamond-top'
  | 'hexagonal'
  | 'pill'
  | 'shield'
  | 'loop'

interface NodeShellProps {
  color: NodeColor
  icon: React.ComponentType<{ className?: string }>
  label: string
  ariaLabel: string
  selected: boolean
  shape?: NodeShape
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
      'border-violet-400 ring-2 ring-violet-300 ring-offset-1 shadow-[0_0_15px_rgba(139,92,246,0.25)] dark:shadow-[0_0_15px_rgba(139,92,246,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-violet-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-violet-400',
    from: 'from-violet-600',
    to: 'to-violet-500',
  },
  blue: {
    selected:
      'border-blue-400 ring-2 ring-blue-300 ring-offset-1 shadow-[0_0_15px_rgba(59,130,246,0.25)] dark:shadow-[0_0_15px_rgba(59,130,246,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-blue-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-blue-400',
    from: 'from-blue-600',
    to: 'to-blue-500',
  },
  emerald: {
    selected:
      'border-emerald-400 ring-2 ring-emerald-300 ring-offset-1 shadow-[0_0_15px_rgba(16,185,129,0.25)] dark:shadow-[0_0_15px_rgba(16,185,129,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-emerald-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-emerald-400',
    from: 'from-emerald-600',
    to: 'to-emerald-500',
  },
  amber: {
    selected:
      'border-amber-400 ring-2 ring-amber-300 ring-offset-1 shadow-[0_0_15px_rgba(245,158,11,0.25)] dark:shadow-[0_0_15px_rgba(245,158,11,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-amber-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-amber-400',
    from: 'from-amber-600',
    to: 'to-amber-500',
  },
  rose: {
    selected:
      'border-rose-400 ring-2 ring-rose-300 ring-offset-1 shadow-[0_0_15px_rgba(244,63,94,0.25)] dark:shadow-[0_0_15px_rgba(244,63,94,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-rose-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-rose-400',
    from: 'from-rose-600',
    to: 'to-rose-500',
  },
  cyan: {
    selected:
      'border-cyan-400 ring-2 ring-cyan-300 ring-offset-1 shadow-[0_0_15px_rgba(6,182,212,0.25)] dark:shadow-[0_0_15px_rgba(6,182,212,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-cyan-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-cyan-400',
    from: 'from-cyan-600',
    to: 'to-cyan-500',
  },
  purple: {
    selected:
      'border-purple-400 ring-2 ring-purple-300 ring-offset-1 shadow-[0_0_15px_rgba(168,85,247,0.25)] dark:shadow-[0_0_15px_rgba(168,85,247,0.15)] dark:ring-offset-slate-900',
    unselected: 'border-slate-200 hover:border-purple-200 hover:shadow-md dark:border-slate-700',
    handle: '!border-purple-400',
    from: 'from-purple-600',
    to: 'to-purple-500',
  },
}

const SHAPE_CLASSES: Record<NodeShape, string> = {
  rectangle: 'rounded-lg',
  chamfered: 'rounded-[0px_14px_14px_0px]',
  'diamond-top': '',
  hexagonal: '',
  pill: 'rounded-3xl',
  shield: '',
  loop: 'rounded-2xl',
}

const SHAPE_CLIP_PATHS: Partial<Record<NodeShape, string>> = {
  'diamond-top': 'polygon(12px 0%, calc(100% - 12px) 0%, 100% 12px, 100% 100%, 0% 100%, 0% 12px)',
  hexagonal: 'polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)',
  shield: 'polygon(0% 0%, 100% 0%, 100% 75%, 50% 100%, 0% 75%)',
}

const SHAPE_BODY_CLASSES: Partial<Record<NodeShape, string>> = {
  hexagonal: 'px-4',
  shield: 'pb-6',
}

export function NodeShell({
  color,
  icon: Icon,
  label,
  ariaLabel,
  selected,
  shape = 'rectangle',
  width = 'w-[200px]',
  targetPosition = Position.Top,
  sourcePosition = Position.Bottom,
  headerGradientTo,
  children,
}: NodeShellProps) {
  const theme = COLOR_CLASSES[color]
  const shapeClass = SHAPE_CLASSES[shape]
  const clipPath = SHAPE_CLIP_PATHS[shape]
  const bodyExtra = SHAPE_BODY_CLASSES[shape]

  const innerStyle: CSSProperties | undefined = clipPath ? { clipPath } : undefined

  return (
    <div aria-label={ariaLabel} className={cn(width, 'relative')}>
      <Handle
        type="target"
        position={targetPosition}
        className={cn('!h-2 !w-2 !border-[1.5px] !bg-white', theme.handle)}
      />

      <div
        className={cn(
          'overflow-hidden border bg-card shadow-sm transition-all duration-150',
          shapeClass,
          shape === 'rectangle' && 'node-accent-left',
          selected ? theme.selected : theme.unselected,
        )}
        style={innerStyle}
      >
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

        <div className={cn('space-y-0.5 px-2 py-1.5', bodyExtra)}>{children}</div>
      </div>

      <Handle
        type="source"
        position={sourcePosition}
        className={cn('!h-2 !w-2 !border-[1.5px] !bg-white', theme.handle)}
      />
    </div>
  )
}
