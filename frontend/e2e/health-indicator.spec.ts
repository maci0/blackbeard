import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Health Indicator', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('health dot visible in sidebar footer', async ({ page }) => {
    await expect(
      page.locator('[data-testid="health-dot"]').or(
        page.getByRole('status', { name: /health/i }),
      ).or(page.locator('.health-indicator')),
    ).toBeVisible()
  })

  test('dot has title attribute with status info', async ({ page }) => {
    const healthDot = page
      .locator('[data-testid="health-dot"]')
      .or(page.getByRole('status', { name: /health/i }))
      .or(page.locator('.health-indicator'))

    await expect(healthDot).toBeVisible()
    await expect(healthDot).toHaveAttribute('title', /.+/)
  })

  test('API label shown next to dot', async ({ page }) => {
    await expect(
      page.getByText(/api/i).locator('visible=true').first(),
    ).toBeVisible()
  })
})
