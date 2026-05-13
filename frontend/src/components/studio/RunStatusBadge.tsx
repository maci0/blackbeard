import { Loader2, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type RunStatus = 'idle' | 'loading' | 'saving' | 'running' | 'success' | 'error'

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

const CONFIGS: Record<RunStatus, { icon: React.ReactNode; cls: string }> = {
  idle: { icon: null, cls: '' },
  loading: {
    icon: <Loader2 className="w-3 h-3 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
  },
  saving: {
    icon: <Loader2 className="w-3 h-3 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300 dark:border-amber-800',
  },
  running: {
    icon: <Loader2 className="w-3 h-3 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  },
  success: {
    icon: <CheckCircle2 className="w-3 h-3" />,
    cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
  },
  error: {
    icon: <AlertCircle className="w-3 h-3" />,
    cls: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900 dark:text-red-300 dark:border-red-800',
  },
}

export function RunStatusBadge({
  status,
  message,
  executionId,
  onNavigate,
}: {
  status: RunStatus
  message: string
  executionId?: string | null
  onNavigate?: () => void
}) {
  if (status === 'idle') return null

  const cfg = CONFIGS[status]
  const isNavigable = status === 'success' && !!executionId && !!onNavigate

  const inner = (
    <>
      {cfg.icon}
      <span>{message || status}</span>
      {isNavigable && <ArrowRight className="w-3 h-3" />}
    </>
  )

  if (isNavigable) {
    return (
      <button
        onClick={onNavigate}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-medium cursor-pointer hover:opacity-75 transition-opacity ${cfg.cls}`}
      >
        {inner}
      </button>
    )
  }

  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-medium ${cfg.cls}`}
    >
      {inner}
    </div>
  )
}
