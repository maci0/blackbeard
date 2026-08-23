import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useToastStore } from '../toastStore'

const EXIT_ANIMATION_MS = 300

describe('toastStore', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useToastStore.setState({ toasts: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('addToast', () => {
    it('adds a success toast', () => {
      useToastStore.getState().success('Operation succeeded')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(1)
      expect(toasts[0]).toMatchObject({
        type: 'success',
        message: 'Operation succeeded',
      })
      expect(toasts[0]?.id).toMatch(/^toast-/)
    })

    it('adds an error toast', () => {
      useToastStore.getState().error('Something went wrong')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(1)
      expect(toasts[0]).toMatchObject({
        type: 'error',
        message: 'Something went wrong',
      })
    })

    it('adds an info toast', () => {
      useToastStore.getState().info('FYI notification')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(1)
      expect(toasts[0]).toMatchObject({
        type: 'info',
        message: 'FYI notification',
      })
    })
  })

  describe('multiple toasts', () => {
    it('stacks multiple toasts', () => {
      useToastStore.getState().success('First')
      useToastStore.getState().error('Second')
      useToastStore.getState().info('Third')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(3)
      expect(toasts[0]?.message).toBe('First')
      expect(toasts[1]?.message).toBe('Second')
      expect(toasts[2]?.message).toBe('Third')
    })

    it('assigns unique IDs to each toast', () => {
      useToastStore.getState().success('One')
      useToastStore.getState().success('Two')

      const toasts = useToastStore.getState().toasts
      expect(toasts[0]?.id).not.toBe(toasts[1]?.id)
    })
  })

  describe('dismiss', () => {
    it('marks toast as dismissing then removes after animation', () => {
      useToastStore.getState().success('Keep me')
      useToastStore.getState().error('Remove me')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(2)

      const toRemove = toasts[1]!
      useToastStore.getState().dismiss(toRemove.id)

      // Immediately: toast marked as dismissing but still present
      const afterDismiss = useToastStore.getState().toasts
      expect(afterDismiss).toHaveLength(2)
      expect(afterDismiss[1]?.dismissing).toBe(true)

      // After animation delay: toast removed
      vi.advanceTimersByTime(EXIT_ANIMATION_MS)
      const remaining = useToastStore.getState().toasts
      expect(remaining).toHaveLength(1)
      expect(remaining[0]?.message).toBe('Keep me')
    })

    it('is a no-op for unknown IDs', () => {
      useToastStore.getState().success('Stay')

      useToastStore.getState().dismiss('nonexistent-id')
      vi.advanceTimersByTime(EXIT_ANIMATION_MS)

      expect(useToastStore.getState().toasts).toHaveLength(1)
    })
  })

  describe('auto-dismiss', () => {
    it.each([
      { method: 'success', seconds: 7 },
      { method: 'error', seconds: 15 },
      { method: 'info', seconds: 7 },
    ] as const)(
      'auto-dismisses $method toast after $seconds seconds + exit animation',
      ({ method, seconds }) => {
        useToastStore.getState()[method](`${method} toast`)

        expect(useToastStore.getState().toasts).toHaveLength(1)

        vi.advanceTimersByTime(seconds * 1000 - 1)
        expect(useToastStore.getState().toasts).toHaveLength(1)

        // Timer fires at exactly duration, sets dismissing=true
        vi.advanceTimersByTime(1)
        expect(useToastStore.getState().toasts[0]?.dismissing).toBe(true)

        // Removed after exit animation
        vi.advanceTimersByTime(EXIT_ANIMATION_MS)
        expect(useToastStore.getState().toasts).toHaveLength(0)
      },
    )
  })

  describe('pause and resume', () => {
    it('pauses auto-dismiss timer', () => {
      useToastStore.getState().success('Pausable')
      const id = useToastStore.getState().toasts[0]!.id

      vi.advanceTimersByTime(2000)
      useToastStore.getState().pause(id)

      vi.advanceTimersByTime(10000)
      expect(useToastStore.getState().toasts).toHaveLength(1)
    })

    it('resumes auto-dismiss timer with remaining time', () => {
      useToastStore.getState().success('Resumable')
      const id = useToastStore.getState().toasts[0]!.id

      vi.advanceTimersByTime(2000)
      useToastStore.getState().pause(id)

      vi.advanceTimersByTime(10000)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      useToastStore.getState().resume(id)

      // ~5000ms remaining (7000 - 2000)
      vi.advanceTimersByTime(4999)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      // Timer fires, sets dismissing
      vi.advanceTimersByTime(1)
      expect(useToastStore.getState().toasts[0]?.dismissing).toBe(true)

      // Removed after exit animation
      vi.advanceTimersByTime(EXIT_ANIMATION_MS)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })
  })
})
