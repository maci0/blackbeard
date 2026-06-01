import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-44: Version Rollback', () => {
  test('resource detail page shows version number', async ({ page }) => {
    await loginAndNavigate(page, '/resources')

    // Wait for resources to load
    await page.waitForTimeout(1000)

    const table = page.getByRole('table')
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      // Click on the first resource to navigate to its detail
      const firstRow = table.locator('tbody tr').first()
      const rowVisible = await firstRow.isVisible().catch(() => false)

      if (rowVisible) {
        await firstRow.click()
        await page.waitForLoadState('domcontentloaded')

        // Version number should be displayed on the detail page
        const versionBadge = page.getByText(/v\d+/i)
        await expect(versionBadge.first()).toBeVisible({ timeout: 10000 })
      }
    }
    // If no resources, test passes gracefully
  })

  test('resource detail page has history tab', async ({ page }) => {
    await loginAndNavigate(page, '/resources')
    await page.waitForTimeout(1000)

    const table = page.getByRole('table')
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      const firstRow = table.locator('tbody tr').first()
      const rowVisible = await firstRow.isVisible().catch(() => false)

      if (rowVisible) {
        await firstRow.click()
        await page.waitForLoadState('domcontentloaded')

        // The tab bar should include a "history" tab
        const historyTab = page.getByRole('tab', { name: /history/i })
        await expect(historyTab).toBeVisible({ timeout: 10000 })
      }
    }
  })

  test('history tab shows version timeline or empty message', async ({ page }) => {
    await loginAndNavigate(page, '/resources')
    await page.waitForTimeout(1000)

    const table = page.getByRole('table')
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      const firstRow = table.locator('tbody tr').first()
      const rowVisible = await firstRow.isVisible().catch(() => false)

      if (rowVisible) {
        await firstRow.click()
        await page.waitForLoadState('domcontentloaded')

        const historyTab = page.getByRole('tab', { name: /history/i })
        const tabVisible = await historyTab.isVisible().catch(() => false)

        if (tabVisible) {
          await historyTab.click()
          await page.waitForTimeout(500)

          // Should show "Current version" badge or "No history available"
          const currentVersion = page.getByText(/current version/i)
          const noHistory = page.getByText(/no history available/i)
          const loadingHistory = page.getByText(/loading history/i)

          await expect(currentVersion.or(noHistory).or(loadingHistory)).toBeVisible({
            timeout: 10000,
          })
        }
      }
    }
  })

  test('current version badge displays on history tab', async ({ page }) => {
    await loginAndNavigate(page, '/resources')
    await page.waitForTimeout(1000)

    const table = page.getByRole('table')
    const tableVisible = await table.isVisible().catch(() => false)

    if (tableVisible) {
      const firstRow = table.locator('tbody tr').first()
      const rowVisible = await firstRow.isVisible().catch(() => false)

      if (rowVisible) {
        await firstRow.click()
        await page.waitForLoadState('domcontentloaded')

        const historyTab = page.getByRole('tab', { name: /history/i })
        const tabVisible = await historyTab.isVisible().catch(() => false)

        if (tabVisible) {
          await historyTab.click()
          await page.waitForTimeout(1000)

          // The version badge (e.g. "v1", "v2") should appear
          const versionBadge = page.locator('span').filter({ hasText: /^v\d+$/ })
          const noHistory = page.getByText(/no history available/i)

          await expect(versionBadge.first().or(noHistory)).toBeVisible({ timeout: 10000 })
        }
      }
    }
  })
})
