import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { resourceToYaml, parseYaml, serializeValue } from '../yaml'
import { KIND_TO_PLURAL } from '../kinds'

const NUM_RUNS = 100
const ALL_KINDS = Object.keys(KIND_TO_PLURAL)

describe('fuzz: resourceToYaml', () => {
  it('never crashes on any resource-shaped input', () => {
    fc.assert(
      fc.property(
        fc.record({
          apiVersion: fc.constant('blackbeard/v1'),
          kind: fc.constantFrom(...ALL_KINDS),
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

  it('output always contains kind and apiVersion for all kinds', () => {
    fc.assert(
      fc.property(
        fc.record({
          apiVersion: fc.constant('blackbeard/v1'),
          kind: fc.constantFrom(...ALL_KINDS),
          metadata: fc.record({
            name: fc.stringMatching(/^[a-z][a-z0-9-]{0,20}$/),
            project: fc.stringMatching(/^[a-z][a-z0-9-]{0,20}$/),
          }),
          spec: fc.dictionary(
            fc.stringMatching(/^[a-z][a-z0-9_]{0,10}$/),
            fc.oneof(fc.string({ maxLength: 50 }), fc.integer(), fc.boolean()),
            { minKeys: 1, maxKeys: 5 },
          ),
        }),
        (resource) => {
          const yaml = resourceToYaml(resource as never)
          expect(yaml).toContain('kind:')
          expect(yaml).toContain('apiVersion:')
          expect(yaml).toContain('project:')
          expect(yaml).toContain(resource.kind)
          expect(yaml).toContain(resource.metadata.name)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('round-trips: resourceToYaml output is parseable and preserves key fields', () => {
    fc.assert(
      fc.property(
        fc.record({
          apiVersion: fc.constant('blackbeard/v1'),
          kind: fc.constantFrom(...ALL_KINDS),
          metadata: fc.record({
            name: fc.stringMatching(/^[a-z][a-z0-9-]{1,15}$/),
            project: fc.stringMatching(/^[a-z][a-z0-9-]{1,15}$/),
          }),
          spec: fc.dictionary(
            fc.stringMatching(/^[a-z][a-z0-9_]{0,10}$/),
            fc.stringMatching(/^[a-z0-9 ]{1,20}$/),
            { minKeys: 1, maxKeys: 3 },
          ),
          version: fc.integer({ min: 1, max: 999 }),
        }),
        (resource) => {
          const yamlStr = resourceToYaml(resource as never)
          const parsed = parseYaml(yamlStr)
          expect(parsed).toHaveProperty('kind', resource.kind)
          expect(parsed).toHaveProperty('apiVersion', resource.apiVersion)
          expect(parsed).toHaveProperty('metadata')
          const meta = parsed.metadata as Record<string, unknown>
          expect(meta.name).toBe(resource.metadata.name)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: parseYaml', () => {
  it('returns object or throws YAMLException for any string input', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        try {
          const result = parseYaml(s)
          expect(typeof result).toBe('object')
          expect(result).not.toBeNull()
          expect(Array.isArray(result)).toBe(false)
        } catch (e: unknown) {
          expect((e as Error).name).toBe('YAMLException')
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('handles valid YAML-like inputs without crashing', () => {
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
          fc.stringMatching(/^[a-z]{1,10}$/).map((s) => `key: "${s}"`),
        ),
        (yaml) => {
          const result = parseYaml(yaml)
          expect(typeof result).toBe('object')
          expect(result).not.toBeNull()
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('fuzz: serializeValue', () => {
  const jsonValue: fc.Arbitrary<unknown> = fc.letrec((tie) => ({
    tree: fc.oneof(
      { depthSize: 'small' },
      fc.string({ maxLength: 50 }),
      fc.integer(),
      fc.boolean(),
      fc.constant(null),
      fc.array(tie('tree'), { maxLength: 3 }),
      fc.dictionary(fc.string({ minLength: 1, maxLength: 10 }), tie('tree'), { maxKeys: 3 }),
    ),
  })).tree

  it('never crashes on recursive structures', () => {
    fc.assert(
      fc.property(
        jsonValue,
        fc.integer({ min: 0, max: 5 }),
        (value, indent) => {
          const result = serializeValue(value, indent)
          expect(typeof result).toBe('string')
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  it('serializes multiline strings with block scalar indicator', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }).chain((a) =>
          fc.string({ minLength: 1, maxLength: 30 }).map((b) => `${a}\n${b}`),
        ),
        (multiline) => {
          const result = serializeValue(multiline, 0)
          expect(result).toContain('|')
        },
      ),
      { numRuns: 50 },
    )
  })
})
