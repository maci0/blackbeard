import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Keyboard Shortcuts Dialog', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/resources')
  })

  test('? key opens keyboard shortcuts dialog', async ({ page }) => {
    await page.keyboard.press('?')

    await expect(
      page.getByRole('dialog', { name: /keyboard shortcuts/i }),
    ).toBeVisible()
  })

  test('dialog shows Navigation and Studio sections', async ({ page }) => {
    await page.keyboard.press('?')

    const dialog = page.getByRole('dialog', { name: /keyboard shortcuts/i })
    await expect(dialog).toBeVisible()

    await expect(dialog.getByText(/navigation/i)).toBeVisible()
    await expect(dialog.getByText(/studio/i)).toBeVisible()
  })

  test('dialog has all shortcut entries', async ({ page }) => {
    await page.keyboard.press('?')

    const dialog = page.getByRole('dialog', { name: /keyboard shortcuts/i })
    await expect(dialog).toBeVisible()

    await expect(dialog.getByText(/command palette/i)).toBeVisible()
    await expect(dialog.getByText(/save/i)).toBeVisible()
    await expect(dialog.getByText(/undo/i)).toBeVisible()
    await expect(dialog.getByText(/redo/i)).toBeVisible()
  })

  test('escape closes dialog', async ({ page }) => {
    await page.keyboard.press('?')

    const dialog = page.getByRole('dialog', { name: /keyboard shortcuts/i })
    await expect(dialog).toBeVisible()

    await page.keyboard.press('Escape')

    await expect(dialog).not.toBeVisible()
  })
})
