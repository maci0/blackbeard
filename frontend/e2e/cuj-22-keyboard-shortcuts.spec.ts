import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-22: Keyboard Shortcuts', () => {
  test.describe('Shortcuts dialog', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/resources')
    })

    test('pressing ? opens the keyboard shortcuts dialog', async ({
      page,
    }) => {
      await page.keyboard.press('?')

      await expect(
        page.getByRole('dialog', { name: /keyboard shortcuts/i }),
      ).toBeVisible()
    })

    test('dialog shows Navigation and Studio sections', async ({ page }) => {
      await page.keyboard.press('?')

      const dialog = page.getByRole('dialog', {
        name: /keyboard shortcuts/i,
      })
      await expect(dialog).toBeVisible()

      await expect(dialog.getByText(/navigation/i)).toBeVisible()
      await expect(dialog.getByText(/studio/i)).toBeVisible()
    })

    test('dialog lists expected shortcut entries', async ({ page }) => {
      await page.keyboard.press('?')

      const dialog = page.getByRole('dialog', {
        name: /keyboard shortcuts/i,
      })
      await expect(dialog).toBeVisible()

      await expect(dialog.getByText(/command palette/i)).toBeVisible()
      await expect(dialog.getByText(/save/i)).toBeVisible()
      await expect(dialog.getByText(/undo/i)).toBeVisible()
      await expect(dialog.getByText(/redo/i)).toBeVisible()
    })

    test('dialog can be closed with Escape', async ({ page }) => {
      await page.keyboard.press('?')

      const dialog = page.getByRole('dialog', {
        name: /keyboard shortcuts/i,
      })
      await expect(dialog).toBeVisible()

      await page.keyboard.press('Escape')

      await expect(dialog).not.toBeVisible()
    })

    test('dialog can be closed with the close button', async ({ page }) => {
      await page.keyboard.press('?')

      const dialog = page.getByRole('dialog', {
        name: /keyboard shortcuts/i,
      })
      await expect(dialog).toBeVisible()

      await dialog.getByRole('button', { name: /close/i }).click()

      await expect(dialog).not.toBeVisible()
    })
  })

  test.describe('Global navigation shortcuts', () => {
    test.beforeEach(async ({ page }) => {
      await loginAndNavigate(page, '/dashboard')
    })

    test('Cmd+Shift+S navigates to Studio', async ({ page }) => {
      await page.keyboard.press('Meta+Shift+s')

      await expect(page).toHaveURL(/\/studio/)
    })

    test('Cmd+Shift+E navigates to Executions', async ({ page }) => {
      await page.keyboard.press('Meta+Shift+e')

      await expect(page).toHaveURL(/\/executions/)
    })

    test('Cmd+Shift+N navigates to Resources', async ({ page }) => {
      await page.keyboard.press('Meta+Shift+n')

      await expect(page).toHaveURL(/\/resources/)
    })

    test('Cmd+. navigates to Settings', async ({ page }) => {
      await page.keyboard.press('Meta+.')

      await expect(page).toHaveURL(/\/settings/)
    })
  })
})
