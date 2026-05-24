import { capitalize } from './utils'

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const seconds = Math.round((now - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(dateStr)
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const now = new Date()
  const options: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }
  if (d.getFullYear() !== now.getFullYear()) {
    options.year = 'numeric'
  }
  return d.toLocaleString(undefined, options)
}

export function getDuration(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((e - s) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  if (min < 60) return `${min}m ${rem}s`
  const hrs = Math.floor(min / 60)
  const remMin = min % 60
  return `${hrs}h ${remMin}m`
}

export function formatCost(cost: number | string | null | undefined): string {
  const n = typeof cost === 'string' ? parseFloat(cost) : cost
  if (n == null || n === 0 || isNaN(n)) return '—'
  if (n >= 1) return `$${n.toFixed(2)}`
  if (n >= 0.01) return `$${n.toFixed(3)}`
  return `$${n.toFixed(4)}`
}

const STATUS_DISPLAY: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  pending: 'Pending',
}

export const statusLabel = (status: string): string => STATUS_DISPLAY[status] ?? capitalize(status)
