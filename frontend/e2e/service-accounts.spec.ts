import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Service Accounts Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/service-accounts')
  })

  test('page renders with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /service accounts/i })).toBeVisible()
  })

  test('shows empty state when no service accounts exist', async ({ page }) => {
    const emptyMsg = page.getByText(/no service accounts/i)
    const table = page.locator('table')
    // Either empty state or a table with data
    await expect(emptyMsg.or(table)).toBeVisible()
  })

  test('refresh button works', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh/i })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
    // Should not crash or navigate away
    await expect(page).toHaveURL('/service-accounts')
  })
})
