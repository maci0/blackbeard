import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-36: Budget Policy Management', () => {
  test.describe('AgentPolicy resources', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/resources')
    })

    test('resources page renders', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()
    })

    test('kind filter dropdown includes AgentPolicy', async ({ page }) => {
      const kindFilter = page.getByLabel(/filter by kind/i)
      await expect(kindFilter).toBeVisible()

      // Check that AgentPolicy is in the filter options
      const options = kindFilter.locator('option')
      const texts = await options.allTextContents()
      expect(texts.map((t) => t.toLowerCase())).toEqual(expect.arrayContaining(['agentpolicy']))
    })

    test('filtering by AgentPolicy shows relevant resources', async ({ page }) => {
      const kindFilter = page.getByLabel(/filter by kind/i)
      await kindFilter.selectOption({ label: 'AgentPolicy' })

      await page.waitForTimeout(500)

      // Should show filtered results or empty state
      const results = page.getByText(/result/i)
      await expect(results).toBeVisible()
    })

    test('AgentPolicy resource detail shows spec fields', async ({ page }) => {
      // Filter to AgentPolicy kind
      const kindFilter = page.getByLabel(/filter by kind/i)
      await kindFilter.selectOption({ label: 'AgentPolicy' })

      await page.waitForTimeout(500)

      // Check for table or card view
      const table = page.getByRole('table', { name: /resources/i })
      const tableVisible = await table.isVisible().catch(() => false)
      const cards = page.getByRole('article')
      const cardsVisible = await cards
        .first()
        .isVisible()
        .catch(() => false)

      if (tableVisible) {
        const firstRow = table.getByRole('row').nth(1)
        const rowVisible = await firstRow.isVisible().catch(() => false)

        if (rowVisible) {
          await firstRow.click()
          await expect(page).toHaveURL(/\/resources\//)

          // Spec tab should be active by default
          const specTab = page.getByRole('tab', { name: /spec/i })
          await expect(specTab).toBeVisible({ timeout: 10000 })

          // The spec display should be visible
          const specContent = page.locator('[class*="divide-y"]')
          await expect(specContent).toBeVisible()
        }
      } else if (cardsVisible) {
        await cards.first().click()
        await expect(page).toHaveURL(/\/resources\//)

        const specTab = page.getByRole('tab', { name: /spec/i })
        await expect(specTab).toBeVisible({ timeout: 10000 })
      }
      // If no AgentPolicy resources exist, test passes silently
    })
  })

  test.describe('New resource creation dialog', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/resources')
    })

    test('new resource dialog has kind selector with AgentPolicy', async ({ page }) => {
      const newButton = page.getByRole('button', { name: /new resource/i })
      await newButton.click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      // Kind selector should contain AgentPolicy
      const kindSelect = dialog.locator('#new-resource-kind')
      await expect(kindSelect).toBeVisible()

      const options = kindSelect.locator('option')
      const texts = await options.allTextContents()
      expect(texts).toContain('AgentPolicy')
    })

    test('new resource dialog has spec JSON field', async ({ page }) => {
      const newButton = page.getByRole('button', { name: /new resource/i })
      await newButton.click()

      const dialog = page.getByRole('dialog')

      // Spec textarea should be visible for entering budget config
      const specField = dialog.locator('#new-resource-spec')
      await expect(specField).toBeVisible()
    })

    test('new resource dialog cancel closes it', async ({ page }) => {
      const newButton = page.getByRole('button', { name: /new resource/i })
      await newButton.click()

      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()

      const cancelButton = dialog.getByRole('button', { name: /cancel/i })
      await cancelButton.click()

      await expect(dialog).not.toBeVisible()
    })
  })
})
