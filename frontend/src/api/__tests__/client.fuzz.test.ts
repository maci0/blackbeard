import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ApiError } from '../client'
import { getErrorMessage } from '@/lib/utils'

const NUM_RUNS = 500

describe('fuzz: ApiError', () => {
  it('constructor never throws with any inputs', () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.integer({ min: 0, max: 999 }),
        fc.anything(),
        fc.option(fc.string()),
        (msg, status, detail, reqId) => {
          const err = new ApiError(msg, status, detail, reqId ?? undefined)
          expect(err.message).toBe(msg)
          expect(err.status).toBe(status)
          expect(err instanceof Error).toBe(true)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('always has name set to "ApiError"', () => {
    fc.assert(
      fc.property(fc.string(), fc.integer({ min: 0, max: 999 }), (msg, status) => {
        const err = new ApiError(msg, status, null)
        expect(err.name).toBe('ApiError')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('preserves detail of any type and survives toString()', () => {
    fc.assert(
      fc.property(fc.anything(), (detail) => {
        const err = new ApiError('test', 500, detail)
        expect(err.detail).toBe(detail)
        expect(() => String(err)).not.toThrow()
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('requestId is undefined when not provided', () => {
    fc.assert(
      fc.property(fc.string(), fc.integer({ min: 100, max: 599 }), (msg, status) => {
        const err = new ApiError(msg, status, null)
        expect(err.requestId).toBeUndefined()
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('requestId is preserved when provided', () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.integer({ min: 100, max: 599 }),
        fc.string(),
        (msg, status, reqId) => {
          const err = new ApiError(msg, status, null, reqId)
          expect(err.requestId).toBe(reqId)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('has proper prototype chain', () => {
    fc.assert(
      fc.property(fc.string(), (msg) => {
        const err = new ApiError(msg, 400, null)
        expect(err instanceof ApiError).toBe(true)
        expect(err instanceof Error).toBe(true)
        expect(err.stack).toBeDefined()
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: getErrorMessage', () => {
  it('always returns a string for Error instances', () => {
    fc.assert(
      fc.property(fc.string(), fc.string(), (msg, fallback) => {
        const result = getErrorMessage(new Error(msg), fallback)
        expect(typeof result).toBe('string')
        expect(result).toBe(msg)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns fallback for non-Error inputs', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.string(),
          fc.integer(),
          fc.constant(null),
          fc.constant(undefined),
          fc.constant(0),
          fc.constant(false),
          fc.object(),
          fc.array(fc.anything()),
        ),
        fc.string(),
        (err, fallback) => {
          const result = getErrorMessage(err, fallback)
          expect(typeof result).toBe('string')
          expect(result).toBe(fallback)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('never throws on any input type', () => {
    fc.assert(
      fc.property(fc.anything(), fc.string(), (err, fallback) => {
        expect(() => getErrorMessage(err, fallback)).not.toThrow()
        const result = getErrorMessage(err, fallback)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns the Error message for ApiError instances', () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.integer({ min: 100, max: 599 }),
        fc.string(),
        (msg, status, fallback) => {
          const err = new ApiError(msg, status, null)
          const result = getErrorMessage(err, fallback)
          expect(result).toBe(msg)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('result is always the fallback string or the Error message', () => {
    fc.assert(
      fc.property(fc.anything(), fc.string(), (err, fallback) => {
        const result = getErrorMessage(err, fallback)
        if (err instanceof Error) {
          expect(result).toBe(err.message)
        } else {
          expect(result).toBe(fallback)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })
})
