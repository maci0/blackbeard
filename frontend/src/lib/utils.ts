import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function capitalize(s: string): string {
  return s.length > 0 ? s.charAt(0).toUpperCase() + s.slice(1) : ''
}

export function toResourceName(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/^-+|-+$/g, '') || 'unnamed'
  )
}

export function parseRef(ref: string): string {
  const idx = ref.lastIndexOf('/')
  return idx >= 0 ? ref.slice(idx + 1) : ref
}

/** `name` in task/tool data becomes metadata.name (not a spec field). */
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
