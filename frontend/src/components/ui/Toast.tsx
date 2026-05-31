import { useEffect, useRef } from 'react'
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToastStore, type Toast } from '@/stores/toastStore'

const ICON_MAP = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
} as const

const STYLE_MAP = {
  success:
    'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200',
  error:
    'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200',
  info: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200',
} as const

function ToastItem({ toast }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss)
  const pause = useToastStore((s) => s.pause)
  const resume = useToastStore((s) => s.resume)
  const Icon = ICON_MAP[toast.type]
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (el) {
      requestAnimationFrame(() => {
        el.classList.remove('translate-y-2', 'sm:translate-y-0', 'sm:translate-x-full', 'opacity-0')
        el.classList.add('translate-y-0', 'sm:translate-x-0', 'opacity-100')
      })
    }
  }, [])

  useEffect(() => {
    const el = ref.current
    if (toast.dismissing && el) {
      el.classList.remove('translate-y-0', 'sm:translate-x-0', 'opacity-100')
      el.classList.add('translate-y-2', 'sm:translate-y-0', 'sm:translate-x-full', 'opacity-0')
    }
  }, [toast.dismissing])

  return (
    <div
      ref={ref}
      role={toast.type === 'error' ? 'alert' : 'status'}
      onMouseEnter={() => pause(toast.id)}
      onMouseLeave={() => resume(toast.id)}
      onFocus={() => pause(toast.id)}
      onBlur={() => resume(toast.id)}
      tabIndex={0}
      className={cn(
        'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg transition-all duration-300 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none',
        'translate-y-2 opacity-0 sm:translate-x-full sm:translate-y-0',
        STYLE_MAP[toast.type],
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p className="flex-1 text-sm font-medium">{toast.message}</p>
      <button
        type="button"
        onClick={() => dismiss(toast.id)}
        className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-md transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:hover:bg-white/10"
        aria-label="Dismiss notification"
        title="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)

  return (
    <div
      role="region"
      aria-label="Notifications"
      className="pointer-events-none fixed bottom-4 left-4 right-4 z-[100] flex flex-col-reverse items-end gap-2 sm:left-auto"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  )
}
