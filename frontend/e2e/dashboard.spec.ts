import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('dashboard loads and shows title', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Dashboard' }),
    ).toBeVisible()
    await expect(
      main.getByText('Overview of your agent management platform'),
    ).toBeVisible()
  })

  test('stat cards rendered', async ({ page }) => {
    const main = page.locator('main')
    const statLabels = [
      'Total Resources',
      'Active Executions',
      'LLM Spend',
      'Total Models',
      'Automations',
    ]

    for (const label of statLabels) {
      await expect(
        main.getByLabel(new RegExp(label)),
      ).toBeVisible({ timeout: 10000 })
    }
  })

  test('Resources by Kind chart shows bars or empty state', async ({
    page,
  }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Resources by Kind' }),
    ).toBeVisible()

    const section = main.locator('section').filter({
      has: page.locator('h2', { hasText: 'Resources by Kind' }),
    })
    const meters = section.getByRole('meter')
    const emptyMsg = section.getByText('No resources created yet')

    await expect(meters.first().or(emptyMsg)).toBeVisible()
  })

  test('Quick Actions links work', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Quick Actions' }),
    ).toBeVisible()

    const section = main.locator('section').filter({
      has: page.locator('h2', { hasText: 'Quick Actions' }),
    })
    await expect(section.getByText('Open Studio')).toBeVisible()
    await expect(section.getByText('Import from Marketplace')).toBeVisible()
    await expect(section.getByText('Add Model')).toBeVisible()

    await section.getByText('Open Studio').click()
    await expect(page).toHaveURL('/studio')
  })

  test('Recent Executions table shows or empty state', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Recent Executions' }),
    ).toBeVisible()

    const section = main.locator('section').filter({
      has: page.locator('h2', { hasText: 'Recent Executions' }),
    })
    const table = section.locator('table')
    const emptyMsg = section.getByText('No executions yet')

    await expect(table.or(emptyMsg)).toBeVisible()
  })

  test('Spend by Crew section renders', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Spend by Crew' }),
    ).toBeVisible()

    const section = main.locator('section').filter({
      has: page.locator('h2', { hasText: 'Spend by Crew' }),
    })
    const meters = section.getByRole('meter')
    const emptyMsg = section.getByText('No spend data yet')

    await expect(meters.first().or(emptyMsg)).toBeVisible()
  })
})
