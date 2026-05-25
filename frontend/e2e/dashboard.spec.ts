import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/dashboard')
  })

  test('dashboard loads and shows title', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Dashboard' }),
    ).toBeVisible()
    await expect(
      page.getByText('Overview of your agent management platform'),
    ).toBeVisible()
  })

  test('stat cards rendered', async ({ page }) => {
    const statLabels = [
      'Total Resources',
      'Active Executions',
      'LLM Spend',
      'Total Models',
      'Automations',
    ]

    for (const label of statLabels) {
      await expect(page.getByLabel(new RegExp(label))).toBeVisible()
    }
  })

  test('Resources by Kind chart shows bars or empty state', async ({
    page,
  }) => {
    const heading = page.getByRole('heading', { name: 'Resources by Kind' })
    await expect(heading).toBeVisible()

    const meters = page.getByRole('meter')
    const emptyMsg = page.getByText('No resources created yet')

    await expect(meters.first().or(emptyMsg)).toBeVisible()
  })

  test('Quick Actions links work', async ({ page }) => {
    const quickActions = page.getByRole('heading', {
      name: 'Quick Actions',
    })
    await expect(quickActions).toBeVisible()

    await expect(page.getByRole('link', { name: /Open Studio/i })).toBeVisible()
    await expect(
      page.getByRole('link', { name: /Import from Marketplace/i }),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: /Add Model/i })).toBeVisible()

    await page.getByRole('link', { name: /Open Studio/i }).click()
    await expect(page).toHaveURL('/studio')
  })

  test('Recent Executions table shows or empty state', async ({ page }) => {
    const heading = page.getByRole('heading', {
      name: 'Recent Executions',
    })
    await expect(heading).toBeVisible()

    const table = page.getByRole('table', { name: /recent executions/i })
    const emptyMsg = page.getByText('No executions yet')

    await expect(table.or(emptyMsg)).toBeVisible()
  })

  test('Spend by Crew section renders', async ({ page }) => {
    const heading = page.getByRole('heading', { name: 'Spend by Crew' })
    await expect(heading).toBeVisible()

    const meters = page
      .locator('section')
      .filter({ has: heading })
      .getByRole('meter')
    const emptyMsg = page.getByText('No spend data yet')

    await expect(meters.first().or(emptyMsg)).toBeVisible()
  })
})
