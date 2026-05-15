/** Default data for newly created studio nodes. */
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
    default:
      return { label: 'New Node' }
  }
}
