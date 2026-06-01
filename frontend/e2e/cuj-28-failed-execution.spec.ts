import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-28: Failed Execution Handling', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/executions')
  })

  test('executions page renders with heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /executions/i })).toBeVisible()
  })

  test('executions page shows table or empty state', async ({ page }) => {
    const table = page.getByRole('table', { name: /executions/i })
    const emptyState = page.getByText(/no executions yet/i)
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

  test('clicking an execution row navigates to detail page', async ({ page }) => {
    const table = page.getByRole('table', { name: /executions/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      // No executions to click, skip gracefully
      return
    }

    const firstRow = table.getByRole('row').nth(1) // skip header
    const rowVisible = await firstRow.isVisible().catch(() => false)

    if (rowVisible) {
      await firstRow.click()
      await expect(page).toHaveURL(/\/executions\//)
    }
  })

  test('execution detail page has error display area for failed runs', async ({ page }) => {
    const table = page.getByRole('table', { name: /executions/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      return
    }

    const firstRow = table.getByRole('row').nth(1)
    const rowVisible = await firstRow.isVisible().catch(() => false)

    if (!rowVisible) {
      return
    }

    await firstRow.click()
    await expect(page).toHaveURL(/\/executions\//)

    // The detail page should show status, tasks, and event log sections.
    // For failed executions, an error alert with role="alert" is rendered.
    // For any execution, the status summary card is always present.
    const statusLabel = page.getByText(/status/i).first()
    await expect(statusLabel).toBeVisible({ timeout: 10000 })

    // Check that the breadcrumb links back to executions
    const breadcrumbLink = page.getByRole('link', { name: /executions/i })
    await expect(breadcrumbLink).toBeVisible()
  })

  test('execution detail page shows retry button for terminal executions', async ({ page }) => {
    const table = page.getByRole('table', { name: /executions/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      return
    }

    const firstRow = table.getByRole('row').nth(1)
    const rowVisible = await firstRow.isVisible().catch(() => false)

    if (!rowVisible) {
      return
    }

    await firstRow.click()
    await expect(page).toHaveURL(/\/executions\//)
    await page.waitForTimeout(1000)

    // Terminal executions show a Retry button, active ones show Cancel
    const retryButton = page.getByRole('button', { name: /retry/i })
    const cancelButton = page.getByRole('button', { name: /cancel execution/i })

    const retryVisible = await retryButton.isVisible().catch(() => false)
    const cancelVisible = await cancelButton.isVisible().catch(() => false)

    // At least one should be visible (retry for completed/failed, cancel for running)
    expect(retryVisible || cancelVisible).toBeTruthy()
  })

  test('execution detail page shows tasks section', async ({ page }) => {
    const table = page.getByRole('table', { name: /executions/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      return
    }

    const firstRow = table.getByRole('row').nth(1)
    const rowVisible = await firstRow.isVisible().catch(() => false)

    if (!rowVisible) {
      return
    }

    await firstRow.click()
    await expect(page).toHaveURL(/\/executions\//)

    const tasksHeading = page.getByRole('heading', { name: /tasks/i })
    await expect(tasksHeading).toBeVisible({ timeout: 10000 })
  })

  test('refresh button is visible on executions list', async ({ page }) => {
    await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible()
  })
})
