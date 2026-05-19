/** Bidirectional YAML <-> Canvas conversion for the Studio editor. */

import yaml from 'js-yaml'
import type { Node, Edge } from '@xyflow/react'
import { API_VERSION } from '@/lib/kinds'
import { capitalize, toResourceName, parseRef } from '@/lib/utils'
import { DATAFLOW_MARKER_END } from './defaults'

/* ------------------------------------------------------------------ */
/* Internal field lists (which spec fields to serialize per kind)      */
/* ------------------------------------------------------------------ */

const NODE_SPEC_FIELDS: Record<string, readonly string[]> = {
  agent: ['role', 'goal', 'backstory', 'llm', 'verbose', 'tools'],
  task: [
    'description',
    'expected_output',
    'agent',
    'context',
    'async_execution',
    'human_input',
    'output_file',
  ],
  tool: ['type', 'class_path', 'description', 'sandbox'],
  pii: ['type', 'pii_entities', 'pii_action', 'backend', 'model'],
}

/** Internal fields that should not appear in YAML spec output. */
const INTERNAL_DATA_KEYS = new Set(['name'])

/** Maps node type to resource kind for serialization. */
const NODE_KIND: Record<string, string> = {
  pii: 'Guardrail',
}

/** Maps internal node data keys to YAML spec field names. */
const FIELD_REMAP: Record<string, Record<string, string>> = {
  pii: { entities: 'pii_entities', action: 'pii_action' },
}

/* ------------------------------------------------------------------ */
/* Canvas -> YAML                                                      */
/* ------------------------------------------------------------------ */

export function canvasToYaml(nodes: Node[]): string {
  if (nodes.length === 0) return ''

  const documents: string[] = []

  for (const node of nodes) {
    const data = node.data
    const nodeType = node.type ?? 'unknown'
    const kind = NODE_KIND[nodeType] ?? capitalize(nodeType)
    const remap = FIELD_REMAP[nodeType] ?? {}

    const rawName =
      (data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? node.id
    const name = toResourceName(rawName)

    const fields = NODE_SPEC_FIELDS[nodeType] ?? []
    const spec: Record<string, unknown> = {}

    for (const f of fields) {
      // Look up the source key: the spec field might be a remapped name
      const sourceKey = Object.entries(remap).find(([, v]) => v === f)?.[0] ?? f
      if (data[sourceKey] !== undefined && data[sourceKey] !== '' && data[sourceKey] !== null) {
        spec[f] = data[sourceKey]
      }
    }

    // Collect remapped source keys to exclude them from extra fields
    const remapSourceKeys = new Set(Object.keys(remap))

    // Include any extra data fields not in the known list and not internal
    for (const [key, value] of Object.entries(data)) {
      if (
        !fields.includes(key) &&
        !INTERNAL_DATA_KEYS.has(key) &&
        !remapSourceKeys.has(key) &&
        value !== undefined &&
        value !== '' &&
        value !== null
      ) {
        spec[key] = value
      }
    }

    const doc = {
      apiVersion: API_VERSION,
      kind,
      metadata: { name },
      spec,
    }

    documents.push(yaml.dump(doc, { lineWidth: -1, noRefs: true, sortKeys: false }).trim())
  }

  return documents.join('\n---\n')
}

/* ------------------------------------------------------------------ */
/* YAML -> Canvas                                                      */
/* ------------------------------------------------------------------ */

interface ParsedDoc {
  apiVersion?: string
  kind?: string
  metadata?: { name?: string }
  spec?: Record<string, unknown>
}

export function yamlToCanvas(
  yamlStr: string,
  existingNodes?: Node[],
): { nodes: Node[]; edges: Edge[] } | null {
  let docs: unknown[]
  try {
    docs = yaml.loadAll(yamlStr)
  } catch {
    return null
  }

  if (!docs || docs.length === 0) return null

  // Build a map of existing node positions by resource name for stable layout
  const positionMap = new Map<string, { x: number; y: number }>()
  if (existingNodes) {
    for (const node of existingNodes) {
      const data = node.data
      const rawName =
        (data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? node.id
      positionMap.set(toResourceName(rawName), { ...node.position })
    }
  }

  const nodes: Node[] = []
  const edges: Edge[] = []
  const kindCounts: Record<string, number> = { agent: 0, task: 0, tool: 0, pii: 0 }

  for (const raw of docs) {
    if (!raw || typeof raw !== 'object') continue
    const doc = raw as ParsedDoc

    let kind = doc.kind?.toLowerCase()
    if (!kind) continue

    // Map Guardrail with type=pii to the pii node type
    const spec = doc.spec ?? {}
    if (kind === 'guardrail' && spec['type'] === 'pii') {
      kind = 'pii'
    }

    if (!['agent', 'task', 'tool', 'pii'].includes(kind)) continue

    const name = doc.metadata?.name ?? `${kind}-${crypto.randomUUID().slice(0, 8)}`

    // Build node data from spec, remapping Guardrail fields to node data fields
    const data: Record<string, unknown> = { ...spec }
    if (kind === 'pii') {
      // Remap pii_entities -> entities, pii_action -> action
      if (data['pii_entities'] !== undefined) {
        data['entities'] = data['pii_entities']
        delete data['pii_entities']
      }
      if (data['pii_action'] !== undefined) {
        data['action'] = data['pii_action']
        delete data['pii_action']
      }
      data['name'] = name
    }
    if (kind === 'task' || kind === 'tool') {
      data['name'] = name
    }

    // Compute position: reuse existing if available, otherwise auto-layout
    const count = kindCounts[kind] ?? 0
    kindCounts[kind] = count + 1

    const xOffsets: Record<string, number> = { agent: 80, task: 360, tool: 640, pii: 920 }
    const defaultPosition = {
      x: xOffsets[kind] ?? 80,
      y: 60 + count * 200,
    }
    const position = positionMap.get(name) ?? defaultPosition

    const nodeId = `${kind}-${name}`
    nodes.push({
      id: nodeId,
      type: kind,
      position,
      data,
    })
  }

  // Build edges from ref fields in task specs
  for (const node of nodes) {
    if (node.type !== 'task') continue
    const data = node.data

    // Agent assignment edge
    const agentRef = data['agent']
    if (typeof agentRef === 'string' && agentRef.startsWith('ref:')) {
      const agentName = parseRef(agentRef)
      const sourceId = `agent-${agentName}`
      if (nodes.some((n) => n.id === sourceId)) {
        edges.push({
          id: `edge-${sourceId}-${node.id}`,
          source: sourceId,
          target: node.id,
          type: 'dataflow',
          markerEnd: DATAFLOW_MARKER_END,
        })
      }
    }

    // Context edges (task-to-task)
    const context = data['context']
    if (Array.isArray(context)) {
      for (const ref of context) {
        if (typeof ref === 'string' && ref.startsWith('ref:')) {
          const taskName = parseRef(ref)
          const sourceId = `task-${taskName}`
          if (nodes.some((n) => n.id === sourceId)) {
            edges.push({
              id: `edge-${sourceId}-${node.id}`,
              source: sourceId,
              target: node.id,
              type: 'dataflow',
              markerEnd: DATAFLOW_MARKER_END,
            })
          }
        }
      }
    }
  }

  return { nodes, edges }
}
