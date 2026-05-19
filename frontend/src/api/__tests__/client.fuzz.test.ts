import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ApiError } from '../client'

const NUM_RUNS = 200

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
