/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ToolsLibrary from '../ToolsLibrary'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockGet = vi.fn()

vi.mock('@/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args) as Promise<unknown>,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function renderToolsLibrary() {
  return render(
    <MemoryRouter>
      <ToolsLibrary />
    </MemoryRouter>,
  )
}

describe('ToolsLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders page heading', () => {
      mockGet.mockReturnValue(new Promise(() => {}))

      renderToolsLibrary()

      expect(screen.getByRole('heading', { name: 'Tools Library' })).toBeInTheDocument()
    })

    it('shows loading state initially', () => {
      mockGet.mockReturnValue(new Promise(() => {}))

      renderToolsLibrary()

      expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument()
    })

    it('renders tool cards when data loaded', async () => {
      mockGet.mockResolvedValue({
        tools: [
          {
            slug: 'web-search',
            name: 'Web Search',
            description: 'Search the web for information',
            category: 'web',
            type: 'python',
            class_path: 'crewai_tools.WebSearchTool',
            sandbox: 'none',
            tags: ['search', 'web'],
          },
          {
            slug: 'file-reader',
            name: 'File Reader',
            description: 'Read files from disk',
            category: 'file',
            type: 'python',
            class_path: 'crewai_tools.FileReaderTool',
            sandbox: 'none',
            tags: ['file', 'read'],
          },
        ],
        total: 2,
        categories: ['web', 'file'],
      })

      renderToolsLibrary()

      expect(await screen.findByText('Web Search')).toBeInTheDocument()
      expect(screen.getByText('File Reader')).toBeInTheDocument()
      expect(screen.getByText('Search the web for information')).toBeInTheDocument()
      expect(screen.getByText('Read files from disk')).toBeInTheDocument()
    })

    it('shows empty message when no tools match', async () => {
      mockGet.mockResolvedValue({
        tools: [],
        total: 0,
        categories: [],
      })

      renderToolsLibrary()

      expect(await screen.findByText('No tools match your search')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
    })
  })
})
