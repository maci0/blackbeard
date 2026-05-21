import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Executions page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Executions' }).click()
    await page.waitForURL('/executions')
  })

  test('page loads with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Executions' })).toBeVisible()
  })

  test('shows empty state with Go to Studio CTA when no executions', async ({
    page,
  }) => {
    // If no executions, empty state should be visible
    const emptyState = page.getByText(/no executions yet/i)
    const table = page.getByRole('table', { name: /executions/i })

    // Either empty state or table should be visible
    await expect(emptyState.or(table)).toBeVisible()

    // If empty state is shown, verify the CTA
    if (await emptyState.isVisible()) {
      await expect(page.getByRole('link', { name: /go to studio/i })).toBeVisible()
    }
  })

  test('Refresh button exists and is clickable', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh executions/i })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
  })

  test('page has correct document title', async ({ page }) => {
    await expect(page).toHaveTitle(/executions/i)
  })

  test('shows table with correct headers when executions exist', async ({
    page,
  }) => {
    const table = page.getByRole('table', { name: /executions/i })

    // Only check headers if the table exists (executions present)
    if (await table.isVisible()) {
      await expect(table.getByRole('columnheader', { name: /status/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /crew/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /tokens/i })).toBeVisible()
      await expect(table.getByRole('columnheader', { name: /cost/i })).toBeVisible()
    }
  })
})
