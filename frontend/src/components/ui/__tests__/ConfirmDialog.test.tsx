import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialog } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    title: 'Delete Resource',
    description: 'Are you sure you want to delete this resource? This action cannot be undone.',
    onConfirm: vi.fn(),
  }

  describe('rendering', () => {
    it('renders with title and description', () => {
      render(<ConfirmDialog {...defaultProps} />)

      expect(screen.getByText('Delete Resource')).toBeInTheDocument()
      expect(
        screen.getByText(
          'Are you sure you want to delete this resource? This action cannot be undone.',
        ),
      ).toBeInTheDocument()
    })

    it('renders default confirm button label', () => {
      render(<ConfirmDialog {...defaultProps} />)

      expect(screen.getByText('Confirm')).toBeInTheDocument()
    })

    it('renders custom confirm button label', () => {
      render(<ConfirmDialog {...defaultProps} confirmLabel="Delete" />)

      expect(screen.getByText('Delete')).toBeInTheDocument()
    })

    it('renders cancel button', () => {
      render(<ConfirmDialog {...defaultProps} />)

      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })

    it('renders close button with accessible label', () => {
      render(<ConfirmDialog {...defaultProps} />)

      expect(screen.getByLabelText('Close')).toBeInTheDocument()
    })

    it('does not render when open is false', () => {
      render(<ConfirmDialog {...defaultProps} open={false} />)

      expect(screen.queryByText('Delete Resource')).not.toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('calls onConfirm when confirm button is clicked', async () => {
      const onConfirm = vi.fn()
      const user = userEvent.setup()

      render(<ConfirmDialog {...defaultProps} onConfirm={onConfirm} />)

      await user.click(screen.getByText('Confirm'))

      expect(onConfirm).toHaveBeenCalledTimes(1)
    })

    it('calls onOpenChange(false) when cancel button is clicked', async () => {
      const onOpenChange = vi.fn()
      const user = userEvent.setup()

      render(<ConfirmDialog {...defaultProps} onOpenChange={onOpenChange} />)

      await user.click(screen.getByText('Cancel'))

      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  describe('destructive variant', () => {
    it('applies red styling for destructive variant', () => {
      render(<ConfirmDialog {...defaultProps} confirmVariant="destructive" confirmLabel="Delete" />)

      const confirmBtn = screen.getByText('Delete').closest('button')
      expect(confirmBtn).toHaveClass('bg-red-600')
    })

    it('does not apply red styling for default variant', () => {
      render(<ConfirmDialog {...defaultProps} />)

      const confirmBtn = screen.getByText('Confirm').closest('button')
      expect(confirmBtn).not.toHaveClass('bg-red-600')
      expect(confirmBtn).toHaveClass('bg-primary')
    })
  })

  describe('loading state', () => {
    it('disables confirm button when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading />)

      const confirmBtn = screen.getByText('Confirm').closest('button')
      expect(confirmBtn).toBeDisabled()
    })

    it('sets aria-busy when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading />)

      const confirmBtn = screen.getByText('Confirm').closest('button')
      expect(confirmBtn).toHaveAttribute('aria-busy', 'true')
    })
  })
})
