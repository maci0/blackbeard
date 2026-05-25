import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Notifications', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('bell icon in sidebar footer', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /notifications/i }),
    ).toBeVisible()
  })

  test('click bell opens notification dropdown', async ({ page }) => {
    await page.getByRole('button', { name: /notifications/i }).click()

    await expect(
      page.getByRole('dialog', { name: /notifications/i }).or(
        page.getByRole('menu', { name: /notifications/i }),
      ).or(page.locator('[data-testid="notification-dropdown"]')),
    ).toBeVisible()
  })

  test('notification dropdown has mark all read or empty state', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /notifications/i }).click()

    const markAllRead = page.getByRole('button', { name: /mark all read/i })
    const emptyState = page.getByText(/no notifications|all caught up/i)

    await expect(markAllRead.or(emptyState)).toBeVisible()
  })
})
