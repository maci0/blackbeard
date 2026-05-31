import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../StatusBadge'

describe('StatusBadge', () => {
  describe('renders correct text for each status', () => {
    it.each([
      ['queued', 'Queued'],
      ['running', 'Running'],
      ['completed', 'Completed'],
      ['failed', 'Failed'],
      ['cancelled', 'Cancelled'],
      ['pending', 'Pending'],
    ] as const)('displays "%s" as "%s"', (status, expectedText) => {
      render(<StatusBadge status={status} />)
      expect(screen.getByText(expectedText)).toBeInTheDocument()
    })
  })

  describe('renders with correct styling classes', () => {
    it('applies green classes for completed status', () => {
      render(<StatusBadge status="completed" />)
      const badge = screen.getByText('Completed').closest('span')
      expect(badge).toHaveClass('bg-green-100', 'text-green-700')
      expect(badge).not.toHaveClass('bg-red-100', 'bg-blue-100')
    })

    it('applies red classes for failed status', () => {
      render(<StatusBadge status="failed" />)
      const badge = screen.getByText('Failed').closest('span')
      expect(badge).toHaveClass('bg-red-100', 'text-red-700')
      expect(badge).not.toHaveClass('bg-green-100', 'bg-blue-100')
    })

    it('applies blue classes for running status', () => {
      render(<StatusBadge status="running" />)
      const badge = screen.getByText('Running').closest('span')
      expect(badge).toHaveClass('bg-blue-100', 'text-blue-700')
    })

    it('applies gray classes for queued status', () => {
      render(<StatusBadge status="queued" />)
      const badge = screen.getByText('Queued').closest('span')
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-700')
    })
  })

  describe('handles unknown status gracefully', () => {
    it('renders with fallback styling for unknown status', () => {
      render(<StatusBadge status="unknown_status" />)
      const badge = screen.getByText('Unknown_status').closest('span')
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-700')
    })

    it('capitalizes unknown status text', () => {
      render(<StatusBadge status="custom" />)
      expect(screen.getByText('Custom')).toBeInTheDocument()
    })
  })

  describe('status icons', () => {
    it('renders a pulsing indicator for running status', () => {
      const { container } = render(<StatusBadge status="running" />)
      const animatedSpan = container.querySelector('.animate-ping')
      expect(animatedSpan).toBeInTheDocument()
    })

    it('does not render pulsing indicator for completed status', () => {
      const { container } = render(<StatusBadge status="completed" />)
      const animatedSpan = container.querySelector('.animate-ping')
      expect(animatedSpan).not.toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('sets role="status" when live prop is true', () => {
      render(<StatusBadge status="running" live />)
      expect(screen.getByRole('status')).toBeInTheDocument()
    })

    it('always sets role="status" regardless of live prop', () => {
      render(<StatusBadge status="running" />)
      const badge = screen.getByText('Running').closest('span')
      expect(badge).toHaveAttribute('role', 'status')
    })
  })
})
