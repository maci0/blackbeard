/** Resource reference parsing and extraction utilities. */

import { PLURAL_TO_KIND } from '@/lib/kinds'

export interface ResourceRef {
  kindPlural: string
  kind: string
  name: string
}

/**
 * Extract the resource name from a ref string or path.
 * `ref:agents/researcher` → `researcher`; bare names pass through.
 */
export function parseRef(ref: string): string {
  const idx = ref.lastIndexOf('/')
  return idx >= 0 ? ref.slice(idx + 1) : ref
}

const REF_PATTERN = /^ref:([a-z][a-z0-9-]*)\/([a-z0-9][a-z0-9-]*)$/

export function extractRefs(spec: Record<string, unknown>): ResourceRef[] {
  const refs: ResourceRef[] = []
  const seen = new Set<string>()

  function walk(value: unknown): void {
    if (typeof value === 'string') {
      const match = value.match(REF_PATTERN)
      if (match) {
        const [, kindPlural, name] = match
        const key = `${kindPlural}/${name}`
        if (!seen.has(key)) {
          seen.add(key)
          refs.push({
            kindPlural: kindPlural!,
            kind: PLURAL_TO_KIND[kindPlural!] ?? kindPlural!,
            name: name!,
          })
        }
      }
      return
    }
    if (Array.isArray(value)) {
      for (const item of value) walk(item)
      return
    }
    if (value !== null && typeof value === 'object') {
      for (const v of Object.values(value as Record<string, unknown>)) walk(v)
    }
  }

  walk(spec)
  return refs
}
