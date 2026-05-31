import { test, expect } from '@playwright/test'
import { login, loginAndNavigate } from './helpers'

test.describe('CUJ-16: Execution Comparison', () => {
  test.describe('Execution list page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/executions')
    })

    test('execution list page renders with heading', async ({ page }) => {
      const main = page.locator('main')
      await expect(
        main.locator('h1, h2, h3').filter({ hasText: 'Executions' }),
      ).toBeVisible()
    })

    test('compare button is visible on executions page', async ({ page }) => {
      const main = page.locator('main')
      // The compare button is always rendered; it is disabled until 2 rows are selected
      const compareBtn = main.getByRole('button', {
        name: /compare/i,
      })
      // The button may only appear when there are executions in the list,
      // so check for either the button or an empty state
      const emptyState = main.getByText(/no executions/i)
      await expect(compareBtn.or(emptyState)).toBeVisible()
    })

    test('refresh button works', async ({ page }) => {
      const main = page.locator('main')
      const refreshBtn = main.getByRole('button', {
        name: /refresh executions/i,
      })
      await expect(refreshBtn).toBeVisible()
      await refreshBtn.click()
      // Page should remain on executions after refresh
      await expect(page).toHaveURL(/\/executions/)
    })
  })

  test.describe('Compare page', () => {
    test.beforeEach(async ({ page }) => {
      await login(page)
    })

    test('compare page without IDs shows error message', async ({ page }) => {
      await page.goto('/executions/compare')

      const main = page.locator('main')
      // Without query params, the page shows a message about needing IDs
      await expect(
        main.getByText(/two execution ids are required|select.*executions|no executions selected/i),
      ).toBeVisible()
    })

    test('compare page renders heading', async ({ page }) => {
      await page.goto('/executions/compare')

      const main = page.locator('main')
      await expect(
        main.locator('h1, h2, h3').filter({ hasText: /compare/i }),
      ).toBeVisible()
    })

    test('compare page with invalid IDs shows error state', async ({
      page,
    }) => {
      await page.goto(
        '/executions/compare?a=00000000-0000-0000-0000-000000000000&b=00000000-0000-0000-0000-000000000001',
      )

      const main = page.locator('main')
      await expect(
        main.getByText(/failed to load|error|not found/i),
      ).toBeVisible()
    })

    test('back to executions link is accessible', async ({ page }) => {
      await page.goto('/executions/compare')

      const main = page.locator('main')
      const backLink = main.getByRole('link', { name: /back to executions/i })
      // The link exists in the error state
      await expect(backLink).toBeVisible()
    })
  })
})
