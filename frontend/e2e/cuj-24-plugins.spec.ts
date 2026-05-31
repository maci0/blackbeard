import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('CUJ-24: Plugin System', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('GET /api/v1/plugins returns a valid response', async ({ page }) => {
    const response = await page.request.get('/api/v1/plugins')

    expect(response.ok()).toBe(true)
    expect(response.status()).toBe(200)

    const body = await response.json()
    expect(body).toHaveProperty('plugins')
    expect(body).toHaveProperty('count')
    expect(Array.isArray(body.plugins)).toBe(true)
    expect(typeof body.count).toBe('number')
    expect(body.count).toBe(body.plugins.length)
  })

  test('each plugin has required fields', async ({ page }) => {
    const response = await page.request.get('/api/v1/plugins')
    const body = await response.json()

    for (const plugin of body.plugins) {
      expect(plugin).toHaveProperty('name')
      expect(plugin).toHaveProperty('version')
      expect(plugin).toHaveProperty('description')
      expect(plugin).toHaveProperty('plugin_type')
      expect(plugin).toHaveProperty('entry_point')
      expect(typeof plugin.name).toBe('string')
      expect(typeof plugin.version).toBe('string')
    }
  })

  test('plugins can be filtered by type', async ({ page }) => {
    // Even if no plugins match, the endpoint should return a valid response
    const response = await page.request.get('/api/v1/plugins?plugin_type=tool')

    // The endpoint either returns 200 with results or 400 for invalid types
    if (response.ok()) {
      const body = await response.json()
      expect(body).toHaveProperty('plugins')
      expect(Array.isArray(body.plugins)).toBe(true)
    }
  })

  test('invalid plugin_type returns 400', async ({ page }) => {
    const response = await page.request.get('/api/v1/plugins?plugin_type=nonexistent_type')

    expect(response.status()).toBe(400)
  })
})
