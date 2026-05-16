// Relative paths work in both dev (Vite proxy) and Docker (nginx proxy).
// Set VITE_API_BASE_URL only when hosting the frontend on a different origin.
const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: unknown,
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

class ApiClient {
  private apiKey: string = ''

  setApiKey(key: string) {
    this.apiKey = key
  }

  getApiKey(): string {
    return this.apiKey
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options

    let response: Response
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(this.apiKey ? { 'X-API-Key': this.apiKey } : {}),
          ...headers,
        },
        signal: AbortSignal.timeout(30_000),
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'TimeoutError') {
        throw new ApiError('Request timed out. Please try again.', 0, null)
      }
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError('Request was cancelled.', 0, null)
      }
      if (err instanceof TypeError) {
        throw new ApiError('Network error — check your connection and try again.', 0, null)
      }
      throw new ApiError('An unexpected error occurred.', 0, null)
    }

    if (!response.ok) {
      const error = (await response.json().catch(() => ({ detail: response.statusText }))) as {
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
      throw new ApiError(message, response.status, detail)
    }

    if (response.status === 204 || !response.headers.get('content-type')?.includes('json')) {
      return undefined as T
    }

    return response.json() as Promise<T>
  }

  get<T>(path: string) {
    return this.request<T>(path)
  }

  post<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: 'POST', body })
  }

  put<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: 'PUT', body })
  }

  patch<T>(path: string, body?: unknown) {
    return this.request<T>(path, { method: 'PATCH', ...(body !== undefined && { body }) })
  }

  delete<T>(path: string) {
    return this.request<T>(path, { method: 'DELETE' })
  }
}

export const api = new ApiClient()
