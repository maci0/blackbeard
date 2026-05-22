import { describe, it, expect } from 'vitest'
import type { Node } from '@xyflow/react'
import { canvasToYaml, yamlToCanvas } from '../yamlSync'

describe('canvasToYaml', () => {
  it('converts agent nodes to YAML', () => {
    const nodes: Node[] = [
      {
        id: 'agent-researcher',
        type: 'agent',
        position: { x: 80, y: 60 },
        data: { role: 'Researcher', goal: 'Find information', backstory: 'Expert researcher' },
      },
    ]

    const yaml = canvasToYaml(nodes)

    expect(yaml).toContain('kind: Agent')
    expect(yaml).toContain('name: researcher')
    expect(yaml).toContain('role: Researcher')
    expect(yaml).toContain('goal: Find information')
    expect(yaml).toContain('backstory: Expert researcher')
  })

  it('converts task nodes to YAML', () => {
    const nodes: Node[] = [
      {
        id: 'task-research',
        type: 'task',
        position: { x: 360, y: 60 },
        data: {
          name: 'research-task',
          description: 'Research the topic',
          expected_output: 'A summary',
          agent: 'ref:agents/researcher',
        },
      },
    ]

    const yaml = canvasToYaml(nodes)

    expect(yaml).toContain('kind: Task')
    expect(yaml).toContain('description: Research the topic')
    expect(yaml).toContain('expected_output: A summary')
    expect(yaml).toContain('agent: ref:agents/researcher')
  })

  it('handles empty nodes array', () => {
    expect(canvasToYaml([])).toBe('')
  })

  it('produces multi-document YAML for multiple nodes', () => {
    const nodes: Node[] = [
      {
        id: 'agent-a',
        type: 'agent',
        position: { x: 0, y: 0 },
        data: { role: 'Agent A', goal: 'Goal A' },
      },
      {
        id: 'agent-b',
        type: 'agent',
        position: { x: 0, y: 200 },
        data: { role: 'Agent B', goal: 'Goal B' },
      },
    ]

    const yaml = canvasToYaml(nodes)

    // Multi-doc separator
    expect(yaml).toContain('---')
    expect(yaml.split('---').length).toBe(2)
  })

  it('includes apiVersion in output', () => {
    const nodes: Node[] = [
      {
        id: 'tool-1',
        type: 'tool',
        position: { x: 0, y: 0 },
        data: { name: 'web-search', type: 'python', class_path: 'tools.WebSearch' },
      },
    ]

    const yaml = canvasToYaml(nodes)

    expect(yaml).toContain('apiVersion: blackbeard/v1')
    expect(yaml).toContain('kind: Tool')
    expect(yaml).toContain('name: web-search')
  })

  it('skips empty/null/undefined spec fields', () => {
    const nodes: Node[] = [
      {
        id: 'agent-sparse',
        type: 'agent',
        position: { x: 0, y: 0 },
        data: { role: 'Sparse', goal: '', backstory: null, llm: undefined },
      },
    ]

    const yaml = canvasToYaml(nodes)

    expect(yaml).toContain('role: Sparse')
    expect(yaml).toContain('kind: Agent')
    expect(yaml).toContain('apiVersion: blackbeard/v1')
    expect(yaml).not.toContain('goal:')
    expect(yaml).not.toContain('backstory:')
    expect(yaml).not.toContain('llm:')
  })

  it('derives resource name from role for agents', () => {
    const nodes: Node[] = [
      {
        id: 'agent-fancy',
        type: 'agent',
        position: { x: 0, y: 0 },
        data: { role: 'Lead Researcher' },
      },
    ]

    const yaml = canvasToYaml(nodes)

    expect(yaml).toContain('name: lead-researcher')
  })
})

