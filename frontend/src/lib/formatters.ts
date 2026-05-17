import { capitalize } from './utils'

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
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
