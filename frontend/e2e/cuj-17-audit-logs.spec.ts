import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-17: Audit Trail Review', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/audit-logs')
  })

  test('page renders with "Audit Logs" heading', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Audit Logs' }),
    ).toBeVisible()
  })

  test('action filter control is visible', async ({ page }) => {
    const main = page.locator('main')
    const actionFilter = main.getByLabel('Filter by action')
    await expect(actionFilter).toBeVisible()
  })

  test('resource type filter control is visible', async ({ page }) => {
    const main = page.locator('main')
    const resourceTypeFilter = main.getByLabel('Filter by resource type')
    await expect(resourceTypeFilter).toBeVisible()
  })

  test('actor search control is visible', async ({ page }) => {
    const main = page.locator('main')
    const actorSearch = main.getByLabel('Search by actor ID')
    await expect(actorSearch).toBeVisible()
  })

  test('table or empty state is rendered', async ({ page }) => {
    const main = page.locator('main')
    const table = main.getByRole('table', { name: /audit logs/i })
    const emptyState = main.getByText(/no audit logs yet/i)

    await expect(table.or(emptyState)).toBeVisible()
  })

  test('table has expected column headers when logs exist', async ({
    page,
  }) => {
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

  test('filter controls can be interacted with', async ({ page }) => {
    const main = page.locator('main')

    // Type into actor search
    const actorSearch = main.getByLabel('Search by actor ID')
    await actorSearch.fill('admin')
    await expect(actorSearch).toHaveValue('admin')

    // Clear it
    await actorSearch.fill('')
    await expect(actorSearch).toHaveValue('')
  })
})
