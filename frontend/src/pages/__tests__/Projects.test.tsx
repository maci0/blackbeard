/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Projects from '../Projects'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args) as Promise<unknown>,
    post: (...args: unknown[]) => mockPost(...args) as Promise<unknown>,
    put: vi.fn(),
    delete: (...args: unknown[]) => mockDelete(...args) as Promise<unknown>,
  },
}))

function renderProjects() {
  return render(
    <MemoryRouter>
      <Projects />
    </MemoryRouter>,
  )
}

describe('Projects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders page heading', () => {
      mockGet.mockReturnValue(new Promise(() => {}))

      renderProjects()

      expect(screen.getByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    })

    it('shows loading skeleton initially', () => {
      mockGet.mockReturnValue(new Promise(() => {}))

      renderProjects()

      expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument()
    })

    it('shows empty state when no projects exist', async () => {
      mockGet.mockResolvedValue({ items: [], total: 0 })

      renderProjects()

      expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    })

    it('renders project rows when data exists', async () => {
      mockGet.mockResolvedValue({
        items: [
          {
            metadata: { name: 'test-project', project: 'default' },
            spec: { description: 'Test' },
            version: 1,
            created_at: '2024-01-01',
            updated_at: '2024-01-01',
            kind: 'Project',
          },
        ],
        total: 1,
      })

      renderProjects()

      expect(await screen.findByText('test-project')).toBeInTheDocument()
      expect(screen.getByText('Test')).toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('opens create dialog when button clicked', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({ items: [], total: 0 })

      renderProjects()

      await screen.findByText('No projects yet')

      await user.click(screen.getByRole('button', { name: /new project/i }))

      // The dialog renders a form with name and description fields
      expect(await screen.findByPlaceholderText('my-project')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Production workloads')).toBeInTheDocument()
    })

    it('search input filters projects', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValue({
        items: [
          {
            metadata: { name: 'alpha', project: 'default' },
            spec: { description: 'First' },
            version: 1,
            created_at: '2024-01-01',
            updated_at: '2024-01-01',
            kind: 'Project',
          },
          {
            metadata: { name: 'beta', project: 'default' },
            spec: { description: 'Second' },
            version: 1,
            created_at: '2024-01-01',
            updated_at: '2024-01-01',
            kind: 'Project',
          },
        ],
        total: 2,
      })

      renderProjects()

      await screen.findByText('alpha')
      expect(screen.getByText('beta')).toBeInTheDocument()

      const searchInput = screen.getByLabelText('Filter projects')
      await user.type(searchInput, 'alpha')

      expect(screen.getByText('alpha')).toBeInTheDocument()
      expect(screen.queryByText('beta')).not.toBeInTheDocument()
    })
  })
})
