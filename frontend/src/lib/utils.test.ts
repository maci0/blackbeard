import { describe, expect, it } from 'vitest'
import { capitalize, toResourceName, parseRef } from './utils'

describe('capitalize', () => {
  it('capitalizes first letter', () => {
    expect(capitalize('agent')).toBe('Agent')
  })

  it('handles empty string', () => {
    expect(capitalize('')).toBe('')
  })

  it('preserves already-capitalized', () => {
    expect(capitalize('Agent')).toBe('Agent')
  })
})

describe('toResourceName', () => {
  it('lowercases and replaces spaces with hyphens', () => {
    expect(toResourceName('My Agent')).toBe('my-agent')
  })

  it('strips invalid characters', () => {
    expect(toResourceName('Hello World!')).toBe('hello-world')
  })

  it('strips leading/trailing hyphens', () => {
    expect(toResourceName('--test--')).toBe('test')
  })

  it('returns "unnamed" for empty result', () => {
    expect(toResourceName('!!!')).toBe('unnamed')
  })
})

describe('parseRef', () => {
  it('extracts name after last slash', () => {
    expect(parseRef('ref:agents/researcher')).toBe('researcher')
  })

  it('returns string as-is when no slash', () => {
    expect(parseRef('researcher')).toBe('researcher')
  })

  it('handles deeply nested paths', () => {
    expect(parseRef('ref:a/b/c')).toBe('c')
  })
})
