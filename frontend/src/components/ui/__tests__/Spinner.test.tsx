import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Spinner } from '../Spinner'

describe('Spinner', () => {
  describe('rendering', () => {
    it('renders with default size', () => {
      const { container } = render(<Spinner />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('h-5', 'w-5')
    })

    it('renders with accessible role="status"', () => {
      render(<Spinner />)

      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  describe('sizes', () => {
    it('renders small size', () => {
      const { container } = render(<Spinner size="sm" />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('h-3.5', 'w-3.5')
    })

    it('renders medium size', () => {
      const { container } = render(<Spinner size="md" />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('h-5', 'w-5')
    })

    it('renders large size', () => {
      const { container } = render(<Spinner size="lg" />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('h-8', 'w-8')
    })
  })

  describe('label', () => {
    it('shows default label text', () => {
      render(<Spinner />)

      expect(screen.getByText('Loading')).toBeInTheDocument()
    })

    it('shows custom label text', () => {
      render(<Spinner label="Processing..." />)

      expect(screen.getByText('Processing...')).toBeInTheDocument()
    })

    it('label has sr-only class for screen readers', () => {
      render(<Spinner label="Loading data" />)

      const label = screen.getByText('Loading data')
      expect(label).toHaveClass('sr-only')
    })
  })

  describe('animation', () => {
    it('has animate-spin class for rotation', () => {
      const { container } = render(<Spinner />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('animate-spin')
    })

    it('has motion-reduce:animate-none for reduced motion', () => {
      const { container } = render(<Spinner />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('motion-reduce:animate-none')
    })
  })

  describe('custom className', () => {
    it('accepts and applies additional classes', () => {
      const { container } = render(<Spinner className="text-blue-500" />)

      const svg = container.querySelector('svg')
      expect(svg).not.toBeNull()
      expect(svg).toHaveClass('text-blue-500')
    })
  })
})
