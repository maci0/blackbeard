import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseRef } from '../refs'

const NUM_RUNS = 200

describe('fuzz: parseRef', () => {
  it('never throws on any string', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = parseRef(s)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('always returns a shorter or equal string', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = parseRef(s)
        expect(result.length).toBeLessThanOrEqual(s.length)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('result never contains a forward slash', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = parseRef(s)
        expect(result).not.toContain('/')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('correctly extracts the last path segment', () => {
    const segmentArb = fc.stringMatching(/^[a-z0-9-]{1,20}$/)

    fc.assert(
      fc.property(fc.array(segmentArb, { minLength: 1, maxLength: 5 }), (segments) => {
        const ref = segments.join('/')
        const result = parseRef(ref)
        const lastSegment = segments[segments.length - 1]
        expect(result).toBe(lastSegment)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns the full string when there is no slash', () => {
    fc.assert(
      fc.property(fc.stringMatching(/^[a-z]{1,20}$/), (s) => {
        const result = parseRef(s)
        expect(result).toBe(s)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})
