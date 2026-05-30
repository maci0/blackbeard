import { MarkerType } from '@xyflow/react'

export const DATAFLOW_MARKER_END = {
  type: MarkerType.ArrowClosed,
  width: 12,
  height: 12,
  color: '#94a3b8',
} as const

export function getDefaultNodeData(type: string): Record<string, unknown> {
  switch (type) {
    case 'agent':
      return {
        role: 'New Agent',
        goal: '',
        backstory: '',
        llm: '',
        tools: [],
        verbose: false,
      }
    case 'task':
      return { name: 'New Task', description: '', expected_output: '', agent: '' }
    case 'tool':
      return { name: 'New Tool', type: 'python', class_path: '', description: '', sandbox: 'none' }
    case 'flowStep':
      return { name: 'step-1', type: 'crew', crew: '', function_path: '', listen_to: [] }
    case 'pii':
      return {
        type: 'pii',
        entities: ['PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD'],
        action: 'redact',
        backend: 'default',
      }
    case 'condition':
      return {
        name: 'check-condition',
        type: 'condition',
        condition: '',
        true_branch: '',
        false_branch: '',
      }
    case 'router':
      return {
        name: 'route-step',
        type: 'router',
        routes: {},
      }
    case 'parallel':
      return {
        name: 'parallel-exec',
        type: 'parallel',
        branches: [],
      }
    case 'stickyNote':
      return { text: '', color: 'yellow' }
    default:
      return { label: 'New Node' }
  }
}
