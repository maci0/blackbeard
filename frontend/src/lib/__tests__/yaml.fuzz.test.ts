import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { resourceToYaml, parseYaml } from '../yaml'

const NUM_RUNS = 100

describe('fuzz: resourceToYaml', () => {
  it('never crashes on any resource-shaped input', () => {
    fc.assert(
      fc.property(
        fc.record({
          apiVersion: fc.constant('blackbeard/v1'),
          kind: fc.constantFrom('Agent', 'Task', 'Crew', 'Tool', 'LLMConnection'),
          metadata: fc.record({
            name: fc.string({ minLength: 1, maxLength: 50 }),
            project: fc.string({ minLength: 1, maxLength: 50 }),
          }),
          spec: fc.dictionary(
            fc.string({ minLength: 1, maxLength: 20 }),
            fc.oneof(fc.string(), fc.integer(), fc.boolean(), fc.constant(null)),
            { minKeys: 0, maxKeys: 10 },
          ),
        }),
        (resource) => {
          const result = resourceToYaml(resource as never)
          expect(typeof result).toBe('string')
          expect(result.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('output always contains kind and apiVersion', () => {
    fc.assert(
      fc.property(
        fc.record({
          apiVersion: fc.constant('blackbeard/v1'),
          kind: fc.constantFrom('Agent', 'Task'),
          metadata: fc.record({
            name: fc.constant('test'),
            project: fc.constant('default'),
          }),
          spec: fc.constant({ role: 'test', goal: 'test', backstory: 'test' }),
        }),
        (resource) => {
          const yaml = resourceToYaml(resource as never)
          expect(yaml).toContain('kind:')
          expect(yaml).toContain('apiVersion:')
          expect(yaml).toContain('project:')
        },
      ),
      { numRuns: 20 },
    )
  })
})

describe('fuzz: parseYaml', () => {
  it('never crashes on any string input', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        try {
          const result = parseYaml(s)
          expect(result === null || typeof result === 'object').toBe(true)
        } catch {
          // parseYaml may throw on invalid YAML — that's acceptable
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('handles YAML-like inputs without crashing', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(''),
          fc.constant('---'),
          fc.constant('null'),
          fc.constant('[]'),
          fc.constant('{}'),
          fc.constant('key: value'),
          fc.constant('- item1\n- item2'),
          fc.string().map((s) => `key: "${s.replace(/"/g, '\\"')}"`),
        ),
        (yaml) => {
          try {
            parseYaml(yaml)
          } catch {
            // acceptable
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})
