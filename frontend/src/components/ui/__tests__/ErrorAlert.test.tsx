import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ErrorAlert } from '../ErrorAlert'

describe('ErrorAlert', () => {
  describe('rendering', () => {
    it('renders error message', () => {
      render(<ErrorAlert message="Something went wrong" />)

      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })

    it('renders with role alert for accessibility', () => {
      render(<ErrorAlert message="Error occurred" />)

      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    it('renders without retry button when onAction is not provided', () => {
      render(<ErrorAlert message="Error" />)

      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })

    it('renders retry button when onAction is provided', () => {
      render(<ErrorAlert message="Error" onAction={() => {}} />)

      expect(screen.getByRole('button')).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    it('renders custom action label', () => {
      render(<ErrorAlert message="Error" onAction={() => {}} actionLabel="Try Again" />)

      expect(screen.getByText('Try Again')).toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('calls onAction when retry button is clicked', async () => {
      const onAction = vi.fn()
      const user = userEvent.setup()

      render(<ErrorAlert message="Error" onAction={onAction} />)

      await user.click(screen.getByText('Retry'))
      expect(onAction).toHaveBeenCalledTimes(1)
    })
  })

  describe('accessibility', () => {
    it('uses default action label as aria-label', () => {
      render(<ErrorAlert message="Error" onAction={() => {}} />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Retry')
    })

    it('uses custom ariaLabel when provided', () => {
      render(<ErrorAlert message="Error" onAction={() => {}} ariaLabel="Retry loading resources" />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Retry loading resources')
    })

    it('applies custom className', () => {
      render(<ErrorAlert message="Error" className="mb-4" />)

      const alert = screen.getByRole('alert')
      expect(alert).toHaveClass('mb-4')
    })
  })
})
