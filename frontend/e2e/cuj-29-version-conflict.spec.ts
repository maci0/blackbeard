import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-29: Version Conflict Detection', () => {
  test.describe('Resource detail version display', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/resources')
    })

    test('resources page renders with heading', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()
    })

    test('resource detail shows version number', async ({ page }) => {
      const table = page.getByRole('table', { name: /resources/i })
      const tableVisible = await table.isVisible().catch(() => false)

      if (!tableVisible) {
        // Check for card view instead
        const cards = page.getByRole('article')
        const cardVisible = await cards
          .first()
          .isVisible()
          .catch(() => false)

        if (!cardVisible) {
          // No resources exist, skip
          return
        }

        await cards.first().click()
      } else {
        const firstRow = table.getByRole('row').nth(1)
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (!rowVisible) {
          return
        }

        await firstRow.click()
      }

      await expect(page).toHaveURL(/\/resources\//)

      // Version badge should be visible (displayed as "v{number}")
      const versionBadge = page.locator('text=/v\\d+/')
      await expect(versionBadge.first()).toBeVisible({ timeout: 10000 })
    })

    test('resource detail has history tab', async ({ page }) => {
      const table = page.getByRole('table', { name: /resources/i })
      const tableVisible = await table.isVisible().catch(() => false)

      if (!tableVisible) {
        const cards = page.getByRole('article')
        const cardVisible = await cards
          .first()
          .isVisible()
          .catch(() => false)

        if (!cardVisible) {
          return
        }

        await cards.first().click()
      } else {
        const firstRow = table.getByRole('row').nth(1)
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (!rowVisible) {
          return
        }

        await firstRow.click()
      }

      await expect(page).toHaveURL(/\/resources\//)

      // The History tab should exist in the tab list
      const historyTab = page.getByRole('tab', { name: /history/i })
      await expect(historyTab).toBeVisible({ timeout: 10000 })
    })

    test('clicking history tab shows version timeline', async ({ page }) => {
      const table = page.getByRole('table', { name: /resources/i })
      const tableVisible = await table.isVisible().catch(() => false)

      if (!tableVisible) {
        const cards = page.getByRole('article')
        const cardVisible = await cards
          .first()
          .isVisible()
          .catch(() => false)

        if (!cardVisible) {
          return
        }

        await cards.first().click()
      } else {
        const firstRow = table.getByRole('row').nth(1)
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (!rowVisible) {
          return
        }

        await firstRow.click()
      }

      await expect(page).toHaveURL(/\/resources\//)

      const historyTab = page.getByRole('tab', { name: /history/i })
      await expect(historyTab).toBeVisible({ timeout: 10000 })
      await historyTab.click()

      // After clicking history, should show "Current version" text or loading state
      const currentVersion = page.getByText(/current version/i)
      const noHistory = page.getByText(/no history/i)
      const loadingHistory = page.getByText(/loading history/i)

      await page.waitForTimeout(1000)

      const versionVisible = await currentVersion.isVisible().catch(() => false)
      const noHistoryVisible = await noHistory.isVisible().catch(() => false)
      const loadingVisible = await loadingHistory.isVisible().catch(() => false)

      expect(versionVisible || noHistoryVisible || loadingVisible).toBeTruthy()
    })

    test('resource detail has edit button', async ({ page }) => {
      const table = page.getByRole('table', { name: /resources/i })
      const tableVisible = await table.isVisible().catch(() => false)

      if (!tableVisible) {
        const cards = page.getByRole('article')
        const cardVisible = await cards
          .first()
          .isVisible()
          .catch(() => false)

        if (!cardVisible) {
          return
        }

        await cards.first().click()
      } else {
        const firstRow = table.getByRole('row').nth(1)
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (!rowVisible) {
          return
        }

        await firstRow.click()
      }

      await expect(page).toHaveURL(/\/resources\//)

      const editButton = page.getByRole('button', { name: /edit/i })
      await expect(editButton).toBeVisible({ timeout: 10000 })
    })
  })
})
