/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDocumentTitle } from '@/hooks'

describe('useDocumentTitle', () => {
  beforeEach(() => {
    document.title = 'Blackbeard'
  })

  it('sets document.title on mount with suffix', () => {
    renderHook(() => useDocumentTitle('Studio'))

    expect(document.title).toBe('Studio — Blackbeard')
  })

  it('restores default title on unmount', () => {
    const { unmount } = renderHook(() => useDocumentTitle('Executions'))

    expect(document.title).toBe('Executions — Blackbeard')

    unmount()

    expect(document.title).toBe('Blackbeard')
  })

  it('updates title when prop changes', () => {
    const { rerender } = renderHook(({ title }) => useDocumentTitle(title), {
      initialProps: { title: 'Resources' },
    })

    expect(document.title).toBe('Resources — Blackbeard')

    rerender({ title: 'Agents' })

    expect(document.title).toBe('Agents — Blackbeard')
  })

  it('handles empty string title', () => {
    renderHook(() => useDocumentTitle(''))

    expect(document.title).toBe('— Blackbeard')
  })

  it('restores title even after multiple title changes', () => {
    const { rerender, unmount } = renderHook(({ title }) => useDocumentTitle(title), {
      initialProps: { title: 'First' },
    })

    rerender({ title: 'Second' })
    rerender({ title: 'Third' })

    expect(document.title).toBe('Third — Blackbeard')

    unmount()

    expect(document.title).toBe('Blackbeard')
  })
})
