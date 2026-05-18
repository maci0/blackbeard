import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ErrorAlert({
  message,
  actionLabel = 'Retry',
  onAction,
  ariaLabel,
  className,
}: {
  message: string
  actionLabel?: string
  onAction?: () => void
  ariaLabel?: string
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive',
        className,
      )}
    >
      <span className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
        {message}
      </span>
      {onAction && (
        <button
          onClick={onAction}
          className="flex h-[44px] shrink-0 items-center rounded px-3 text-xs font-medium underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={ariaLabel ?? actionLabel}
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}
