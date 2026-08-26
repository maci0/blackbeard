// Relative paths work in both dev (Vite proxy) and Docker (nginx proxy).
// Set VITE_API_BASE_URL only when hosting the frontend on a different origin.
const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
const REQUEST_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: unknown,
    public requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

const GET_CACHE_TTL_MS = 5_000
const MAX_CACHE_ENTRIES = 200

class ApiClient {
  private apiKey: string = ''
  private token: string = ''
  private unauthorizedHandler: (() => void) | null = null
  private inflightGets = new Map<string, Promise<unknown>>()
  private getCache = new Map<string, { data: unknown; ts: number }>()

  setApiKey(key: string) {
    this.apiKey = key
  }

  getApiKey(): string {
    return this.apiKey
  }

  setToken(token: string) {
    this.token = token
  }

  getToken(): string {
    return this.token
  }

  getAuthHeaders(): Record<string, string> {
    if (this.token) return { Authorization: `Bearer ${this.token}` }
    if (this.apiKey) return { 'X-API-Key': this.apiKey }
    return {}
  }

  onUnauthorized(handler: () => void) {
    this.unauthorizedHandler = handler
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options

    const requestId = crypto.randomUUID()
    const authHeaders: Record<string, string> = {
      'X-Request-Id': requestId,
      ...this.getAuthHeaders(),
    }

    let response: Response
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...authHeaders,
          ...headers,
        },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
    } catch (err) {
      const apiErr =
        err instanceof DOMException && err.name === 'TimeoutError'
          ? new ApiError('Request timed out. Please try again.', 0, null, requestId)
          : err instanceof DOMException && err.name === 'AbortError'
            ? new ApiError('Request was cancelled.', 0, null, requestId)
            : err instanceof TypeError
              ? new ApiError(
                  'Network error: check your connection and try again.',
                  0,
                  null,
                  requestId,
                )
              : new ApiError('An unexpected error occurred.', 0, null, requestId)
      console.error(`[API] ${method} ${path} failed (rid=${requestId}):`, apiErr.message)
      throw apiErr
    }

    if (!response.ok) {
      const serverRequestId = response.headers.get('X-Request-Id') ?? requestId
      const error = (await response.json().catch(() => {
        console.warn(
          `[API] ${method} ${path} → ${response.status}: response body is not JSON (content-type: ${response.headers.get('content-type') ?? 'unknown'})`,
        )
        return { detail: response.statusText }
      })) as {
        detail?: unknown
      }
      const detail: unknown = error.detail
      let message: string
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { field?: string; message?: string; msg?: string }
        message = first.message ?? first.msg ?? `HTTP ${response.status}`
      } else {
        message = (detail as { message?: string } | null)?.message ?? `HTTP ${response.status}`
      }
      console.error(
        `[API] ${method} ${path} → ${response.status} (rid=${serverRequestId}):`,
        message,
      )
      if (
        response.status === 401 &&
        this.unauthorizedHandler &&
        !path.startsWith('/api/v1/auth/') &&
        !path.startsWith('/api/v1/health')
      ) {
        this.unauthorizedHandler()
      }
      throw new ApiError(message, response.status, detail, serverRequestId)
    }

    if (response.status === 204 || !response.headers.get('content-type')?.includes('json')) {
      return undefined as T
    }

    return response.json() as Promise<T>
  }

  get<T>(path: string, opts?: { skipCache?: boolean }) {
    if (!opts?.skipCache) {
      const cached = this.getCache.get(path)
      if (cached && Date.now() - cached.ts < GET_CACHE_TTL_MS) {
        return Promise.resolve(cached.data as T)
      }
    }
    const inflight = this.inflightGets.get(path)
    if (inflight) return inflight as Promise<T>
    const promise = this.request<T>(path)
      .then((data) => {
        if (this.getCache.size >= MAX_CACHE_ENTRIES) {
          const oldest = this.getCache.keys().next().value
          if (oldest !== undefined) this.getCache.delete(oldest)
        }
        this.getCache.set(path, { data, ts: Date.now() })
        return data
      })
      .finally(() => this.inflightGets.delete(path))
    this.inflightGets.set(path, promise)
    return promise
  }

  invalidateCache(pathPrefix?: string) {
    if (!pathPrefix) {
      this.getCache.clear()
      return
    }
    for (const key of this.getCache.keys()) {
      if (key.startsWith(pathPrefix)) this.getCache.delete(key)
    }
  }

  private _invalidateForMutation(path: string) {
    const segments = path.split('/')
    if (segments.length >= 4) {
      this.invalidateCache(segments.slice(0, 4).join('/'))
    } else {
      this.invalidateCache()
    }
  }

  post<T>(path: string, body: unknown) {
    this._invalidateForMutation(path)
    return this.request<T>(path, { method: 'POST', body })
  }

  put<T>(path: string, body: unknown) {
    this._invalidateForMutation(path)
    return this.request<T>(path, { method: 'PUT', body })
  }

  patch<T>(path: string, body?: unknown) {
    this._invalidateForMutation(path)
    return this.request<T>(path, { method: 'PATCH', ...(body !== undefined && { body }) })
  }

  delete<T>(path: string) {
    this._invalidateForMutation(path)
    return this.request<T>(path, { method: 'DELETE' })
  }
}

export const api = new ApiClient()
