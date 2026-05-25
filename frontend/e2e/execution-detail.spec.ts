import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Execution detail page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('non-existent execution shows error', async ({ page }) => {
    await page.goto('/executions/00000000-0000-0000-0000-000000000000')

    const main = page.locator('main')
    await expect(
      main.getByText(/execution not found|failed to load/i),
    ).toBeVisible()
    await expect(
      main.getByRole('link', { name: /back to executions/i }),
    ).toBeVisible()
  })

  test('breadcrumb navigation present on execution page', async ({
    page,
  }) => {
    await page.goto('/executions')

    const main = page.locator('main')
    const table = main.getByRole('table', { name: /executions/i })
    const emptyState = main.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const breadcrumb = main.getByRole('navigation', {
        name: /breadcrumb/i,
      })
      await expect(breadcrumb).toBeVisible()
      await expect(
        breadcrumb.getByRole('link', { name: 'Executions' }),
      ).toBeVisible()
    }
  })

  test('cancel or retry buttons conditionally shown', async ({ page }) => {
    await page.goto('/executions')

    const main = page.locator('main')
    const table = main.getByRole('table', { name: /executions/i })
    const emptyState = main.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const cancelBtn = main.getByRole('button', {
        name: /cancel execution/i,
      })
      const retryBtn = main.getByRole('button', { name: /retry/i })

      const eitherBtn = cancelBtn.or(retryBtn)
      await expect(eitherBtn).toBeVisible()
    }
  })

  test('event log section present when execution has events', async ({
    page,
  }) => {
    await page.goto('/executions')

    const main = page.locator('main')
    const table = main.getByRole('table', { name: /executions/i })
    const emptyState = main.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const eventLog = main.locator('h1, h2, h3').filter({ hasText: /event log/i })
      const noTasks = main.getByText(
        /no tasks recorded|waiting for tasks/i,
      )

      await expect(
        main.locator('h1, h2, h3').filter({ hasText: /tasks/i }),
      ).toBeVisible()
      await expect(eventLog.or(noTasks)).toBeVisible()
    }
  })
})
