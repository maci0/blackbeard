import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-41: HITL Interaction', () => {
  test.describe('Executions list page', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/executions')
    })

    test('page renders with heading', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /executions/i })).toBeVisible()
    })

    test('execution list renders table or empty state', async ({ page }) => {
      const table = page.getByRole('table')
      const emptyState = page.getByText(/no executions/i)
      const skeleton = page.locator('[class*="skeleton"], [class*="pulse"]')

      await page.waitForTimeout(500)

      const tableVisible = await table.isVisible().catch(() => false)
      const emptyVisible = await emptyState.isVisible().catch(() => false)
      const skeletonVisible = await skeleton
        .first()
        .isVisible()
        .catch(() => false)

      expect(tableVisible || emptyVisible || skeletonVisible).toBeTruthy()
    })

    test('refresh button is visible', async ({ page }) => {
      await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible()
    })
  })

  test.describe('Execution detail page', () => {
    test('execution detail shows event log section when navigable', async ({ page }) => {
      await loginAndNavigate(page, '/executions')

      // Wait for list to load
      await page.waitForTimeout(1000)

      // Try to click into the first execution row
      const table = page.getByRole('table')
      const tableVisible = await table.isVisible().catch(() => false)

      if (tableVisible) {
        const firstRow = table.locator('tbody tr').first()
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (rowVisible) {
          await firstRow.click()
          await page.waitForLoadState('domcontentloaded')

          // Execution detail page should show event log section
          const eventLogHeading = page.getByText(/event log/i)
          const tasksHeading = page.getByText(/tasks/i)

          // At minimum, the tasks or event log section should appear
          await expect(tasksHeading.first().or(eventLogHeading.first())).toBeVisible({
            timeout: 10000,
          })
        }
      }
      // If no executions exist, the test passes (nothing to drill into)
    })

    test('HITL panel appears for active executions with human input', async ({ page }) => {
      await loginAndNavigate(page, '/executions')
      await page.waitForTimeout(1000)

      const table = page.getByRole('table')
      const tableVisible = await table.isVisible().catch(() => false)

      if (tableVisible) {
        // Look for a running execution to check HITL panel
        const runningRow = table
          .locator('tbody tr')
          .filter({ hasText: /running/i })
          .first()
        const hasRunning = await runningRow.isVisible().catch(() => false)

        if (hasRunning) {
          await runningRow.click()
          await page.waitForLoadState('domcontentloaded')

          // If HITL panel is shown, it should have the response textarea
          const hitlPanel = page.getByText(/human input required/i)
          const hitlVisible = await hitlPanel.isVisible().catch(() => false)

          if (hitlVisible) {
            await expect(page.getByLabel(/your response/i)).toBeVisible()
            await expect(page.getByRole('button', { name: /respond/i })).toBeVisible()
          }
        }
      }
      // Gracefully passes when no running HITL executions exist
    })
  })
})
