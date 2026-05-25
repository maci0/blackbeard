import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Executions page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/executions')
  })

  test('page loads with header', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Executions' })).toBeVisible()
  })

  test('shows empty state with Go to Studio CTA when no executions', async ({
    page,
  }) => {
    const main = page.locator('main')
    // If no executions, empty state should be visible
    const emptyState = main.getByText(/no executions yet/i)
    const table = main.getByRole('table', { name: /executions/i })

    // Either empty state or table should be visible
    await expect(emptyState.or(table)).toBeVisible()

    // If empty state is shown, verify the CTA
    if (await emptyState.isVisible()) {
      await expect(main.getByRole('link', { name: /go to studio/i })).toBeVisible()
    }
  })

  test('Refresh button exists and is clickable', async ({ page }) => {
    const main = page.locator('main')
    const refreshBtn = main.getByRole('button', { name: /refresh executions/i })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
  })

  test('page has correct document title', async ({ page }) => {
    await expect(page).toHaveTitle(/executions/i)
  })

  test('shows table with correct headers when executions exist', async ({
    page,
  }) => {
    const main = page.locator('main')
    const table = main.getByRole('table', { name: /executions/i })

    // Only check headers if the table exists (executions present)
    if (await table.isVisible()) {
      await expect(table.getByRole('columnheader', { name: /status/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /crew/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /tokens/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /cost/i })).toBeVisible()
    }
  })
})
