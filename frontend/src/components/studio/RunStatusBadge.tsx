import { useEffect, useRef, useState } from 'react'
import { Loader2, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react'
import type { RunStatus } from '@/lib/types'

const CONFIGS: Record<RunStatus, { icon: React.ReactNode; cls: string }> = {
  idle: { icon: null, cls: '' },
  loading: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
  },
  saving: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300 dark:border-amber-800',
  },
  running: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />,
    cls: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  },
  success: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
  },
  error: {
    icon: <AlertCircle className="h-3.5 w-3.5" />,
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
  const [visible, setVisible] = useState(false)
  const [animating, setAnimating] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const prevStatusRef = useRef<RunStatus>(status)

  useEffect(() => {
    if (status === 'idle') {
      setVisible(false)
      setAnimating(false)
      prevStatusRef.current = status
      return
    }

    let animTimer: ReturnType<typeof setTimeout> | undefined

    // Trigger slide-in animation when status changes
    if (status !== prevStatusRef.current) {
      setAnimating(true)
      setVisible(true)
      // Reset animation trigger after transition completes
      animTimer = setTimeout(() => setAnimating(false), 300)

      // Auto-dismiss success after 3 seconds
      if (timerRef.current) clearTimeout(timerRef.current)
      if (status === 'success') {
        timerRef.current = setTimeout(() => setVisible(false), 3000)
      }
    } else {
      setVisible(true)
    }

    prevStatusRef.current = status

    return () => {
      if (animTimer) clearTimeout(animTimer)
    }
  }, [status])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  if (status === 'idle' || !visible) return null

  const cfg = CONFIGS[status]
  const isNavigable = status === 'success' && !!executionId && !!onNavigate

  const inner = (
    <>
      {cfg.icon}
      <span className="font-semibold">{message || status}</span>
      {isNavigable && <ArrowRight className="h-3.5 w-3.5" />}
    </>
  )

  const baseClass = `flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-all duration-300 ${cfg.cls}`

  const slideClass = animating ? 'animate-in slide-in-from-right-4 fade-in duration-300' : ''

  if (isNavigable) {
    return (
      <button
        onClick={onNavigate}
        aria-label={`View execution: ${message || status}`}
        className={`${baseClass} ${slideClass} cursor-pointer hover:opacity-75`}
      >
        {inner}
      </button>
    )
  }

  return <div className={`${baseClass} ${slideClass}`}>{inner}</div>
}
