/** YAML serialization for studio nodes. */

import { API_VERSION } from '@/lib/kinds'
import { capitalize, toResourceName } from '@/lib/utils'
import { serializeValue } from '@/lib/yaml'

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
  flowStep: ['type', 'crew', 'function_path', 'listen_to'],
  pii: ['type', 'pii_entities', 'pii_action', 'backend', 'model'],
}

/** Maps node type to resource kind. Most types use capitalized node type,
 *  but PII nodes map to the Guardrail resource kind. */
const NODE_KIND: Record<string, string> = {
  pii: 'Guardrail',
}

/** Maps internal node data keys to YAML spec field names for types that
 *  differ between canvas representation and persisted resource spec. */
const FIELD_REMAP: Record<string, Record<string, string>> = {
  pii: { entities: 'pii_entities', action: 'pii_action' },
}

export function nodeToYaml(
  nodeType: string,
  nodeId: string,
  data: Record<string, unknown>,
): string {
  const kind = NODE_KIND[nodeType] ?? capitalize(nodeType)
  const rawName =
    (data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? nodeId
  const name = toResourceName(rawName)

  const fields = NODE_SPEC_FIELDS[nodeType] ?? []
  const remap = FIELD_REMAP[nodeType] ?? {}
  const spec: Record<string, unknown> = {}
  for (const f of fields) {
    // Look up the source key: the spec field might be a remapped name
    const sourceKey = Object.entries(remap).find(([, v]) => v === f)?.[0] ?? f
    if (data[sourceKey] !== undefined && data[sourceKey] !== '' && data[sourceKey] !== null) {
      spec[f] = data[sourceKey]
    }
  }

  const specYaml = serializeValue(spec, 1)

  return [
    `apiVersion: ${API_VERSION}`,
    `kind: ${kind}`,
    'metadata:',
    `  name: ${name}`,
    'spec:',
    ...(specYaml.startsWith('\n') ? [specYaml.slice(1)] : [specYaml]),
  ].join('\n')
}
