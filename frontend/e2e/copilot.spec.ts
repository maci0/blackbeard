import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Copilot', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('copilot button visible in studio', async ({ page }) => {
    // The studio page should have a copilot/sparkles button
    const sparklesBtn = page.getByRole('button', { name: /copilot|sparkles|generate/i })
    await expect(sparklesBtn).toBeVisible()
  })

  test('clicking copilot opens dialog with textarea', async ({ page }) => {
    const sparklesBtn = page.getByRole('button', { name: /copilot|sparkles|generate/i })
    await sparklesBtn.click()

    // Dialog should open with a textarea for prompt
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole('textbox').or(dialog.locator('textarea')),
    ).toBeVisible()
  })

  test('copilot dialog has textarea and generate button', async ({ page }) => {
    const sparklesBtn = page.getByRole('button', { name: /copilot|sparkles|generate/i })
    await sparklesBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Should have a text input area
    await expect(
      dialog.getByRole('textbox').or(dialog.locator('textarea')),
    ).toBeVisible()

    // Should have a generate button
    await expect(
      dialog.getByRole('button', { name: /generate/i }),
    ).toBeVisible()
  })
})
