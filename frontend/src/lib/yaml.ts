/** YAML serialization and parsing utilities for Blackbeard resources. */

import yaml from 'js-yaml'
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
    return '\n' + value.map((item) => `${pad}- ${serializeValue(item, indent + 1)}`).join('\n')
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
          return rendered.startsWith('\n') ? `${pad}${k}:${rendered}` : `${pad}${k}: ${rendered}`
        })
        .join('\n')
    )
  }

  return typeof value === 'string' ? value : JSON.stringify(value)
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

export function parseYaml(yamlStr: string): Record<string, unknown> {
  const result = yaml.load(yamlStr)
  if (result === null || result === undefined || typeof result !== 'object') {
    return {}
  }
  return result as Record<string, unknown>
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
    (data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? nodeId
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
