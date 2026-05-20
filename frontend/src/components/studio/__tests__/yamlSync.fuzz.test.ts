import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { canvasToYaml, yamlToCanvas } from '../yamlSync'

const NUM_RUNS = 200

describe('fuzz: canvasToYaml', () => {
  it('never throws on random node arrays', () => {
    const nodeArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 50 }),
      type: fc.constantFrom('agent', 'task', 'tool'),
      position: fc.record({ x: fc.integer(), y: fc.integer() }),
      data: fc.dictionary(fc.string({ maxLength: 20 }), fc.string({ maxLength: 100 })),
    })

    fc.assert(
      fc.property(fc.array(nodeArb, { maxLength: 20 }), (nodes) => {
        const result = canvasToYaml(nodes)
        expect(typeof result).toBe('string')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('returns empty string for empty nodes', () => {
    expect(canvasToYaml([])).toBe('')
  })

  it('output always contains kind for each node', () => {
    const nodeArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 50 }),
      type: fc.constantFrom('agent', 'task', 'tool'),
      position: fc.record({ x: fc.integer(), y: fc.integer() }),
      data: fc.record({
        name: fc.stringMatching(/^[a-z0-9]{1,20}$/),
        role: fc.stringMatching(/^[a-z ]{1,20}$/),
      }),
    })

    fc.assert(
      fc.property(fc.array(nodeArb, { minLength: 1, maxLength: 5 }), (nodes) => {
        const result = canvasToYaml(nodes)
        expect(result).toContain('kind:')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('output always contains apiVersion', () => {
    const nodeArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 20 }),
      type: fc.constantFrom('agent', 'task', 'tool'),
      position: fc.record({ x: fc.integer(), y: fc.integer() }),
      data: fc.record({
        name: fc.constant('test'),
      }),
    })

    fc.assert(
      fc.property(fc.array(nodeArb, { minLength: 1, maxLength: 3 }), (nodes) => {
        const result = canvasToYaml(nodes)
        expect(result).toContain('apiVersion: blackbeard/v1')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('multi-document separator count matches node count minus one', () => {
    const nodeArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 20 }),
      type: fc.constantFrom('agent', 'task', 'tool'),
      position: fc.record({ x: fc.integer(), y: fc.integer() }),
      data: fc.record({
        name: fc.constant('node'),
      }),
    })

    fc.assert(
      fc.property(fc.array(nodeArb, { minLength: 2, maxLength: 8 }), (nodes) => {
        const result = canvasToYaml(nodes)
        const separatorCount = result.split('---').length - 1
        expect(separatorCount).toBe(nodes.length - 1)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: yamlToCanvas', () => {
  it('handles random YAML strings without crashing', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 5000 }), (yaml) => {
        const result = yamlToCanvas(yaml)
        if (result !== null) {
          expect(Array.isArray(result.nodes)).toBe(true)
          expect(Array.isArray(result.edges)).toBe(true)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('null or valid structure on random input', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 2000 }), (yaml) => {
        const result = yamlToCanvas(yaml)
        if (result !== null) {
          expect(Array.isArray(result.nodes)).toBe(true)
          expect(Array.isArray(result.edges)).toBe(true)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('round-trips valid canvas nodes through YAML', () => {
    const nodeArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 20 }),
      type: fc.constantFrom('agent', 'task', 'tool'),
      position: fc.record({
        x: fc.integer({ min: 0, max: 2000 }),
        y: fc.integer({ min: 0, max: 2000 }),
      }),
      data: fc.record({
        name: fc.stringMatching(/^[a-z0-9]{1,15}$/),
        role: fc.stringMatching(/^[a-z ]{1,15}$/),
      }),
    })

    fc.assert(
      fc.property(fc.array(nodeArb, { minLength: 1, maxLength: 5 }), (nodes) => {
        const yaml = canvasToYaml(nodes)
        const result = yamlToCanvas(yaml)

        // If we produced valid YAML, it should parse back with same node count
        if (yaml.length > 0) {
          expect(result).not.toBeNull()
          if (result) {
            expect(result.nodes.length).toBe(nodes.length)
          }
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('never produces edges referencing non-existent nodes', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 3000 }), (yaml) => {
        const result = yamlToCanvas(yaml)
        if (result !== null) {
          const nodeIds = new Set(result.nodes.map((n) => n.id))
          for (const edge of result.edges) {
            expect(nodeIds.has(edge.source)).toBe(true)
            expect(nodeIds.has(edge.target)).toBe(true)
          }
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })
})
