import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Audit Logs page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/audit-logs')
  })

  test('page loads with title', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Audit Logs' }),
    ).toBeVisible()
  })

  test('filter dropdowns present', async ({ page }) => {
    const main = page.locator('main')
    const actionFilter = main.getByLabel('Filter by action')
    await expect(actionFilter).toBeVisible()

    const resourceTypeFilter = main.getByLabel('Filter by resource type')
    await expect(resourceTypeFilter).toBeVisible()

    const actorSearch = main.getByLabel('Search by actor ID')
    await expect(actorSearch).toBeVisible()
  })

  test('pagination or empty state visible', async ({ page }) => {
    const main = page.locator('main')
    const table = main.getByRole('table', { name: /audit logs/i })
    const emptyState = main.getByText(/no audit logs yet/i)

    await expect(table.or(emptyState)).toBeVisible()
  })

  test('table headers correct when logs exist', async ({ page }) => {
    const main = page.locator('main')
    const table = main.getByRole('table', { name: /audit logs/i })
    const emptyState = main.getByText(/no audit logs yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const expectedHeaders = [
        'Timestamp',
        'Action',
        'Actor',
        'Resource Type',
        'Resource ID',
      ]
      for (const header of expectedHeaders) {
        await expect(
          table.getByRole('columnheader', { name: header }),
        ).toBeVisible()
      }
    }
  })
})
