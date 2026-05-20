/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

// We need a fresh module for each test to reset private state (token, apiKey).
// Re-import after resetModules().
let api: typeof import('../client').api
let ApiError: typeof import('../client').ApiError

function mockResponse(
  status: number,
  body: unknown = null,
  headers: Record<string, string> = {},
): Response {
  const contentType = body !== null ? 'application/json' : undefined
  const headerMap = new Headers(headers)
  if (contentType) headerMap.set('content-type', contentType)
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `HTTP ${status}`,
    headers: headerMap,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response
}

describe('ApiClient', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn())
    // crypto.randomUUID is needed by the client
    if (!globalThis.crypto?.randomUUID) {
      vi.stubGlobal('crypto', { randomUUID: () => '00000000-0000-0000-0000-000000000000' })
    }
    // Fresh import to reset internal state
    vi.resetModules()
    const mod = await import('../client')
    api = mod.api
    ApiError = mod.ApiError
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('setToken / getToken', () => {
    it('stores and retrieves token', () => {
      api.setToken('my-token')
      expect(api.getToken()).toBe('my-token')
    })

    it('returns empty string when no token set', () => {
      expect(api.getToken()).toBe('')
    })
  })

  describe('setApiKey / getApiKey', () => {
    it('stores and retrieves API key', () => {
      api.setApiKey('key-abc')
      expect(api.getApiKey()).toBe('key-abc')
    })

    it('returns empty string when no API key set', () => {
      expect(api.getApiKey()).toBe('')
    })
  })

  describe('request()', () => {
    it('sends Authorization header when token is set', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { ok: true }))

      api.setToken('bearer-token-123')
      await api.get('/api/v1/test')

      expect(fetchMock).toHaveBeenCalledTimes(1)
      const [, init] = fetchMock.mock.calls[0]!
      const headers = init?.headers as Record<string, string>
      expect(headers['Authorization']).toBe('Bearer bearer-token-123')
    })

    it('sends X-API-Key header when only API key is set', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { ok: true }))

      api.setApiKey('api-key-456')
      await api.get('/api/v1/test')

      const [, init] = fetchMock.mock.calls[0]!
      const headers = init?.headers as Record<string, string>
      expect(headers['X-API-Key']).toBe('api-key-456')
      expect(headers['Authorization']).toBeUndefined()
    })

    it('token takes precedence over API key in headers', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { ok: true }))

      api.setToken('my-token')
      api.setApiKey('my-key')
      await api.get('/api/v1/test')

      const [, init] = fetchMock.mock.calls[0]!
      const headers = init?.headers as Record<string, string>
      expect(headers['Authorization']).toBe('Bearer my-token')
      expect(headers['X-API-Key']).toBeUndefined()
    })

    it('sends X-Request-Id header', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { ok: true }))

      await api.get('/api/v1/test')

      const [, init] = fetchMock.mock.calls[0]!
      const headers = init?.headers as Record<string, string>
      expect(headers['X-Request-Id']).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
      )
    })

    it('handles 204 No Content', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(204))

      const result = await api.delete('/api/v1/resources/test')

      expect(result).toBeUndefined()
    })

    it('handles non-JSON response with ok status', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      const response = {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: new Headers({ 'content-type': 'text/plain' }),
        json: () => Promise.resolve(null),
      } as unknown as Response
      fetchMock.mockResolvedValueOnce(response)

      const result = await api.get('/api/v1/health')

      expect(result).toBeUndefined()
    })

    it('throws ApiError with correct status and message on 401', async () => {
      expect.assertions(6)
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(401, { detail: 'Invalid credentials' }))

      await expect(api.get('/api/v1/protected')).rejects.toThrow(ApiError)

      try {
        fetchMock.mockResolvedValueOnce(mockResponse(401, { detail: 'Invalid credentials' }))
        await api.get('/api/v1/protected')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(401)
        expect(apiErr.message).toBe('Invalid credentials')
        expect(apiErr.detail).toBe('Invalid credentials')
        expect(apiErr.requestId).toBeDefined()
      }
    })

    it('throws ApiError with array detail (validation error)', async () => {
      expect.assertions(4)
      const fetchMock = vi.mocked(globalThis.fetch)
      const detail = [
        { field: 'name', message: 'Name is required' },
        { field: 'spec', message: 'Spec must be an object' },
      ]
      fetchMock.mockResolvedValueOnce(mockResponse(422, { detail }))

      try {
        await api.post('/api/v1/agents', {})
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(422)
        expect(apiErr.message).toBe('Name is required')
        expect(apiErr.detail).toEqual(detail)
      }
    })

    it('handles array detail with msg field (FastAPI style)', async () => {
      expect.assertions(1)
      const fetchMock = vi.mocked(globalThis.fetch)
      const detail = [{ loc: ['body', 'name'], msg: 'field required', type: 'missing' }]
      fetchMock.mockResolvedValueOnce(mockResponse(422, { detail }))

      try {
        await api.post('/api/v1/agents', {})
      } catch (err) {
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.message).toBe('field required')
      }
    })

    it('falls back to HTTP status code in message when detail is unparseable', async () => {
      expect.assertions(2)
      const fetchMock = vi.mocked(globalThis.fetch)
      // Non-JSON error body
      const response = {
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.reject(new Error('not json')),
      } as unknown as Response
      fetchMock.mockResolvedValueOnce(response)

      try {
        await api.get('/api/v1/broken')
      } catch (err) {
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(500)
        expect(apiErr.message).toBe('Internal Server Error')
      }
    })

    it('throws ApiError on network error (TypeError)', async () => {
      expect.assertions(3)
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

      try {
        await api.get('/api/v1/test')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(0)
        expect(apiErr.message).toContain('Network error')
      }
    })

    it('throws ApiError on timeout (DOMException TimeoutError)', async () => {
      expect.assertions(3)
      const fetchMock = vi.mocked(globalThis.fetch)
      const timeoutError = new DOMException('The operation was aborted.', 'TimeoutError')
      fetchMock.mockRejectedValueOnce(timeoutError)

      try {
        await api.get('/api/v1/slow')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(0)
        expect(apiErr.message).toContain('timed out')
      }
    })

    it('throws ApiError on abort (DOMException AbortError)', async () => {
      expect.assertions(3)
      const fetchMock = vi.mocked(globalThis.fetch)
      const abortError = new DOMException('The operation was aborted.', 'AbortError')
      fetchMock.mockRejectedValueOnce(abortError)

      try {
        await api.get('/api/v1/cancelled')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.status).toBe(0)
        expect(apiErr.message).toContain('cancelled')
      }
    })

    it('sends Content-Type and body for POST requests', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(201, { id: '1' }))

      await api.post('/api/v1/agents', { name: 'test' })

      const [, init] = fetchMock.mock.calls[0]!
      expect(init?.method).toBe('POST')
      const headers = init?.headers as Record<string, string>
      expect(headers['Content-Type']).toBe('application/json')
      expect(init?.body).toBe(JSON.stringify({ name: 'test' }))
    })

    it('does not send Content-Type for GET requests', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, []))

      await api.get('/api/v1/agents')

      const [, init] = fetchMock.mock.calls[0]!
      const headers = init?.headers as Record<string, string>
      expect(headers['Content-Type']).toBeUndefined()
    })

    it('uses server X-Request-Id from error response when available', async () => {
      expect.assertions(1)
      const fetchMock = vi.mocked(globalThis.fetch)
      const response = {
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        headers: new Headers({
          'content-type': 'application/json',
          'X-Request-Id': 'server-rid-789',
        }),
        json: () => Promise.resolve({ detail: 'Bad input' }),
      } as unknown as Response
      fetchMock.mockResolvedValueOnce(response)

      try {
        await api.get('/api/v1/test')
      } catch (err) {
        const apiErr = err as InstanceType<typeof ApiError>
        expect(apiErr.requestId).toBe('server-rid-789')
      }
    })
  })

  describe('convenience methods', () => {
    it('put() sends PUT method', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { updated: true }))

      await api.put('/api/v1/agents/test', { spec: {} })

      const [, init] = fetchMock.mock.calls[0]!
      expect(init?.method).toBe('PUT')
    })

    it('patch() sends PATCH method', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { patched: true }))

      await api.patch('/api/v1/agents/test', { spec: {} })

      const [, init] = fetchMock.mock.calls[0]!
      expect(init?.method).toBe('PATCH')
    })

    it('patch() works without body', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(200, { patched: true }))

      await api.patch('/api/v1/executions/123/cancel')

      const [, init] = fetchMock.mock.calls[0]!
      expect(init?.method).toBe('PATCH')
      expect(init?.body).toBeUndefined()
    })

    it('delete() sends DELETE method', async () => {
      const fetchMock = vi.mocked(globalThis.fetch)
      fetchMock.mockResolvedValueOnce(mockResponse(204))

      await api.delete('/api/v1/agents/test')

      const [, init] = fetchMock.mock.calls[0]!
      expect(init?.method).toBe('DELETE')
    })
  })
})
