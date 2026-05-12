/** Canonical resource kind registry — single source of truth for the frontend. */

export const KIND_TO_PLURAL: Record<string, string> = {
  Agent: 'agents',
  Task: 'tasks',
  Crew: 'crews',
  Tool: 'tools',
  LLMConnection: 'llm-connections',
  AgentPolicy: 'agent-policies',
  Guardrail: 'guardrails',
}

export const PLURAL_TO_KIND: Record<string, string> = Object.fromEntries(
  Object.entries(KIND_TO_PLURAL).map(([k, v]) => [v, k])
)

export const ALL_KINDS: string[] = Object.keys(KIND_TO_PLURAL)
export const ALL_PLURALS: string[] = Object.values(KIND_TO_PLURAL)

export const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
