/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ServiceAccounts from '../ServiceAccounts'
import { useResourceStore } from '@/stores/resourceStore'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function renderServiceAccounts() {
  return render(
    <MemoryRouter>
      <ServiceAccounts />
    </MemoryRouter>,
  )
}

const noopFetch = vi.fn()

describe('ServiceAccounts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useResourceStore.setState({
      resources: {},
      loadingKinds: {},
      loading: false,
      error: null,
      fetchResources: noopFetch,
    })
  })

  describe('rendering', () => {
    it('renders page heading', () => {
      renderServiceAccounts()

      expect(screen.getByRole('heading', { name: 'Service Accounts' })).toBeInTheDocument()
    })

    it('shows empty state when no service accounts exist', () => {
      useResourceStore.setState({
        resources: { 'service-accounts': [] },
        loadingKinds: {},
        fetchResources: noopFetch,
      })

      renderServiceAccounts()

      expect(screen.getByText('No service accounts')).toBeInTheDocument()
    })

    it('renders table rows when data exists', () => {
      useResourceStore.setState({
        resources: {
          'service-accounts': [
            {
              id: 'sa-1',
              apiVersion: 'blackbeard/v1',
              metadata: { name: 'sa-researcher', project: 'default', labels: {} },
              spec: { description: 'Researcher service account' },
              version: 1,
              created_at: '2024-01-01',
              updated_at: '2024-01-01',
              kind: 'ServiceAccount',
            },
          ],
        },
        loadingKinds: {},
        fetchResources: noopFetch,
      })

      renderServiceAccounts()

      expect(screen.getByText('sa-researcher')).toBeInTheDocument()
      expect(screen.getByText('Researcher service account')).toBeInTheDocument()
      expect(screen.getByText('default')).toBeInTheDocument()
    })

    it('shows loading skeleton when loading', () => {
      useResourceStore.setState({
        resources: {},
        loadingKinds: { 'service-accounts': true as const },
        fetchResources: noopFetch,
      })

      renderServiceAccounts()

      expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('refresh button triggers refetch', async () => {
      const mockFetch = vi.fn()
      useResourceStore.setState({
        resources: { 'service-accounts': [] },
        loadingKinds: {},
        fetchResources: mockFetch,
      })

      const user = userEvent.setup()
      renderServiceAccounts()

      // fetchResources is called once on mount, clear to track the button click
      mockFetch.mockClear()

      await user.click(screen.getByRole('button', { name: 'Refresh' }))

      expect(mockFetch).toHaveBeenCalledWith('service-accounts')
    })
  })
})
