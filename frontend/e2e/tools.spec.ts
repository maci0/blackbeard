import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Tools page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/tools')
  })

  test('page loads with header', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Tools' })).toBeVisible()
    await expect(main.getByText('Tool library and registry')).toBeVisible()
  })

  test('tool cards are visible', async ({ page }) => {
    const main = page.locator('main')
    // Expect at least one tool card from seed data
    const toolCards = main.getByRole('link', { name: /^tool:/i })
    await expect(toolCards.first()).toBeVisible()
  })

  test('search filter works', async ({ page }) => {
    const main = page.locator('main')
    const searchInput = main.getByLabel(/search tools/i)
    await expect(searchInput).toBeVisible()

    await searchInput.fill('csv')

    // Should show filtered count
    await expect(main.getByRole('status')).toBeVisible()

    // At least one result should contain the search term
    await expect(main.getByText(/csv/i).first()).toBeVisible()
  })

  test('search clear button resets results', async ({ page }) => {
    const main = page.locator('main')
    const searchInput = main.getByLabel(/search tools/i)
    await searchInput.fill('csv')

    await expect(main.getByRole('status')).toBeVisible()

    await main.getByRole('button', { name: /clear search/i }).click()

    // Search input should be empty after clearing
    await expect(searchInput).toHaveValue('')
  })

  test('Built-in badge shown on builtin tools', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByText('Built-in').first()).toBeVisible()
  })

  test('Create in Studio link exists', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('link', { name: /create in studio/i }),
    ).toBeVisible()
  })

  test('Refresh button exists', async ({ page }) => {
    const main = page.locator('main')
    const refreshBtn = main.getByRole('button', { name: /refresh tools/i })
    await expect(refreshBtn).toBeVisible()
  })
})
