import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { PLURAL_TO_KIND, KIND_TO_PLURAL } from '../kinds'

const NUM_RUNS = 500

describe('fuzz: PLURAL_TO_KIND mapping', () => {
  it('returns undefined or a valid kind string for random keys', () => {
    // Exclude Object.prototype keys (__proto__, toString, etc.) that are
    // inherited by plain objects and would return non-string values.
    const protoKeys = new Set(Object.getOwnPropertyNames(Object.prototype))
    fc.assert(
      fc.property(
        fc.string().filter((s) => !protoKeys.has(s)),
        (key) => {
          const result = PLURAL_TO_KIND[key]
          if (result !== undefined) {
            expect(typeof result).toBe('string')
            expect(result.length).toBeGreaterThan(0)
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('lookup never throws for any string key', () => {
    fc.assert(
      fc.property(fc.string(), (key) => {
        expect(() => PLURAL_TO_KIND[key]).not.toThrow()
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('random strings that are not valid plurals return undefined', () => {
    const allPlurals = new Set(Object.keys(PLURAL_TO_KIND))
    // Also exclude Object.prototype keys (toString, valueOf, etc.) that are
    // inherited by plain objects and would return a function, not undefined.
    const protoKeys = new Set(Object.getOwnPropertyNames(Object.prototype))
    fc.assert(
      fc.property(
        fc.string().filter((s) => !allPlurals.has(s) && !protoKeys.has(s)),
        (key) => {
          expect(PLURAL_TO_KIND[key]).toBeUndefined()
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: KIND_TO_PLURAL inverse consistency', () => {
  it('every value in PLURAL_TO_KIND maps back via KIND_TO_PLURAL', () => {
    for (const [plural, kind] of Object.entries(PLURAL_TO_KIND)) {
      expect(KIND_TO_PLURAL[kind]).toBe(plural)
    }
  })

  it('every value in KIND_TO_PLURAL maps back via PLURAL_TO_KIND', () => {
    for (const [kind, plural] of Object.entries(KIND_TO_PLURAL)) {
      expect(PLURAL_TO_KIND[plural]).toBe(kind)
    }
  })

  it('the mappings are bijective (same number of entries)', () => {
    expect(Object.keys(KIND_TO_PLURAL).length).toBe(Object.keys(PLURAL_TO_KIND).length)
  })

  it('all kind values are PascalCase', () => {
    for (const kind of Object.values(PLURAL_TO_KIND)) {
      expect(kind).toMatch(/^[A-Z][a-zA-Z]*$/)
    }
  })

  it('all plural values are lowercase with hyphens', () => {
    for (const plural of Object.values(KIND_TO_PLURAL)) {
      expect(plural).toMatch(/^[a-z][a-z0-9-]*$/)
    }
  })

  it('random kind lookups never throw', () => {
    fc.assert(
      fc.property(fc.string(), (key) => {
        expect(() => KIND_TO_PLURAL[key]).not.toThrow()
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('round-trip: PLURAL_TO_KIND -> KIND_TO_PLURAL for all known entries', () => {
    fc.assert(
      fc.property(fc.constantFrom(...Object.keys(PLURAL_TO_KIND)), (plural) => {
        const kind = PLURAL_TO_KIND[plural]
        expect(kind).toBeDefined()
        const roundTrip = KIND_TO_PLURAL[kind!]
        expect(roundTrip).toBe(plural)
      }),
      { numRuns: 100 },
    )
  })

  it('round-trip: KIND_TO_PLURAL -> PLURAL_TO_KIND for all known entries', () => {
    fc.assert(
      fc.property(fc.constantFrom(...Object.keys(KIND_TO_PLURAL)), (kind) => {
        const plural = KIND_TO_PLURAL[kind]
        expect(plural).toBeDefined()
        const roundTrip = PLURAL_TO_KIND[plural!]
        expect(roundTrip).toBe(kind)
      }),
      { numRuns: 100 },
    )
  })
})
