import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-43: API Key Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/settings')
  })

  test('settings page renders with heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Settings' })).toBeVisible()
  })

  test('API Connection section is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'API Connection' })).toBeVisible()
    await expect(main.getByLabel('API base URL')).toBeVisible()
  })

  test('Authentication section shows auth method', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Authentication' })).toBeVisible()
    await expect(main.getByText('Auth method')).toBeVisible()
  })

  test('API key section displays status or generate button', async ({ page }) => {
    const main = page.locator('main')

    // The settings page should show either a generate button (no key)
    // or the masked key with rotate/revoke options
    const generateBtn = main.getByRole('button', {
      name: /generate.*key/i,
    })
    const maskedKey = main.getByText(/\*{3,}/i)
    const revokeBtn = main.getByRole('button', { name: /revoke/i })
    const rotateBtn = main.getByRole('button', { name: /rotate/i })

    // Wait for the key status to load
    await page.waitForTimeout(1000)

    const hasGenerate = await generateBtn.isVisible().catch(() => false)
    const hasMasked = await maskedKey.isVisible().catch(() => false)
    const hasRevoke = await revokeBtn.isVisible().catch(() => false)
    const hasRotate = await rotateBtn.isVisible().catch(() => false)

    // One of these states should be true
    expect(hasGenerate || hasMasked || hasRevoke || hasRotate).toBeTruthy()
  })

  test('save button exists for API base URL', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByRole('button', { name: /save/i })).toBeVisible()
  })

  test('Services section shows expected endpoints', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Services' })).toBeVisible()
    await expect(main.getByText('/api/v1/health')).toBeVisible()
    await expect(main.getByText('/api/v1/docs')).toBeVisible()
  })
})
