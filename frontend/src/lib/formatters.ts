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
  return `${min}m ${rem}s`
}

export function formatCost(cost: number | null | undefined): string {
  if (cost == null || cost === 0) return '—'
  return `$${cost.toFixed(4)}`
}

export function formatTokens(tokens: number | null | undefined): string {
  if (tokens == null || tokens === 0) return '—'
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(tokens)
}
