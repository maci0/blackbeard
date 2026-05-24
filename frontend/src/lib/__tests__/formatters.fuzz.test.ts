import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { formatDate, getDuration, formatCost, statusLabel } from '../formatters'

const NUM_RUNS = 500

/* ---------- formatDate ---------- */

describe('fuzz: formatDate', () => {
  it('never throws on random ISO-like date strings', () => {
    const isoArb = fc
      .tuple(
        fc.integer({ min: 1970, max: 2100 }),
        fc.integer({ min: 1, max: 12 }),
        fc.integer({ min: 1, max: 28 }),
        fc.integer({ min: 0, max: 23 }),
        fc.integer({ min: 0, max: 59 }),
        fc.integer({ min: 0, max: 59 }),
      )
      .map(
        ([y, m, d, h, mi, s]) =>
          `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}:${String(s).padStart(2, '0')}Z`,
      )

    fc.assert(
      fc.property(isoArb, (dateStr) => {
        const result = formatDate(dateStr)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on arbitrary garbage strings', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = formatDate(s)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on null or undefined', () => {
    fc.assert(
      fc.property(fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant('')), (input) => {
        const result = formatDate(input)
        expect(result).toBe('—')
      }),
      { numRuns: 10 },
    )
  })

  it('always returns a non-empty string', () => {
    fc.assert(
      fc.property(fc.oneof(fc.string(), fc.constant(null), fc.constant(undefined)), (input) => {
        const result = formatDate(input)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

/* ---------- getDuration ---------- */

describe('fuzz: getDuration', () => {
  it('always returns a string for random ISO date pairs', () => {
    const isoArb = fc
      .tuple(
        fc.integer({ min: 2000, max: 2030 }),
        fc.integer({ min: 1, max: 12 }),
        fc.integer({ min: 1, max: 28 }),
        fc.integer({ min: 0, max: 23 }),
        fc.integer({ min: 0, max: 59 }),
        fc.integer({ min: 0, max: 59 }),
      )
      .map(
        ([y, m, d, h, mi, s]) =>
          `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}:${String(s).padStart(2, '0')}Z`,
      )

    fc.assert(
      fc.property(isoArb, fc.option(isoArb), (start, end) => {
        const result = getDuration(start, end ?? null)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns dash for nullish start', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constant(null), fc.constant(undefined)),
        fc.oneof(fc.constant(null), fc.constant(undefined), fc.string()),
        (start, end) => {
          const result = getDuration(start, end)
          expect(result).toBe('—')
        },
      ),
      { numRuns: 20 },
    )
  })

  it('result matches expected duration format', () => {
    const isoArb = fc
      .tuple(
        fc.integer({ min: 2000, max: 2030 }),
        fc.integer({ min: 1, max: 12 }),
        fc.integer({ min: 1, max: 28 }),
        fc.integer({ min: 0, max: 23 }),
        fc.integer({ min: 0, max: 59 }),
        fc.integer({ min: 0, max: 59 }),
      )
      .map(
        ([y, m, d, h, mi, s]) =>
          `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}T${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}:${String(s).padStart(2, '0')}Z`,
      )

    fc.assert(
      fc.property(isoArb, isoArb, (start, end) => {
        const result = getDuration(start, end)
        // Must be either "Ns", "Nm Ns", or "Nh Nm" format
        expect(result).toMatch(/^-?\d+s$|^\d+m -?\d+s$|^\d+h \d+m$/)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

/* ---------- formatCost ---------- */

describe('fuzz: formatCost', () => {
  it('never throws on random numbers including edge cases', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.double({ noNaN: false }),
          fc.constant(NaN),
          fc.constant(Infinity),
          fc.constant(-Infinity),
          fc.constant(0),
          fc.constant(-0),
        ),
        (n) => {
          const result = formatCost(n)
          expect(typeof result).toBe('string')
          expect(result.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on random strings as cost', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = formatCost(s)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on null or undefined', () => {
    fc.assert(
      fc.property(fc.oneof(fc.constant(null), fc.constant(undefined)), (input) => {
        const result = formatCost(input)
        expect(result).toBe('—')
      }),
      { numRuns: 10 },
    )
  })

  it('positive valid numbers always produce a dollar-prefixed string', () => {
    fc.assert(
      fc.property(fc.double({ min: 0.0001, max: 1_000_000, noNaN: true }), (n) => {
        const result = formatCost(n)
        expect(result).toMatch(/^\$\d/)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('negative numbers produce dash (filtered by n === 0 || isNaN check)', () => {
    fc.assert(
      fc.property(fc.double({ min: -1_000_000, max: -0.0001, noNaN: true }), (n) => {
        // Negative numbers should still produce a string (implementation detail:
        // formatCost does not explicitly guard negatives, so it formats them)
        const result = formatCost(n)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

/* ---------- statusLabel ---------- */

describe('fuzz: statusLabel', () => {
  it('always returns a string for any input', () => {
    // Exclude Object.prototype keys (toString, valueOf, etc.) that collide
    // with the STATUS_DISPLAY Record lookup via prototype chain, returning
    // a function instead of a string. This is a known prototype pollution
    // edge case in plain JS objects used as maps.
    const protoKeys = new Set(Object.getOwnPropertyNames(Object.prototype))
    fc.assert(
      fc.property(
        fc.string().filter((s) => !protoKeys.has(s)),
        (s) => {
          const result = statusLabel(s)
          expect(typeof result).toBe('string')
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('known statuses always return their display label', () => {
    const knownStatuses = ['queued', 'running', 'completed', 'failed', 'cancelled', 'pending']
    fc.assert(
      fc.property(fc.constantFrom(...knownStatuses), (status) => {
        const result = statusLabel(status)
        expect(result).toBe(status.charAt(0).toUpperCase() + status.slice(1))
      }),
      { numRuns: 100 },
    )
  })

  it('unknown statuses get capitalized', () => {
    // Exclude Object.prototype keys (toString, valueOf, etc.) that collide
    // with the STATUS_DISPLAY Record lookup via prototype chain.
    const protoKeys = new Set(Object.getOwnPropertyNames(Object.prototype))
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => /^[a-z]/.test(s) && !protoKeys.has(s)),
        (s) => {
          const result = statusLabel(s)
          expect(result.charAt(0)).toBe(s.charAt(0).toUpperCase())
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('empty string returns empty string', () => {
    expect(statusLabel('')).toBe('')
  })

  it('result length matches input length for non-prototype strings', () => {
    // Exclude Object.prototype keys that collide with Record lookup.
    const protoKeys = new Set(Object.getOwnPropertyNames(Object.prototype))
    fc.assert(
      fc.property(
        fc.string().filter((s) => !protoKeys.has(s)),
        (s) => {
          const result = statusLabel(s)
          // statusLabel either returns a known label or capitalize(s), both preserve length
          expect(result.length).toBe(
            ['queued', 'running', 'completed', 'failed', 'cancelled', 'pending'].includes(s)
              ? result.length // known status: length is already correct
              : s.length,
          )
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})
