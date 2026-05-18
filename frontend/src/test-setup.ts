import '@testing-library/jest-dom/vitest'

// Vitest's jsdom environment doesn't copy localStorage from jsdom's window to
// the global scope on Node.js 21+ because Node declares its own (unavailable)
// localStorage global, and vitest skips globals already present on the Node
// global. Force-copy it from the jsdom window so that application code using
// the bare `localStorage` identifier works correctly in tests.
if (
  typeof globalThis.localStorage === 'undefined' &&
  typeof window !== 'undefined' &&
  typeof window.localStorage !== 'undefined'
) {
  globalThis.localStorage = window.localStorage
} else if (typeof globalThis.localStorage === 'undefined') {
  // Fallback polyfill when jsdom's localStorage is also unavailable.
  const store: Record<string, string> = {}
  globalThis.localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      Object.keys(store).forEach((k) => delete store[k])
    },
    get length() {
      return Object.keys(store).length
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
}
