import { describe, it, expect, vi, afterEach } from 'vitest'
import { formatDate, getDuration, formatCost, statusLabel } from '../formatters'

describe('formatDate', () => {
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
    const result = formatDate('2024-06-15T10:30:00Z')
    expect(result).toMatch(/2024/)
    expect(result).toMatch(/15/)
    expect(result).toMatch(/:/)
    expect(result.length).toBeGreaterThan(8)
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
    expect(result).toMatch(/10/)
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
    expect(formatCost(5.123)).toBe('$5.12')
    expect(formatCost(100.5)).toBe('$100.50')
  })

  it('formats costs >= $0.01 with 3 decimal places', () => {
    expect(formatCost(0.055)).toBe('$0.055')
    expect(formatCost(0.1)).toBe('$0.100')
  })

  it('formats costs < $0.01 with 4 decimal places', () => {
    expect(formatCost(0.001)).toBe('$0.0010')
    expect(formatCost(0.0005)).toBe('$0.0005')
  })

  it('parses string costs', () => {
    expect(formatCost('5.50')).toBe('$5.50')
    expect(formatCost('0.05')).toBe('$0.050')
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
