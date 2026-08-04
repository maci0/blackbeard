import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  formatDate,
  getDuration,
  formatCost,
  formatCostZero,
  formatNumber,
  formatPercent,
  formatCompact,
  plural,
  statusLabel,
  timeAgo,
} from '../formatters'

function expectedUsd(n: number, minFrac: number, maxFrac: number): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: minFrac,
    maximumFractionDigits: maxFrac,
  }).format(n)
}

describe('formatDate', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns dash for null input', () => {
    expect(formatDate(null)).toBe('—')
  })

  it('returns dash for undefined input', () => {
    expect(formatDate(undefined)).toBe('—')
  })

  it('returns dash for empty string', () => {
    expect(formatDate('')).toBe('—')
  })

  it('formats a valid date string', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-03-01T12:00:00Z'))

    const result = formatDate('2024-06-15T10:30:00Z')
    expect(result).toContain('2024')
    // formatDate renders in the local timezone; derive the expected day the
    // same way so the test passes regardless of the machine's TZ.
    expect(result).toContain(String(new Date('2024-06-15T10:30:00Z').getDate()))
    expect(result).toMatch(/\d{1,2}:\d{2}/)
    expect(result).not.toBe('—')

    vi.useRealTimers()
  })

  it('includes year for dates in a different year', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-01T12:00:00Z'))

    const result = formatDate('2024-06-15T10:30:00Z')
    expect(result).toMatch(/2024/)

    vi.useRealTimers()
  })

  it('omits year for dates in the current year', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-01T12:00:00Z'))

    const result = formatDate('2026-01-10T08:00:00Z')
    expect(result).not.toMatch(/2026/)
    expect(result).toContain(String(new Date('2026-01-10T08:00:00Z').getDate()))
    expect(result).toMatch(/:/)

    vi.useRealTimers()
  })
})

describe('getDuration', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns dash for null start', () => {
    expect(getDuration(null, null)).toBe('—')
  })

  it('returns dash for undefined start', () => {
    expect(getDuration(undefined, undefined)).toBe('—')
  })

  it('formats seconds-only durations', () => {
    const start = '2024-01-01T00:00:00Z'
    const end = '2024-01-01T00:00:30Z'
    expect(getDuration(start, end)).toBe('30s')
  })

  it('formats minutes and seconds', () => {
    const start = '2024-01-01T00:00:00Z'
    const end = '2024-01-01T00:02:15Z'
    expect(getDuration(start, end)).toBe('2m 15s')
  })

  it('formats hours and minutes', () => {
    const start = '2024-01-01T00:00:00Z'
    const end = '2024-01-01T01:30:00Z'
    expect(getDuration(start, end)).toBe('1h 30m')
  })

  it('uses current time when end is null', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-01-01T00:01:00Z'))

    const start = '2024-01-01T00:00:00Z'
    expect(getDuration(start, null)).toBe('1m 0s')
  })

  it('handles zero-second duration', () => {
    const start = '2024-01-01T00:00:00Z'
    const end = '2024-01-01T00:00:00Z'
    expect(getDuration(start, end)).toBe('0s')
  })
})

describe('formatCost', () => {
  it('returns dash for null', () => {
    expect(formatCost(null)).toBe('—')
  })

  it('returns dash for undefined', () => {
    expect(formatCost(undefined)).toBe('—')
  })

  it('returns dash for zero', () => {
    expect(formatCost(0)).toBe('—')
  })

  it('returns dash for NaN string', () => {
    expect(formatCost('not-a-number')).toBe('—')
  })

  it('formats costs >= $1 with 2 decimal places', () => {
    expect(formatCost(5.123)).toBe(expectedUsd(5.12, 2, 2))
    expect(formatCost(100.5)).toBe(expectedUsd(100.5, 2, 2))
  })

  it('formats costs >= $0.01 with 3 decimal places', () => {
    expect(formatCost(0.055)).toBe(expectedUsd(0.055, 3, 3))
    expect(formatCost(0.1)).toBe(expectedUsd(0.1, 3, 3))
  })

  it('formats costs < $0.01 with 4 decimal places', () => {
    expect(formatCost(0.001)).toBe(expectedUsd(0.001, 4, 4))
    expect(formatCost(0.0005)).toBe(expectedUsd(0.0005, 4, 4))
  })

  it('parses string costs', () => {
    expect(formatCost('5.50')).toBe(expectedUsd(5.5, 2, 2))
    expect(formatCost('0.05')).toBe(expectedUsd(0.05, 3, 3))
  })

  it('formatCostZero returns locale-aware zero USD', () => {
    expect(formatCostZero()).toBe(expectedUsd(0, 2, 2))
  })
})

describe('formatNumber / formatPercent / formatCompact', () => {
  it('formatNumber uses locale grouping', () => {
    expect(formatNumber(1234)).toBe(new Intl.NumberFormat(undefined).format(1234))
  })

  it('formatPercent appends percent with locale decimals', () => {
    const num = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(12.5)
    expect(formatPercent(12.5)).toBe(`${num}%`)
  })

  it('formatCompact uses compact notation', () => {
    expect(formatCompact(1500)).toBe(
      new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(
        1500,
      ),
    )
  })
})

describe('plural', () => {
  it('selects one/other for English', () => {
    expect(plural(1, { one: 'entry', other: 'entries' })).toBe('entry')
    expect(plural(0, { one: 'entry', other: 'entries' })).toBe('entries')
    expect(plural(2, { one: 'entry', other: 'entries' })).toBe('entries')
  })
})

describe('timeAgo', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns dash for null/empty', () => {
    expect(timeAgo(null)).toBe('—')
    expect(timeAgo('')).toBe('—')
  })

  it('returns relative time for recent timestamps', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-01-01T12:00:00Z'))
    const result = timeAgo('2024-01-01T11:55:00Z')
    const expected = new Intl.RelativeTimeFormat(undefined, {
      numeric: 'auto',
      style: 'narrow',
    }).format(-5, 'minute')
    expect(result).toBe(expected)
    vi.useRealTimers()
  })

  it('returns now for sub-minute differences', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-01-01T12:00:00Z'))
    const result = timeAgo('2024-01-01T11:59:30Z')
    const expected = new Intl.RelativeTimeFormat(undefined, {
      numeric: 'auto',
      style: 'narrow',
    }).format(0, 'second')
    expect(result).toBe(expected)
    vi.useRealTimers()
  })
})

describe('statusLabel', () => {
  it.each([
    ['queued', 'Queued'],
    ['running', 'Running'],
    ['completed', 'Completed'],
    ['failed', 'Failed'],
    ['cancelled', 'Cancelled'],
    ['pending', 'Pending'],
  ] as const)('maps "%s" to "%s"', (status, expected) => {
    expect(statusLabel(status)).toBe(expected)
  })

  it('capitalizes unknown statuses', () => {
    expect(statusLabel('custom')).toBe('Custom')
    expect(statusLabel('in_progress')).toBe('In_progress')
  })

  it('handles empty string', () => {
    expect(statusLabel('')).toBe('')
  })
})
