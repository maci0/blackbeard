import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Capitalize first letter */
export function capitalize(s: string): string {
  return s.length > 0 ? s.charAt(0).toUpperCase() + s.slice(1) : ''
}

/** Convert a string to a kebab-case resource name */
export function toResourceName(s: string): string {
  return s
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/^-+|-+$/g, '')
    || 'unnamed'
}

/** Simple YAML serializer for resource specs */
export function serializeValue(value: unknown, indent: number): string {
  const pad = '  '.repeat(indent)

  if (value === null || value === undefined) return 'null'
  if (typeof value === 'boolean') return String(value)
  if (typeof value === 'number') return String(value)

  if (typeof value === 'string') {
    if (value === '') return '""'
    if (value.includes('\n')) {
      const indented = value
        .split('\n')
        .map((l) => `${pad}  ${l}`)
        .join('\n')
      return `|\n${indented}`
    }
    // Quote strings that contain special YAML chars or reserved words
    if (
      /[:#{}\[\],&*?|<>=!%@`]/.test(value) ||
      value.startsWith(' ') ||
      value === 'true' ||
      value === 'false' ||
      value === 'null'
    ) {
      return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
    }
    return value
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    return (
      '\n' +
      value.map((item) => `${pad}- ${serializeValue(item, indent + 1)}`).join('\n')
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, v]) => v !== undefined && v !== null && v !== '',
    )
    if (entries.length === 0) return '{}'
    return (
      '\n' +
      entries
        .map(([k, v]) => {
          const rendered = serializeValue(v, indent + 1)
          return rendered.startsWith('\n')
            ? `${pad}${k}:${rendered}`
            : `${pad}${k}: ${rendered}`
        })
        .join('\n')
    )
  }

  return String(value)
}

/** Default data for new canvas nodes, shared between Canvas and Palette */
export function getDefaultNodeData(type: string): Record<string, unknown> {
  switch (type) {
    case 'agent':
      return { role: 'New Agent', goal: '', backstory: '', llm: 'gpt-4o', tools: [], verbose: false }
    case 'task':
      return { name: 'New Task', description: '', expected_output: '', agent: '' }
    case 'tool':
      return { name: 'New Tool', type: 'python', class_path: '', description: '', sandbox: 'none' }
    default:
      return { label: 'New Node' }
  }
}

/** Build a full resource YAML string from node type + data */
export function nodeToYaml(
  nodeType: string,
  nodeId: string,
  data: Record<string, unknown>,
): string {
  const kind = capitalize(nodeType)

  // Derive a clean name
  const rawName =
    (data['role'] as string | undefined) ??
    (data['name'] as string | undefined) ??
    nodeId
  const name = toResourceName(rawName)

  // Build spec from data, filtered to known fields per kind
  const spec: Record<string, unknown> = {}

  if (nodeType === 'agent') {
    const fields = ['role', 'goal', 'backstory', 'llm', 'verbose', 'tools'] as const
    for (const f of fields) {
      if (data[f] !== undefined && data[f] !== '' && data[f] !== null) {
        spec[f] = data[f]
      }
    }
  } else if (nodeType === 'task') {
    const fields = ['name', 'description', 'expected_output', 'agent'] as const
    for (const f of fields) {
      if (data[f] !== undefined && data[f] !== '' && data[f] !== null) {
        spec[f] = data[f]
      }
    }
  } else if (nodeType === 'tool') {
    const fields = ['name', 'type', 'class_path', 'description', 'sandbox'] as const
    for (const f of fields) {
      if (data[f] !== undefined && data[f] !== '' && data[f] !== null) {
        spec[f] = data[f]
      }
    }
  }

  const specYaml = serializeValue(spec, 1)

  return [
    'apiVersion: blackbeard/v1',
    `kind: ${kind}`,
    'metadata:',
    `  name: ${name}`,
    'spec:',
    ...(specYaml.startsWith('\n') ? [specYaml.slice(1)] : [specYaml]),
  ].join('\n')
}
