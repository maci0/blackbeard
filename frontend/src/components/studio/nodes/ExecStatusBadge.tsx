import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ExecStatusBadgeProps {
  status: string
  output?: string
}

export function ExecStatusBadge({ status, output }: ExecStatusBadgeProps) {
  const isCompleted = status === 'completed'
  const isFailed = status === 'failed'

  const truncated = output && output.length > 100 ? `${output.slice(0, 100)}...` : output

  return (
    <div
      className={cn(
        'mt-1 rounded border px-1 py-0.5',
        isCompleted &&
          'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950',
        isFailed && 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950',
        !isCompleted &&
          !isFailed &&
          'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950',
      )}
    >
      <div className="flex items-center gap-1">
        {isCompleted ? (
          <CheckCircle2 className="h-2.5 w-2.5 shrink-0 text-emerald-500" />
        ) : isFailed ? (
          <XCircle className="h-2.5 w-2.5 shrink-0 text-red-500" />
        ) : (
          <Loader2 className="h-2.5 w-2.5 shrink-0 animate-spin text-amber-500" />
        )}
        <span
          className={cn(
            'text-[9px] font-semibold uppercase',
            isCompleted && 'text-emerald-700 dark:text-emerald-300',
            isFailed && 'text-red-700 dark:text-red-300',
            !isCompleted && !isFailed && 'text-amber-700 dark:text-amber-300',
          )}
        >
          {status}
        </span>
      </div>
      {truncated && (
        <p
          className={cn(
            'mt-0.5 line-clamp-2 text-[9px] leading-tight',
            isCompleted && 'text-emerald-600 dark:text-emerald-400',
            isFailed && 'text-red-600 dark:text-red-400',
          )}
          title={output}
        >
          {truncated}
        </p>
      )}
    </div>
  )
}
