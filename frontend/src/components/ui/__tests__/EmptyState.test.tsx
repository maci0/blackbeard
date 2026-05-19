import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { EmptyState } from '../EmptyState'

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('EmptyState', () => {
  describe('rendering', () => {
    it('renders title and description', () => {
      renderWithRouter(
        <EmptyState
          icon={<svg data-testid="icon" />}
          title="No agents yet"
          description="Create your first agent to get started."
        />,
      )

      expect(screen.getByText('No agents yet')).toBeInTheDocument()
      expect(screen.getByText('Create your first agent to get started.')).toBeInTheDocument()
    })

    it('renders icon when provided', () => {
      renderWithRouter(
        <EmptyState
          icon={<svg data-testid="test-icon" />}
          title="Empty"
          description="Nothing here."
        />,
      )

      expect(screen.getByTestId('test-icon')).toBeInTheDocument()
    })

    it('renders action button with onClick handler', async () => {
      const handleClick = vi.fn()
      const user = userEvent.setup()

      renderWithRouter(
        <EmptyState
          icon={<svg />}
          title="No items"
          description="Create one."
          action={{ label: 'Create Agent', onClick: handleClick }}
        />,
      )

      const button = screen.getByText('Create Agent')
      expect(button).toBeInTheDocument()
      expect(button.tagName).toBe('BUTTON')

      await user.click(button)
      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('renders action link when href is provided', () => {
      renderWithRouter(
        <EmptyState
          icon={<svg />}
          title="No items"
          description="Create one."
          action={{ label: 'Go to Studio', href: '/studio' }}
        />,
      )

      const link = screen.getByText('Go to Studio')
      expect(link).toBeInTheDocument()
      expect(link.tagName).toBe('A')
      expect(link).toHaveAttribute('href', '/studio')
    })

    it('does not render action when not provided', () => {
      renderWithRouter(<EmptyState icon={<svg />} title="Empty" description="Nothing here." />)

      expect(screen.queryByRole('button')).not.toBeInTheDocument()
      expect(screen.queryByRole('link')).not.toBeInTheDocument()
    })

    it('icon container has aria-hidden attribute', () => {
      renderWithRouter(
        <EmptyState icon={<svg data-testid="icon" />} title="Empty" description="Nothing here." />,
      )

      const iconContainer = screen.getByTestId('icon').parentElement
      expect(iconContainer).toHaveAttribute('aria-hidden', 'true')
    })
  })
})
