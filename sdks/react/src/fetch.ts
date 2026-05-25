import { BlackbeardApiError } from './types'
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

  const base = config.baseUrl ?? 'http://localhost:8000'
  const url = `${base.replace(/\/+$/, '')}${path}`
  const timeout = config.timeout ?? 30_000

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      signal: AbortSignal.timeout(timeout),
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  } catch (err) {
    if (err instanceof DOMException && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
      throw new BlackbeardApiError(0, `Request timed out after ${timeout}ms`)
    }
    const networkError = new BlackbeardApiError(
      0,
      err instanceof Error ? err.message : 'Network request failed',
    )
    networkError.cause = err
    throw networkError
  }

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => ({ detail: response.statusText }))) as Record<string, unknown>
    const detail = typeof errorBody.detail === 'string' ? errorBody.detail : response.statusText
    throw new BlackbeardApiError(response.status, detail, errorBody)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