describe('yamlToCanvas', () => {
  it('parses YAML back to nodes', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find info
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    expect(result!.nodes).toHaveLength(1)
    const node = result!.nodes[0]!
    expect(node.type).toBe('agent')
    expect(node.id).toBe('agent-researcher')
    expect(node.data['role']).toBe('Researcher')
    expect(node.data['goal']).toBe('Find info')
  })

  it('returns null for YAML that parses to non-object scalars only', () => {
    // yaml.loadAll('just a string') returns a scalar, not an object with kind/metadata,
    // so yamlToCanvas produces no valid nodes → { nodes: [], edges: [] }.
    // Truly malformed YAML (tab indentation errors) triggers the catch → null.
    const result = yamlToCanvas('\t- :\n\t\t:\t-')

    expect(result).toBeNull()
  })

  it('returns null for empty YAML', () => {
    const result = yamlToCanvas('')

    expect(result).toBeNull()
  })

  it('preserves existing positions when re-parsing', () => {
    const existingNodes: Node[] = [
      {
        id: 'agent-researcher',
        type: 'agent',
        position: { x: 500, y: 300 },
        data: { role: 'Researcher' },
      },
    ]

    const yamlStr = `
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Updated goal
`
    const result = yamlToCanvas(yamlStr, existingNodes)

    expect(result).not.toBeNull()
    expect(result!.nodes[0]!.position).toEqual({ x: 500, y: 300 })
  })

  it('creates edges from agent refs in tasks', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
---
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: research-task
spec:
  description: Do research
  expected_output: A report
  agent: "ref:agents/researcher"
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    expect(result!.nodes).toHaveLength(2)
    expect(result!.edges).toHaveLength(1)
    const edge = result!.edges[0]!
    expect(edge.source).toBe('agent-researcher')
    expect(edge.target).toBe('task-research-task')
  })

  it('creates edges from context refs between tasks', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: task-a
spec:
  description: First task
  expected_output: Output A
---
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: task-b
spec:
  description: Second task
  expected_output: Output B
  context:
    - "ref:tasks/task-a"
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    expect(result!.edges).toHaveLength(1)
    const edge = result!.edges[0]!
    expect(edge.source).toBe('task-task-a')
    expect(edge.target).toBe('task-task-b')
  })

  it('ignores unknown kinds', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Crew
metadata:
  name: my-crew
spec:
  agents: []
---
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    // Only Agent should be parsed, Crew is ignored
    expect(result!.nodes).toHaveLength(1)
    expect(result!.nodes[0]!.type).toBe('agent')
  })

  it('does not create edges to non-existent nodes', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: lonely-task
spec:
  description: A task
  expected_output: Output
  agent: "ref:agents/ghost"
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    expect(result!.nodes).toHaveLength(1)
    // No edge because agent-ghost does not exist
    expect(result!.edges).toHaveLength(0)
  })

  it('assigns default positions based on kind', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: a1
spec:
  role: A1
---
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: t1
spec:
  description: Task 1
  expected_output: Output
---
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: tool1
spec:
  type: python
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    // Each kind gets a different x offset
    const agentNode = result!.nodes.find((n) => n.type === 'agent')!
    const taskNode = result!.nodes.find((n) => n.type === 'task')!
    const toolNode = result!.nodes.find((n) => n.type === 'tool')!
    expect(agentNode.position.x).toBe(80)
    expect(taskNode.position.x).toBe(360)
    expect(toolNode.position.x).toBe(640)
  })

  it('sets name in data for tasks and tools', () => {
    const yamlStr = `
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: my-task
spec:
  description: Test
  expected_output: Output
---
apiVersion: blackbeard/v1
kind: Tool
metadata:
  name: my-tool
spec:
  type: python
`
    const result = yamlToCanvas(yamlStr)

    expect(result).not.toBeNull()
    const taskNode = result!.nodes.find((n) => n.type === 'task')!
    const toolNode = result!.nodes.find((n) => n.type === 'tool')!
    expect(taskNode.data['name']).toBe('my-task')
    expect(toolNode.data['name']).toBe('my-tool')
  })
})
