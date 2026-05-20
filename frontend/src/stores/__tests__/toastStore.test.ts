import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useToastStore } from '../toastStore'

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
    it('removes a toast by ID', () => {
      useToastStore.getState().success('Keep me')
      useToastStore.getState().error('Remove me')

      const toasts = useToastStore.getState().toasts
      expect(toasts).toHaveLength(2)

      const toRemove = toasts[1]!
      useToastStore.getState().dismiss(toRemove.id)

      const remaining = useToastStore.getState().toasts
      expect(remaining).toHaveLength(1)
      expect(remaining[0]?.message).toBe('Keep me')
    })

    it('is a no-op for unknown IDs', () => {
      useToastStore.getState().success('Stay')

      useToastStore.getState().dismiss('nonexistent-id')

      expect(useToastStore.getState().toasts).toHaveLength(1)
    })
  })

  describe('auto-dismiss', () => {
    it('auto-dismisses success toast after 5 seconds', () => {
      useToastStore.getState().success('Temporary')

      expect(useToastStore.getState().toasts).toHaveLength(1)

      vi.advanceTimersByTime(4999)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      vi.advanceTimersByTime(1)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('auto-dismisses error toast after 15 seconds', () => {
      useToastStore.getState().error('Error toast')

      vi.advanceTimersByTime(14999)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      vi.advanceTimersByTime(1)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })

    it('auto-dismisses info toast after 7 seconds', () => {
      useToastStore.getState().info('Info toast')

      vi.advanceTimersByTime(6999)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      vi.advanceTimersByTime(1)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })
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

      // ~3000ms remaining (5000 - 2000)
      vi.advanceTimersByTime(2999)
      expect(useToastStore.getState().toasts).toHaveLength(1)

      vi.advanceTimersByTime(1)
      expect(useToastStore.getState().toasts).toHaveLength(0)
    })
  })
})
