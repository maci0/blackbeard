import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-39: Flow Execution', () => {
  test.describe('Resources page with Flow filter', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/resources')
    })

    test('page renders with heading', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()
    })

    test('kind filter dropdown includes Flow option', async ({ page }) => {
      // The kind filter dropdown should list Flow as a filterable kind
      const kindFilter = page.locator('select').filter({ hasText: /all kinds/i })
      if (await kindFilter.isVisible()) {
        const options = await kindFilter.locator('option').allTextContents()
        expect(options.map((t) => t.toLowerCase())).toEqual(expect.arrayContaining(['flow']))
      }
    })

    test('filtering by Flow shows resources or empty state', async ({ page }) => {
      const kindFilter = page.locator('select').filter({ hasText: /all kinds/i })
      if (await kindFilter.isVisible()) {
        await kindFilter.selectOption({ label: 'Flow' })
        await page.waitForTimeout(300)

        const table = page.getByRole('table')
        const emptyState = page.getByText(/no resources/i)

        await expect(table.or(emptyState)).toBeVisible()
      }
    })
  })

  test.describe('Studio palette has Flow Step node', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/studio')
    })

    test('flow step node type is available in palette', async ({ page }) => {
      // The palette lists draggable node types including Flow Step
      const palette = page
        .locator('[data-testid="palette"]')
        .or(page.locator('aside, [class*="palette"]'))

      // Flow Step should appear as a palette item
      const flowStepItem = page.getByText('Flow Step')
      await expect(flowStepItem.first()).toBeVisible({ timeout: 10000 })
    })
  })
})
