import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Tools page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/tools')
  })

  test('page loads with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Tools' })).toBeVisible()
    await expect(page.getByText('Tool library and registry')).toBeVisible()
  })

  test('tool cards are visible', async ({ page }) => {
    // Expect at least one tool card from seed data
    const toolCards = page.getByRole('link', { name: /^tool:/i })
    await expect(toolCards.first()).toBeVisible()
  })

  test('search filter works', async ({ page }) => {
    const searchInput = page.getByLabel(/search tools/i)
    await expect(searchInput).toBeVisible()

    await searchInput.fill('csv')

    // Should show filtered count
    await expect(page.getByRole('status')).toBeVisible()

    // At least one result should contain the search term
    await expect(page.getByText(/csv/i).first()).toBeVisible()
  })

  test('search clear button resets results', async ({ page }) => {
    const searchInput = page.getByLabel(/search tools/i)
    await searchInput.fill('csv')

    await expect(page.getByRole('status')).toBeVisible()

    await page.getByRole('button', { name: /clear search/i }).click()

    // Search input should be empty after clearing
    await expect(searchInput).toHaveValue('')
  })

  test('Built-in badge shown on builtin tools', async ({ page }) => {
    await expect(page.getByText('Built-in').first()).toBeVisible()
  })

  test('Create in Studio link exists', async ({ page }) => {
    await expect(
      page.getByRole('link', { name: /create in studio/i }),
    ).toBeVisible()
  })

  test('Refresh button exists', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh tools/i })
    await expect(refreshBtn).toBeVisible()
  })
})
