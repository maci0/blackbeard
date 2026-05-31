import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Agency Agents Import', () => {
  test('import endpoint returns agent list', async ({ page }) => {
    await loginAndNavigate(page, '/resources')

    // The agency import API should be reachable
    const response = await page.request.get('/api/v1/import/agency-agents?division=engineering', {
      headers: { 'X-API-Key': 'change-me-in-production' },
    })
    // May fail if GitHub is unreachable, but should not 500
    expect([200, 429, 502, 503]).toContain(response.status())
  })

  test('import endpoint validates division parameter', async ({ page }) => {
    await loginAndNavigate(page, '/resources')

    const response = await page.request.get('/api/v1/import/agency-agents?division=nonexistent', {
      headers: { 'X-API-Key': 'change-me-in-production' },
    })
    expect(response.status()).toBe(422)
  })
})
