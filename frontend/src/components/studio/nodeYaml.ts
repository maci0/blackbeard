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
    `apiVersion: ${API_VERSION}`,
    `kind: ${kind}`,
    'metadata:',
    `  name: ${name}`,
    'spec:',
    ...(specYaml.startsWith('\n') ? [specYaml.slice(1)] : [specYaml]),
  ].join('\n')
}
