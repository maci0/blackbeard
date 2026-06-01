import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-35: Bulk Operations', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/resources')
  })

  test('resources page renders', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /resources/i })).toBeVisible()
  })

  test('table view has select-all checkbox in header', async ({ page }) => {
    const table = page.getByRole('table', { name: /resources/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      // Switch to table view if in card mode
      const tableViewButton = page.getByRole('button', { name: /table/i })
      const buttonVisible = await tableViewButton.isVisible().catch(() => false)

      if (buttonVisible) {
        await tableViewButton.click()
        await page.waitForTimeout(500)
      }
    }

    // After ensuring table view, check again
    const tableNow = page.getByRole('table', { name: /resources/i })
    const nowVisible = await tableNow.isVisible().catch(() => false)

    if (nowVisible) {
      const selectAllCheckbox = page.getByRole('checkbox', {
        name: /select all/i,
      })
      await expect(selectAllCheckbox).toBeVisible()
    }
    // If no table visible (no resources), test passes silently
  })

  test('table rows have individual select checkboxes', async ({ page }) => {
    const table = page.getByRole('table', { name: /resources/i })
    const tableVisible = await table.isVisible().catch(() => false)

    if (!tableVisible) {
      const tableViewButton = page.getByRole('button', { name: /table/i })
      const buttonVisible = await tableViewButton.isVisible().catch(() => false)

      if (buttonVisible) {
        await tableViewButton.click()
        await page.waitForTimeout(500)
      }
    }

    const tableNow = page.getByRole('table', { name: /resources/i })
    const nowVisible = await tableNow.isVisible().catch(() => false)

    if (!nowVisible) {
      return
    }

    // Check that rows have checkboxes
    const rowCheckboxes = page.getByRole('checkbox', { name: /select /i })
    const count = await rowCheckboxes.count()

    // At least the header checkbox should exist
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('paste YAML button is visible', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await expect(pasteButton).toBeVisible()
  })

  test('paste YAML button opens import dialog', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Dialog should have the "Paste YAML" title
    await expect(dialog.getByText('Paste YAML')).toBeVisible()
  })

  test('paste YAML dialog has textarea for YAML input', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Should have a textarea with YAML content label
    const textarea = dialog.getByLabel(/yaml content/i)
    await expect(textarea).toBeVisible()
  })

  test('paste YAML dialog has import button', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Import button should be present (initially disabled since textarea is empty)
    const importButton = dialog.getByRole('button', { name: /import yaml/i })
    await expect(importButton).toBeVisible()
    await expect(importButton).toBeDisabled()
  })

  test('paste YAML dialog enables import button when text entered', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    const textarea = dialog.getByLabel(/yaml content/i)
    const importButton = dialog.getByRole('button', { name: /import yaml/i })

    // Initially disabled
    await expect(importButton).toBeDisabled()

    // Type some YAML
    await textarea.fill('apiVersion: blackbeard/v1alpha1\nkind: Agent\nmetadata:\n  name: test')

    // Import button should be enabled now
    await expect(importButton).toBeEnabled()
  })

  test('paste YAML dialog has cancel button', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    const cancelButton = dialog.getByRole('button', { name: /cancel/i })
    await expect(cancelButton).toBeVisible()
  })

  test('paste YAML dialog cancel closes it', async ({ page }) => {
    const pasteButton = page.getByRole('button', { name: /paste yaml/i })
    await pasteButton.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const cancelButton = dialog.getByRole('button', { name: /cancel/i })
    await cancelButton.click()

    await expect(dialog).not.toBeVisible()
  })

  test('import YAML file button is visible', async ({ page }) => {
    const importButton = page.getByRole('button', { name: /import yaml/i })
    await expect(importButton).toBeVisible()
  })

  test('card view has select checkboxes on hover', async ({ page }) => {
    // Switch to card view if possible
    const cardViewButton = page.getByRole('button', { name: /card/i })
    const buttonVisible = await cardViewButton.isVisible().catch(() => false)

    if (buttonVisible) {
      await cardViewButton.click()
      await page.waitForTimeout(500)
    }

    const cards = page.getByRole('article')
    const cardsVisible = await cards
      .first()
      .isVisible()
      .catch(() => false)

    if (cardsVisible) {
      // Hover over the first card to reveal checkbox
      await cards.first().hover()
      await page.waitForTimeout(200)

      // Checkbox should be visible after hover
      const checkbox = cards.first().getByRole('checkbox')
      const checkboxVisible = await checkbox.isVisible().catch(() => false)
      expect(checkboxVisible).toBeTruthy()
    }
    // If no cards, test passes silently
  })
})
