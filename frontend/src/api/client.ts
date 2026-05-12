// Use relative paths — Vite dev server proxies /api to the backend.
// In production builds, set VITE_API_BASE_URL to the backend origin.
const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

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

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options

    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(this.apiKey ? { 'X-API-Key': this.apiKey } : {}),
        ...headers,
      },
      signal: AbortSignal.timeout(30_000),
      ...(body ? { body: JSON.stringify(body) } : {}),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    if (response.status === 204 || !response.headers.get('content-type')?.includes('json')) {
      return undefined as T
    }

    return response.json()
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

  delete<T>(path: string) {
    return this.request<T>(path, { method: 'DELETE' })
  }
}

export const api = new ApiClient()
