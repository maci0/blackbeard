import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOnboarding } from '../useOnboarding'

describe('useOnboarding', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns showOnboarding=true when no localStorage key exists', () => {
    const { result } = renderHook(() => useOnboarding())

    expect(result.current.showOnboarding).toBe(true)
  })

  it('returns showOnboarding=false when localStorage key exists', () => {
    localStorage.setItem('blackbeard_onboarding_completed', 'true')

    const { result } = renderHook(() => useOnboarding())

    expect(result.current.showOnboarding).toBe(false)
  })

  it('dismissOnboarding sets localStorage and updates state to false', () => {
    const { result } = renderHook(() => useOnboarding())

    expect(result.current.showOnboarding).toBe(true)

    act(() => {
      result.current.dismissOnboarding()
    })

    expect(result.current.showOnboarding).toBe(false)
    expect(localStorage.getItem('blackbeard_onboarding_completed')).toBe('true')
  })

  it('dismissOnboarding is stable between renders', () => {
    const { result, rerender } = renderHook(() => useOnboarding())

    const firstDismiss = result.current.dismissOnboarding
    rerender()
    const secondDismiss = result.current.dismissOnboarding

    expect(firstDismiss).toBe(secondDismiss)
  })

  it('persists dismissed state across hook re-mounts', () => {
    const { result: first } = renderHook(() => useOnboarding())
    act(() => {
      first.current.dismissOnboarding()
    })

    const { result: second } = renderHook(() => useOnboarding())
    expect(second.current.showOnboarding).toBe(false)
  })
})
