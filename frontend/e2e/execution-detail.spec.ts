import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Execution detail page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('non-existent execution shows error', async ({ page }) => {
    await page.goto('/executions/00000000-0000-0000-0000-000000000000')

    await expect(
      page.getByText(/execution not found|failed to load/i),
    ).toBeVisible()
    await expect(
      page.getByRole('link', { name: /back to executions/i }),
    ).toBeVisible()
  })

  test('breadcrumb navigation present on execution page', async ({
    page,
  }) => {
    await page.goto('/executions')

    const table = page.getByRole('table', { name: /executions/i })
    const emptyState = page.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const breadcrumb = page.getByRole('navigation', {
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

    const table = page.getByRole('table', { name: /executions/i })
    const emptyState = page.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const cancelBtn = page.getByRole('button', {
        name: /cancel execution/i,
      })
      const retryBtn = page.getByRole('button', { name: /retry/i })

      const eitherBtn = cancelBtn.or(retryBtn)
      await expect(eitherBtn).toBeVisible()
    }
  })

  test('event log section present when execution has events', async ({
    page,
  }) => {
    await page.goto('/executions')

    const table = page.getByRole('table', { name: /executions/i })
    const emptyState = page.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstRow = table.getByRole('row').nth(1)
      await firstRow.click()

      const eventLog = page.getByRole('heading', { name: /event log/i })
      const noTasks = page.getByText(
        /no tasks recorded|waiting for tasks/i,
      )

      await expect(
        page.getByRole('heading', { name: /tasks/i }),
      ).toBeVisible()
      await expect(eventLog.or(noTasks)).toBeVisible()
    }
  })
})
