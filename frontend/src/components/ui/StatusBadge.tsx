import { CheckCircle2, XCircle, Clock, Ban } from 'lucide-react'
import { statusLabel } from '@/lib/formatters'

const STATUS_CLASSES: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
  cancelled: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  pending: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
}

const STATUS_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
  pending: Clock,
  queued: Clock,
}

export function StatusBadge({ status }: { status: string; live?: boolean }) {
  const classes =
    STATUS_CLASSES[status] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  const label = statusLabel(status)
  const Icon = STATUS_ICON[status]
  return (
    <span
      role="status"
      aria-label={`Status: ${label}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold ${classes}`}
    >
      {status === 'running' ? (
        <span className="relative flex h-2 w-2" aria-hidden="true">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75 motion-reduce:animate-none" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
        </span>
      ) : Icon ? (
        <Icon className="h-3 w-3" aria-hidden="true" />
      ) : null}
      {label}
    </span>
  )
}
