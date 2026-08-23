/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../Dashboard'
import { formatCost } from '@/lib/formatters'
import type { Execution, Resource } from '@/lib/types'

vi.mock('@/hooks/useDocumentTitle', () => ({
  useDocumentTitle: vi.fn(),
}))

let mockResources: Record<string, Resource[]> = {}
let mockExecutions: Execution[] = []
let mockResourcesLoading = false
let mockExecutionsLoading = false

vi.mock('@/stores/resourceStore', () => ({
  useResourceStore: () => ({
    resources: mockResources,
    loading: mockResourcesLoading,
    fetchAllResources: vi.fn(),
  }),
}))

vi.mock('@/stores/executionStore', () => ({
  useExecutionStore: () => ({
    executions: mockExecutions,
    loading: mockExecutionsLoading,
    fetchExecutions: vi.fn(),
  }),
}))

function makeResource(kindPlural: string, name: string): Resource {
  return {
    id: `${kindPlural}-${name}`,
    apiVersion: 'v1',
    kind: kindPlural,
    metadata: { name, project: 'default', labels: {} },
    spec: {},
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function makeExecution(overrides: Partial<Execution>): Execution {
  return {
    id: overrides.id ?? 'exec-1',
    crew_name: 'research-crew',
    crew_project: 'default',
    execution_type: 'kickoff',
    status: 'completed',
    n_iterations: null,
    training_file: null,
    inputs: {},
    outputs: null,
    error: null,
    total_tokens: 100,
    prompt_tokens: 60,
    completion_tokens: 40,
    cost_usd: 0,
    initiated_by: null,
    principal_chain: [],
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:01:00Z',
    tasks: undefined,
    ...overrides,
  }
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockResources = {}
    mockExecutions = []
    mockResourcesLoading = false
    mockExecutionsLoading = false
  })

  it('renders page heading', () => {
    renderDashboard()

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('renders all five stat cards with store-derived values', () => {
    mockResources = {
      agents: [makeResource('agents', 'a'), makeResource('agents', 'b')],
      'llm-connections': [makeResource('llm-connections', 'm')],
      automations: [makeResource('automations', 'auto')],
    }
    mockExecutions = [
      makeExecution({ status: 'running', cost_usd: 0.5 }),
      makeExecution({ id: 'exec-2', status: 'completed', cost_usd: 1.5 }),
    ]

    renderDashboard()

    expect(screen.getByRole('link', { name: 'Total Resources: 4' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Active Executions: 1' })).toBeInTheDocument()
    const expectedSpend = formatCost(2)
    expect(screen.getByRole('link', { name: `LLM Spend: ${expectedSpend}` })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Total Models: 1' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Automations: 1' })).toBeInTheDocument()
  })

  it('links stat cards to their detail pages', () => {
    renderDashboard()

    expect(screen.getByRole('link', { name: /^Total Resources/ })).toHaveAttribute(
      'href',
      '/resources',
    )
    expect(screen.getByRole('link', { name: /^Active Executions/ })).toHaveAttribute(
      'href',
      '/executions',
    )
    expect(screen.getByRole('link', { name: /^Total Models/ })).toHaveAttribute('href', '/models')
    expect(screen.getByRole('link', { name: /^Automations/ })).toHaveAttribute(
      'href',
      '/automations',
    )
  })

  it('renders recent executions with crew names', () => {
    mockExecutions = [
      makeExecution({ crew_name: 'alpha-crew' }),
      makeExecution({ id: 'exec-2', crew_name: 'beta-crew' }),
    ]

    renderDashboard()

    expect(screen.getByText('Recent Executions')).toBeInTheDocument()
    expect(screen.getByText('alpha-crew')).toBeInTheDocument()
    expect(screen.getByText('beta-crew')).toBeInTheDocument()
  })

  it('shows empty states when there is no data', () => {
    renderDashboard()

    expect(screen.getByText('No executions yet')).toBeInTheDocument()
    expect(screen.getByText('No resources created yet')).toBeInTheDocument()
    expect(screen.getByText('No spend data yet')).toBeInTheDocument()
  })
})
