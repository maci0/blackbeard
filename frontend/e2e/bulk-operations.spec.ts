import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Bulk operations', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Resources page shows checkboxes in list view', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const viewToggle = main.getByRole('radiogroup', { name: /view mode/i })
    await viewToggle.getByRole('radio', { name: /list view/i }).click()

    const table = main.getByRole('table', { name: /resources/i })
    const emptyState = main.getByText(/no resources found/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const checkboxes = table.getByRole('checkbox')
      await expect(checkboxes.first()).toBeVisible()
    }
  })

  test('selecting items shows floating action bar with count', async ({
    page,
  }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const viewToggle = main.getByRole('radiogroup', { name: /view mode/i })
    await viewToggle.getByRole('radio', { name: /list view/i }).click()

    const table = main.getByRole('table', { name: /resources/i })
    const emptyState = main.getByText(/no resources found/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstCheckbox = table
        .getByRole('row')
        .nth(1)
        .getByRole('checkbox')

      if (await firstCheckbox.isVisible()) {
        await firstCheckbox.click()
        await expect(main.getByText(/1 selected/i)).toBeVisible()
        await expect(
          main.getByRole('button', { name: /delete selected/i }),
        ).toBeVisible()
      }
    }
  })

  test('clear selection button works', async ({ page }) => {
    await page.goto('/resources')

    const main = page.locator('main')
    const viewToggle = main.getByRole('radiogroup', { name: /view mode/i })
    await viewToggle.getByRole('radio', { name: /list view/i }).click()

    const table = main.getByRole('table', { name: /resources/i })
    const emptyState = main.getByText(/no resources found/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const firstCheckbox = table
        .getByRole('row')
        .nth(1)
        .getByRole('checkbox')

      if (await firstCheckbox.isVisible()) {
        await firstCheckbox.click()
        await expect(main.getByText(/1 selected/i)).toBeVisible()

        await main.getByRole('button', { name: /clear selection/i }).click()
        await expect(main.getByText(/1 selected/i)).not.toBeVisible()
      }
    }
  })

  test('compare button on Executions page', async ({ page }) => {
    await page.goto('/executions')

    const main = page.locator('main')
    const table = main.getByRole('table', { name: /executions/i })
    const emptyState = main.getByText(/no executions yet/i)

    await expect(table.or(emptyState)).toBeVisible()

    if (await table.isVisible()) {
      const compareButton = main.getByRole('button', {
        name: /compare/i,
      })
      await expect(compareButton).toBeVisible()
      await expect(compareButton).toBeDisabled()

      const rows = table.getByRole('row')
      const rowCount = await rows.count()

      if (rowCount > 2) {
        const checkbox1 = rows.nth(1).getByRole('checkbox')
        const checkbox2 = rows.nth(2).getByRole('checkbox')

        await checkbox1.click()
        await checkbox2.click()

        await expect(
          main.getByRole('button', {
            name: /compare selected executions/i,
          }),
        ).toBeEnabled()
      }
    }
  })
})
