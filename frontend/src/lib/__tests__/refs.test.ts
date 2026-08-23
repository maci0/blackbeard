import { describe, it, expect } from 'vitest'
import { parseRef } from '../refs'

describe('parseRef()', () => {
  it('extracts name from ref string', () => {
    expect(parseRef('ref:agents/researcher')).toBe('researcher')
  })

  it('handles non-ref strings without slash', () => {
    expect(parseRef('researcher')).toBe('researcher')
  })

  it('handles deeply nested paths', () => {
    expect(parseRef('ref:a/b/c')).toBe('c')
  })

  it('handles ref with just kind and name', () => {
    expect(parseRef('ref:tools/web-search')).toBe('web-search')
  })

  it('handles plain path', () => {
    expect(parseRef('tasks/write-report')).toBe('write-report')
  })

  it('handles trailing slash', () => {
    expect(parseRef('agents/')).toBe('')
  })
})
