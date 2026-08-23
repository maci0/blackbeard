import { describe, it, expect } from 'vitest'
import { cn, toResourceName, capitalize, caseFold, compareStrings } from '../utils'

describe('cn()', () => {
  it('merges class names', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  it('deduplicates conflicting Tailwind classes', () => {
    const result = cn('px-2', 'px-4')
    expect(result).toBe('px-4')
  })

  it('handles conditional classes', () => {
    const isHidden = false as boolean
    const result = cn('base', isHidden && 'hidden', 'visible')
    expect(result).toBe('base visible')
  })

  it('handles undefined and null inputs', () => {
    const result = cn('base', undefined, null, 'end')
    expect(result).toBe('base end')
  })

  it('handles empty call', () => {
    expect(cn()).toBe('')
  })

  it('merges array inputs', () => {
    expect(cn(['px-2', 'py-1'])).toBe('px-2 py-1')
  })

  it('handles object syntax', () => {
    const result = cn({ 'text-red-500': true, 'text-blue-500': false })
    expect(result).toBe('text-red-500')
  })
})

describe('toResourceName()', () => {
  it('converts to lowercase kebab-case', () => {
    expect(toResourceName('My Agent')).toBe('my-agent')
  })

  it('strips invalid characters', () => {
    expect(toResourceName('Hello World!')).toBe('hello-world')
  })

  it('strips leading and trailing hyphens', () => {
    expect(toResourceName('--test--')).toBe('test')
  })

  it('returns "unnamed" for fully invalid input', () => {
    expect(toResourceName('!!!')).toBe('unnamed')
  })

  it('returns "unnamed" for empty string', () => {
    expect(toResourceName('')).toBe('unnamed')
  })

  it('preserves numbers', () => {
    expect(toResourceName('Agent 007')).toBe('agent-007')
  })

  it('collapses multiple spaces into single hyphen', () => {
    expect(toResourceName('a   b   c')).toBe('a-b-c')
  })
})

describe('capitalize()', () => {
  it('capitalizes first letter', () => {
    expect(capitalize('agent')).toBe('Agent')
  })

  it('handles empty string', () => {
    expect(capitalize('')).toBe('')
  })

  it('preserves already-capitalized', () => {
    expect(capitalize('Agent')).toBe('Agent')
  })

  it('capitalizes first character and preserves the rest', () => {
    expect(capitalize('hELLO')).toBe('HELLO')
  })

  it('handles single character', () => {
    expect(capitalize('a')).toBe('A')
  })
})

describe('caseFold()', () => {
  it('lowercases ASCII', () => {
    expect(caseFold('Agent')).toBe('agent')
  })

  it('uses locale rules for Turkish-sensitive letters when available', () => {
    // toLocaleLowerCase without explicit locale uses the runtime default;
    // for Latin input it still folds case for search matching.
    expect(caseFold('STATUS')).toBe('status')
  })
})

describe('compareStrings()', () => {
  it('orders alphabetically with base sensitivity', () => {
    expect(compareStrings('apple', 'banana')).toBeLessThan(0)
    expect(compareStrings('Banana', 'apple')).toBeGreaterThan(0)
  })

  it('treats accented variants as equal at base sensitivity', () => {
    expect(compareStrings('cafe', 'café')).toBe(0)
  })
})
