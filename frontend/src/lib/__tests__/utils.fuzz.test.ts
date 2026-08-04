import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { toResourceName, parseRef, capitalize, cn } from '../utils'
import { NAME_RE } from '../kinds'

const NUM_RUNS = 200

describe('fuzz: toResourceName', () => {
  it('never throws on any string input', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output always matches resource name pattern or is "unnamed"', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        // The function returns 'unnamed' for fully invalid input,
        // otherwise it must match the resource name pattern.
        expect(result).toMatch(NAME_RE)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('is idempotent', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const once = toResourceName(s)
        const twice = toResourceName(once)
        expect(once).toBe(twice)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output never contains uppercase letters', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        expect(result).toBe(result.toLowerCase())
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output never starts or ends with a hyphen', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        expect(result).not.toMatch(/^-/)
        expect(result).not.toMatch(/-$/)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output only contains valid characters', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        // Every character in the output must be lowercase alphanumeric or hyphen.
        for (const ch of result) {
          expect(ch).toMatch(/[a-z0-9-]/)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output length is bounded by input length plus fallback', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = toResourceName(s)
        // Result can be at most as long as input (lowercased, spaces to hyphens)
        // or 'unnamed' (7 chars) for fully invalid input.
        expect(result.length).toBeLessThanOrEqual(Math.max(s.length, 7))
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

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

describe('fuzz: capitalize', () => {
  it('never throws', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = capitalize(s)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('first char is uppercase if input is non-empty alpha', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => /^[a-zA-Z]/.test(s)),
        (s) => {
          const result = capitalize(s)
          expect(result[0]).toBe(s[0]!.toLocaleUpperCase())
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('preserves string length and uppercases first char', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = capitalize(s)
        expect(result.length).toBe(s.length)
        if (s.length > 0) {
          expect(result[0]).toBe(s[0]!.toLocaleUpperCase())
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('only changes the first character', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 2 }), (s) => {
        const result = capitalize(s)
        expect(result.slice(1)).toBe(s.slice(1))
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns empty string for empty input', () => {
    expect(capitalize('')).toBe('')
  })

  it('is idempotent', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const once = capitalize(s)
        const twice = capitalize(once)
        expect(once).toBe(twice)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: cn', () => {
  it('never throws on any array of strings', () => {
    fc.assert(
      fc.property(fc.array(fc.string(), { maxLength: 20 }), (args) => {
        const result = cn(...args)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on mixed inputs including falsy values', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(fc.string(), fc.constant(undefined), fc.constant(null), fc.constant(false)),
          { maxLength: 20 },
        ),
        (args) => {
          const result = cn(...(args as Parameters<typeof cn>))
          expect(typeof result).toBe('string')
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns empty string for empty array', () => {
    expect(cn()).toBe('')
  })
})
