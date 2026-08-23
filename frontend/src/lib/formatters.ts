import { capitalize } from './utils'

/** Browser locale for all user-facing formatting. */
const LOCALE: string | undefined = undefined

const _rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto', style: 'narrow' })

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const then = new Date(dateStr).getTime()
  if (isNaN(then)) return '—'
  // Negative delta = past (what RelativeTimeFormat expects for "ago").
  const diffSec = Math.round((then - Date.now()) / 1000)
  const abs = Math.abs(diffSec)
  if (abs < 60) return _rtf.format(0, 'second')
  const absMin = Math.round(abs / 60)
  if (absMin < 60) return _rtf.format(Math.sign(diffSec) * absMin, 'minute')
  const absHr = Math.round(abs / 3600)
  if (absHr < 24) return _rtf.format(Math.sign(diffSec) * absHr, 'hour')
  const absDay = Math.round(abs / 86400)
  if (absDay < 7) return _rtf.format(Math.sign(diffSec) * absDay, 'day')
  return formatDate(dateStr)
}

const _dateFmt = new Intl.DateTimeFormat(LOCALE, {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const _dateFmtYear = new Intl.DateTimeFormat(LOCALE, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  const fmt = d.getFullYear() !== new Date().getFullYear() ? _dateFmtYear : _dateFmt
  return fmt.format(d)
}

/** Calendar date of *date* in the browser's timezone as YYYY-MM-DD.
 *
 * Use instead of `toISOString().slice(0, 10)` whenever a timestamp is grouped
 * or labeled by day ("Today", weekday names): the ISO slice yields the UTC
 * date, which shifts spend/counts onto the wrong bar and can drop late-day
 * events entirely for users away from UTC.
 */
export function localDateKey(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function getDuration(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  if (isNaN(s)) return '—'
  const e = end ? new Date(end).getTime() : Date.now()
  if (isNaN(e)) return '—'
  const sec = Math.round((e - s) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  if (min < 60) return `${min}m ${rem}s`
  const hrs = Math.floor(min / 60)
  const remMin = min % 60
  return `${hrs}h ${remMin}m`
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  const sec = ms / 1000
  if (sec < 60)
    return `${formatNumber(sec, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return `${min}m ${Math.round(rem)}s`
}

export function parseCost(cost: number | string | null | undefined): number {
  const n = typeof cost === 'string' ? parseFloat(cost) : cost
  return n != null && !isNaN(n) ? n : 0
}

function usdFormatter(minFrac: number, maxFrac: number): Intl.NumberFormat {
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: minFrac,
    maximumFractionDigits: maxFrac,
  })
}

/** Locale-aware USD. Returns em dash for zero/missing (no spend). */
export function formatCost(cost: number | string | null | undefined): string {
  const n = parseCost(cost)
  if (n === 0) return '—'
  const abs = Math.abs(n)
  if (abs >= 1) return usdFormatter(2, 2).format(n)
  if (abs >= 0.01) return usdFormatter(3, 3).format(n)
  return usdFormatter(4, 4).format(n)
}

/** Locale-aware USD zero for stats that should show $0 rather than an em dash. */
export function formatCostZero(): string {
  return usdFormatter(2, 2).format(0)
}

/** Locale-aware integer/decimal formatting (grouping, separators). */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(LOCALE, options).format(value)
}

/**
 * Format a percentage value already expressed in percent points (e.g. 12.5 → "12.5%").
 * Uses locale decimal separators; keeps a trailing % for UI density.
 */
export function formatPercent(value: number, fractionDigits = 1): string {
  return `${new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)}%`
}

/** Compact notation (1.2K, 3M) using the browser locale. */
export function formatCompact(value: number): string {
  return new Intl.NumberFormat(LOCALE, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

/**
 * Pick a plural form via Intl.PluralRules. Provide at least `other`;
 * languages with more categories (Arabic, Polish, Russian) can add `zero`/`few`/`many`.
 */
export function plural(
  count: number,
  forms: Partial<Record<Intl.LDMLPluralRule, string>> & { other: string },
): string {
  const category = new Intl.PluralRules(LOCALE).select(count)
  return forms[category] ?? forms.other
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
