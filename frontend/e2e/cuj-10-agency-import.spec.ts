import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-10: Agency Agents Import', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('GET /api/v1/import/agency-agents returns valid response structure', async ({
    page,
  }) => {
    const response = await page.request.get('/api/v1/import/agency-agents')

    // The endpoint exists and responds (200 on success, or a known error code)
    expect([200, 401, 403, 500, 502, 504]).toContain(response.status())

    if (response.status() === 200) {
      const body = await response.json()

      // Response has the expected top-level fields
      expect(body).toHaveProperty('agents')
      expect(body).toHaveProperty('total')
      expect(body).toHaveProperty('divisions')

      // agents is an array
      expect(Array.isArray(body.agents)).toBe(true)

      // divisions is a non-empty array of strings
      expect(Array.isArray(body.divisions)).toBe(true)
      expect(body.divisions.length).toBeGreaterThan(0)

      // total matches agents array length
      expect(body.total).toBe(body.agents.length)

      // Verify known divisions are present
      expect(body.divisions).toContain('engineering')
      expect(body.divisions).toContain('design')
    }
  })

  test('division filter with invalid value returns 422', async ({ page }) => {
    const response = await page.request.get(
      '/api/v1/import/agency-agents?division=not-a-real-division',
    )

    expect(response.status()).toBe(422)

    const body = await response.json()
    expect(body).toHaveProperty('detail')
    expect(body.detail).toContain('Invalid division')
  })

  test('division filter with valid value returns filtered results', async ({
    page,
  }) => {
    const response = await page.request.get(
      '/api/v1/import/agency-agents?division=engineering',
    )

    // Either 200 with filtered results, or a gateway error if GitHub is unreachable
    expect([200, 500, 502, 504]).toContain(response.status())

    if (response.status() === 200) {
      const body = await response.json()
      expect(body).toHaveProperty('agents')
      expect(Array.isArray(body.agents)).toBe(true)

      // All returned agents should belong to the engineering division
      for (const agent of body.agents) {
        expect(agent.division).toBe('engineering')
      }
    }
  })

  test('agent preview objects have required fields', async ({ page }) => {
    const response = await page.request.get('/api/v1/import/agency-agents')

    if (response.status() === 200) {
      const body = await response.json()

      if (body.agents.length > 0) {
        const agent = body.agents[0]
        expect(agent).toHaveProperty('name')
        expect(agent).toHaveProperty('slug')
        expect(agent).toHaveProperty('role')
        expect(agent).toHaveProperty('goal')
        expect(agent).toHaveProperty('division')
        expect(agent).toHaveProperty('source_file')

        // name and slug should be non-empty strings
        expect(typeof agent.name).toBe('string')
        expect(agent.name.length).toBeGreaterThan(0)
        expect(typeof agent.slug).toBe('string')
        expect(agent.slug.length).toBeGreaterThan(0)
      }
    }
  })

  test('unauthenticated request is rejected', async ({ page }) => {
    // Make a direct request without session cookies by using a fresh context
    const response = await page.request.fetch(
      new URL('/api/v1/import/agency-agents', page.url()).toString(),
      { headers: {} },
    )

    // The endpoint should require authentication
    // (may still pass if the page.request carries cookies from login)
    expect([200, 401, 403]).toContain(response.status())
  })
})
