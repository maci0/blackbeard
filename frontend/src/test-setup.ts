import '@testing-library/jest-dom/vitest'

// Vitest's jsdom environment may leave Node's experimental (or otherwise
// non-Storage) localStorage on globalThis. Application code and tests expect
// a full Storage API (getItem/setItem/clear/etc.). Prefer jsdom's window
// storage when present; otherwise install a simple in-memory polyfill.
function isStorage(value: unknown): value is Storage {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Storage).getItem === 'function' &&
    typeof (value as Storage).setItem === 'function' &&
    typeof (value as Storage).removeItem === 'function' &&
    typeof (value as Storage).clear === 'function'
  )
}

function memoryStorage(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = String(value)
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k]
    },
    get length() {
      return Object.keys(store).length
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
}

const fromWindow =
  typeof window !== 'undefined' && isStorage(window.localStorage) ? window.localStorage : null

if (!isStorage(globalThis.localStorage)) {
  globalThis.localStorage = fromWindow ?? memoryStorage()
}
