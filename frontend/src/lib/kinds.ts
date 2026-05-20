/** Resource kind registry — mirrors backend/blackbeard/kinds.py (keep in sync). */

/** Canonical API version. Mirrors backend/blackbeard/kinds.py API_VERSION. */
export const API_VERSION = 'blackbeard/v1'

export const KIND_TO_PLURAL: Record<string, string> = {
  Agent: 'agents',
  Task: 'tasks',
  Crew: 'crews',
  Tool: 'tools',
  LLMConnection: 'llm-connections',
  AgentPolicy: 'agent-policies',
  Guardrail: 'guardrails',
  Flow: 'flows',
  KnowledgeSource: 'knowledge-sources',
  Role: 'roles',
  RoleBinding: 'role-bindings',
  Automation: 'automations',
}

export const PLURAL_TO_KIND: Record<string, string> = Object.fromEntries(
  Object.entries(KIND_TO_PLURAL).map(([k, v]) => [v, k]),
)

export const ALL_PLURALS: string[] = Object.values(KIND_TO_PLURAL)
