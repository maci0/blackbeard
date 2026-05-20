import type { BlackbeardConfig } from './types'

/** Minimal typed fetch wrapper for the Blackbeard API. */
export async function apiFetch<T>(
  config: BlackbeardConfig,
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { method = 'GET', body } = options
  const headers: Record<string, string> = {}

  if (config.token) {
    headers['Authorization'] = `Bearer ${config.token}`
  } else if (config.apiKey) {
    headers['X-API-Key'] = config.apiKey
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const url = `${config.baseUrl.replace(/\/+$/, '')}${path}`

  const response = await fetch(url, {
    method,
    headers,
    signal: AbortSignal.timeout(30_000),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`Blackbeard API ${method} ${path}: ${response.status} ${detail}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}
