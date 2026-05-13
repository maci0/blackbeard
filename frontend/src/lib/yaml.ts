/** YAML serialization and parsing utilities for Blackbeard resources. */

import type { Resource } from '@/stores/resourceStore'
import { capitalize, toResourceName } from '@/lib/utils'

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
    if (
      /[:#{}[\],&*?|<>=!%@`]/.test(value) ||
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

export function resourceToYaml(resource: Resource): string {
  const lines = [
    `apiVersion: ${resource.apiVersion}`,
    `kind: ${resource.kind}`,
    'metadata:',
    `  name: ${resource.metadata.name}`,
    `  namespace: ${resource.metadata.namespace || 'default'}`,
  ]
  const labels = resource.metadata.labels ?? {}
  if (Object.keys(labels).length > 0) {
    lines.push('  labels:')
    for (const [k, v] of Object.entries(labels)) {
      lines.push(`    ${k}: ${v}`)
    }
  }
  lines.push('spec:')
  for (const [k, v] of Object.entries(resource.spec)) {
    const rendered = serializeValue(v, 2)
    lines.push(rendered.startsWith('\n') ? `  ${k}:${rendered}` : `  ${k}: ${rendered}`)
  }
  lines.push(`version: ${resource.version}`)
  return lines.join('\n')
}

function parseScalar(value: string): unknown {
  if (!value || value === 'null' || value === '~') return null
  if (value === 'true') return true
  if (value === 'false') return false
  if (/^-?\d+$/.test(value)) return parseInt(value, 10)
  if (/^-?\d+\.\d+$/.test(value)) return parseFloat(value)
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1)
  }
  return value
}

export function parseYaml(yamlStr: string): Record<string, unknown> {
  const lines = yamlStr.split('\n')
  const root: Record<string, unknown> = {}
  const stack: Array<{ indent: number; obj: Record<string, unknown> }> = [
    { indent: -2, obj: root },
  ]

  let i = 0
  while (i < lines.length) {
    const line = lines[i] ?? ''
    i++
    if (!line.trim() || line.trim().startsWith('#')) continue

    const indent = line.search(/\S/)
    const trimmed = line.trim()

    while (stack.length > 1 && (stack[stack.length - 1]?.indent ?? -2) >= indent) {
      stack.pop()
    }
    const parent = stack[stack.length - 1]?.obj ?? root

    if (trimmed.startsWith('- ')) continue

    const colonIdx = trimmed.indexOf(':')
    if (colonIdx === -1) continue

    const key = trimmed.slice(0, colonIdx).trim()
    const rest = trimmed.slice(colonIdx + 1).trim()

    if (rest === '|' || rest === '>') {
      const blockLines: string[] = []
      const baseIndent = indent + 2
      while (i < lines.length) {
        const next = lines[i] ?? ''
        if (!next.trim()) { blockLines.push(''); i++; continue }
        if (next.search(/\S/) < baseIndent) break
        blockLines.push(next.slice(baseIndent))
        i++
      }
      parent[key] = blockLines.join('\n').trimEnd()
    } else if (!rest) {
      const nextNonEmpty = lines.slice(i).find((l) => l.trim() && !l.trim().startsWith('#'))
      if (nextNonEmpty && nextNonEmpty.trim().startsWith('- ')) {
        const arr: unknown[] = []
        parent[key] = arr
        while (i < lines.length) {
          const next = lines[i] ?? ''
          if (!next.trim()) { i++; continue }
          const ni = next.search(/\S/)
          const nextTrimmed = next.trim()
          if (ni <= indent && nextTrimmed && !nextTrimmed.startsWith('-')) break
          if (nextTrimmed.startsWith('- ')) {
            arr.push(parseScalar(nextTrimmed.slice(2).trim()))
          }
          i++
        }
      } else {
        const obj: Record<string, unknown> = {}
        parent[key] = obj
        stack.push({ indent, obj })
      }
    } else {
      parent[key] = parseScalar(rest)
    }
  }

  return root
}

const NODE_SPEC_FIELDS: Record<string, readonly string[]> = {
  agent: ['role', 'goal', 'backstory', 'llm', 'verbose', 'tools'],
  task: ['description', 'expected_output', 'agent'],
  tool: ['type', 'class_path', 'description', 'sandbox'],
}

export function nodeToYaml(
  nodeType: string,
  nodeId: string,
  data: Record<string, unknown>,
): string {
  const kind = capitalize(nodeType)
  const rawName =
    (data['role'] as string | undefined) ??
    (data['name'] as string | undefined) ??
    nodeId
  const name = toResourceName(rawName)

  const fields = NODE_SPEC_FIELDS[nodeType] ?? []
  const spec: Record<string, unknown> = {}
  for (const f of fields) {
    if (data[f] !== undefined && data[f] !== '' && data[f] !== null) {
      spec[f] = data[f]
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
