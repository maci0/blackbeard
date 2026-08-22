/** YAML serialization and parsing utilities for Blackbeard resources. */

import yaml from 'js-yaml'
import type { Resource } from '@/lib/types'

/**
 * True when a single-line string must be quoted so that a YAML round-trip
 * reads it back as the same string. Covers special characters and values
 * YAML would coerce to another type ("4.1" -> 4.1, "007" -> 7, "true" -> true).
 */
function needsQuoting(value: string): boolean {
  try {
    if (yaml.load(value, { schema: yaml.JSON_SCHEMA }) !== value) return true
  } catch {
    return true
  }
  return value.startsWith(' ') || value.endsWith(' ')
}

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
    if (needsQuoting(value)) {
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

  return JSON.stringify(value)
}

export function resourceToYaml(resource: Resource): string {
  const lines = [
    `apiVersion: ${resource.apiVersion}`,
    `kind: ${resource.kind}`,
    'metadata:',
    `  name: ${resource.metadata.name}`,
    `  project: ${resource.metadata.project || 'default'}`,
  ]
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- labels may be absent in runtime data
  const labels = resource.metadata.labels ?? {}
  if (Object.keys(labels).length > 0) {
    lines.push('  labels:')
    for (const [k, v] of Object.entries(labels)) {
      lines.push(`    ${serializeValue(k, 2)}: ${serializeValue(v, 2)}`)
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
  const result = yaml.load(yamlStr, { schema: yaml.JSON_SCHEMA })
  if (
    result === null ||
    result === undefined ||
    typeof result !== 'object' ||
    Array.isArray(result)
  ) {
    return {}
  }
  return result as Record<string, unknown>
}

/** Parse a multi-document YAML stream into resource-shaped objects. */
export function parseYamlDocs(yamlStr: string): Record<string, unknown>[] {
  const docs = yaml.loadAll(yamlStr, undefined, { schema: yaml.JSON_SCHEMA })
  return docs.filter(
    (d): d is Record<string, unknown> =>
      d !== null && d !== undefined && typeof d === 'object' && !Array.isArray(d),
  )
}
