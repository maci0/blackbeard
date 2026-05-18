const KIND_BADGE_CLASSES: Record<string, string> = {
  Agent: 'bg-violet-100 text-violet-700 dark:bg-violet-900 dark:text-violet-300',
  Task: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  Crew: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
  Tool: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
  LLMConnection: 'bg-pink-100 text-pink-700 dark:bg-pink-900 dark:text-pink-300',
  AgentPolicy: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-300',
  Guardrail: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  Flow: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300',
  KnowledgeSource: 'bg-teal-100 text-teal-700 dark:bg-teal-900 dark:text-teal-300',
  Role: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
  RoleBinding: 'bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300',
}

const KIND_DISPLAY: Record<string, string> = {
  LLMConnection: 'LLM Connection',
  AgentPolicy: 'Agent Policy',
  KnowledgeSource: 'Knowledge Source',
  RoleBinding: 'Role Binding',
}

export function KindBadge({ kind }: { kind: string }) {
  const classes =
    KIND_BADGE_CLASSES[kind] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  const displayName = KIND_DISPLAY[kind] || kind
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${classes}`}
    >
      {displayName}
    </span>
  )
}
