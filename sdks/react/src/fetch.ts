import { BlackbeardApiError, formatErrorDetail } from './types'
import type { BlackbeardConfig } from './types'

function errorMeta(resp: Response): { requestId?: string; retryAfter?: number } {
  const requestId =
    resp.headers.get('x-request-id') ?? resp.headers.get('X-Request-Id') ?? undefined
  const retryRaw = resp.headers.get('retry-after') ?? resp.headers.get('Retry-After')
  let retryAfter: number | undefined
  if (retryRaw != null) {
    const n = Number.parseInt(retryRaw, 10)
    if (!Number.isNaN(n)) retryAfter = n
  }
  return { requestId: requestId || undefined, retryAfter }
}

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
      throw new BlackbeardApiError(0, `${method} ${path}: request timed out after ${timeout}ms`, undefined, { cause: err })
    }
    throw new BlackbeardApiError(
      0,
      `${method} ${path}: ${err instanceof Error ? err.message : 'network request failed'}`,
      undefined,
      { cause: err },
    )
  }

  if (!response.ok) {
    const fallback = response.statusText || `HTTP ${response.status}`
    const errorBody = (await response.json().catch(() => ({}))) as Record<string, unknown>
    const detail = formatErrorDetail(errorBody.detail, fallback)
    throw new BlackbeardApiError(response.status, detail, errorBody, errorMeta(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
