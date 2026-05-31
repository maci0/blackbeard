/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Observability from '../Observability'
import { useExecutionStore } from '@/stores/executionStore'
import type { Execution } from '@/lib/types'
import { useResourceStore } from '@/stores/resourceStore'

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

const noopFetchExecutions = vi.fn()
const noopFetchAllResources = vi.fn()

function renderObservability() {
  return render(
    <MemoryRouter>
      <Observability />
    </MemoryRouter>,
  )
}

const sampleExecutions: Execution[] = [
  {
    id: 'exec-1',
    crew_name: 'research-crew',
    crew_project: 'default',
    execution_type: 'kickoff',
    status: 'completed',
    n_iterations: null,
    training_file: null,
    inputs: {},
    outputs: null,
    error: null,
    total_tokens: 5000,
    prompt_tokens: 3000,
    completion_tokens: 2000,
    cost_usd: 0.05,
    initiated_by: 'admin',
    principal_chain: ['admin'],
    created_at: '2024-06-01T10:00:00Z',
    started_at: '2024-06-01T10:00:01Z',
    completed_at: '2024-06-01T10:01:00Z',
    tasks: [],
  },
  {
    id: 'exec-2',
    crew_name: 'writer-crew',
    crew_project: 'default',
    execution_type: 'kickoff',
    status: 'failed',
    n_iterations: null,
    training_file: null,
    inputs: {},
    outputs: null,
    error: 'timeout',
    total_tokens: 1200,
    prompt_tokens: 800,
    completion_tokens: 400,
    cost_usd: 0.02,
    initiated_by: 'admin',
    principal_chain: ['admin'],
    created_at: '2024-06-02T12:00:00Z',
    started_at: '2024-06-02T12:00:01Z',
    completed_at: '2024-06-02T12:00:30Z',
    tasks: [],
  },
]

describe('Observability', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Default: audit logs return empty
    mockGet.mockResolvedValue({ items: [], total: 0 })

    useExecutionStore.setState({
      executions: [],
      executionsTotal: 0,
      loading: false,
      error: null,
      fetchExecutions: noopFetchExecutions,
    })

    useResourceStore.setState({
      resources: {},
      loadingKinds: {},
      loading: false,
      error: null,
      fetchAllResources: noopFetchAllResources,
    })
  })

  describe('rendering', () => {
    it('renders page heading', () => {
      renderObservability()

      expect(screen.getByRole('heading', { name: 'Observability' })).toBeInTheDocument()
    })

    it('renders description text', () => {
      renderObservability()

      expect(
        screen.getByText('Budget, execution, and safety metrics across your platform'),
      ).toBeInTheDocument()
    })

    it('renders all four section headings', () => {
      renderObservability()

      expect(screen.getByText('Budget Utilization')).toBeInTheDocument()
      expect(screen.getByText('Execution Metrics')).toBeInTheDocument()
      expect(screen.getByText('Token Usage')).toBeInTheDocument()
      expect(screen.getByText('Policy and Safety')).toBeInTheDocument()
    })

    it('renders budget stat cards', () => {
      renderObservability()

      expect(screen.getByText('Total Spend')).toBeInTheDocument()
      expect(screen.getByText('Budget Remaining')).toBeInTheDocument()
      expect(screen.getByText('Spend Rate')).toBeInTheDocument()
    })

    it('renders execution stat cards', () => {
      renderObservability()

      expect(screen.getByText('Total Executions')).toBeInTheDocument()
      expect(screen.getByText('Success Rate')).toBeInTheDocument()
      expect(screen.getByText('Avg Duration')).toBeInTheDocument()
      expect(screen.getByText('Active Now')).toBeInTheDocument()
    })

    it('renders token stat cards', () => {
      renderObservability()

      expect(screen.getByText('Total Tokens')).toBeInTheDocument()
      expect(screen.getByText('Prompt Tokens')).toBeInTheDocument()
      expect(screen.getByText('Completion Tokens')).toBeInTheDocument()
    })

    it('renders policy stat cards', () => {
      renderObservability()

      expect(screen.getByText('Policy Denials')).toBeInTheDocument()
      expect(screen.getByText('Guardrail Triggers')).toBeInTheDocument()
      expect(screen.getByText('Budget Exceeded')).toBeInTheDocument()
    })
  })

  describe('with execution data', () => {
    it('displays computed metrics from executions', () => {
      useExecutionStore.setState({
        executions: sampleExecutions,
        executionsTotal: 2,
        loading: false,
        fetchExecutions: noopFetchExecutions,
      })

      renderObservability()

      // Total Executions should show 2
      expect(screen.getByText('2')).toBeInTheDocument()

      // Success rate: 1 completed out of 2 = 50%
      expect(screen.getByText('50%')).toBeInTheDocument()
    })

    it('shows status breakdown chart when executions exist', () => {
      useExecutionStore.setState({
        executions: sampleExecutions,
        executionsTotal: 2,
        loading: false,
        fetchExecutions: noopFetchExecutions,
      })

      renderObservability()

      expect(screen.getByText('Status Breakdown')).toBeInTheDocument()
      // completed and failed should show in the breakdown
      expect(screen.getByText('completed')).toBeInTheDocument()
      expect(screen.getByText('failed')).toBeInTheDocument()
    })

    it('shows empty state charts when no executions', () => {
      useExecutionStore.setState({
        executions: [],
        executionsTotal: 0,
        loading: false,
        fetchExecutions: noopFetchExecutions,
      })

      renderObservability()

      expect(screen.getByText('No executions yet')).toBeInTheDocument()
      expect(screen.getByText('No spend data yet')).toBeInTheDocument()
      expect(screen.getByText('No token data yet')).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('shows skeletons when loading with no data', () => {
      useExecutionStore.setState({
        executions: [],
        executionsTotal: 0,
        loading: true,
        fetchExecutions: noopFetchExecutions,
      })

      renderObservability()

      // Skeleton elements render with aria-hidden, so we check for their
      // presence via the animate-pulse class
      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })
  })

  describe('audit log integration', () => {
    it('displays audit log counts for policy section', async () => {
      mockGet.mockResolvedValue({
        items: [
          {
            id: '1',
            action: 'policy_denied',
            resource_kind: 'Agent',
            resource_name: 'writer',
            timestamp: '2024-06-01T10:00:00Z',
          },
          {
            id: '2',
            action: 'guardrail_triggered',
            resource_kind: 'Task',
            resource_name: 'write-article',
            timestamp: '2024-06-01T10:01:00Z',
          },
          {
            id: '3',
            action: 'budget_exceeded',
            resource_kind: 'Crew',
            resource_name: 'research-crew',
            timestamp: '2024-06-01T10:02:00Z',
          },
        ],
        total: 3,
      })

      renderObservability()

      // Wait for audit log counts to load (they use api.get directly)
      await waitFor(() => {
        const denials = screen.getByLabelText(/Policy Denials/i)
        expect(denials).toBeInTheDocument()
      })
    })
  })

  describe('interactions', () => {
    it('refresh button triggers data refetch', async () => {
      const user = userEvent.setup()
      renderObservability()

      // Clear initial mount calls
      noopFetchExecutions.mockClear()
      noopFetchAllResources.mockClear()

      await user.click(screen.getByRole('button', { name: /refresh data/i }))

      expect(noopFetchExecutions).toHaveBeenCalled()
      expect(noopFetchAllResources).toHaveBeenCalled()
    })
  })
})
