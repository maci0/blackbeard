import { createContext, useContext } from 'react'
import type { BlackbeardConfig } from './types'

const BlackbeardContext = createContext<BlackbeardConfig | null>(null)

export interface BlackbeardProviderProps extends BlackbeardConfig {
  children: React.ReactNode
}

/**
 * Provides Blackbeard API configuration to all child components.
 *
 * Wrap your application (or widget subtree) with this provider and pass
 * the API `baseUrl` plus an `apiKey` or `token` for authentication.
 *
 * ```tsx
 * <BlackbeardProvider baseUrl="https://bb.example.com" apiKey="sk-...">
 *   <CrewViewer crewName="my-crew" />
 * </BlackbeardProvider>
 * ```
 */
export function BlackbeardProvider({ baseUrl, apiKey, token, children }: BlackbeardProviderProps) {
  return (
    <BlackbeardContext.Provider value={{ baseUrl, apiKey, token }}>
      {children}
    </BlackbeardContext.Provider>
  )
}

/**
 * Returns the Blackbeard API configuration from the nearest provider.
 * Throws if used outside a `<BlackbeardProvider>`.
 */
export function useBlackbeard(): BlackbeardConfig {
  const ctx = useContext(BlackbeardContext)
  if (!ctx) {
    throw new Error('useBlackbeard must be used within a <BlackbeardProvider>')
  }
  return ctx
}
