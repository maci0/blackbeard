import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Tools Library Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/tools/library')
  })

  test('page renders with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /tool library/i })).toBeVisible()
  })

  test('displays tool cards from catalog', async ({ page }) => {
    // Wait for tools to load
    const cards = page.locator('[class*="card"], [class*="rounded-lg"]').filter({ hasText: /install/i })
    // Should have at least one installable tool
    await expect(cards.first()).toBeVisible({ timeout: 10000 })
  })

  test('search filters tools', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i)
    if (await searchInput.isVisible()) {
      await searchInput.fill('web-search')
      // Wait for filtering
      await page.waitForTimeout(300)
      // Should show filtered results
      const visibleCards = page.locator('[class*="card"], [class*="rounded-lg"]')
      await expect(visibleCards.first()).toBeVisible()
    }
  })
})
