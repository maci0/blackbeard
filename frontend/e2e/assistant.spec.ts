import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Assistant', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('assistant button visible in studio', async ({ page }) => {
    const main = page.locator('main')
    // The studio page should have a assistant/sparkles button
    const sparklesBtn = main.getByRole('button', { name: /assistant|sparkles|generate/i })
    await expect(sparklesBtn).toBeVisible()
  })

  test('clicking assistant opens dialog with textarea', async ({ page }) => {
    const main = page.locator('main')
    const sparklesBtn = main.getByRole('button', { name: /assistant|sparkles|generate/i })
    await sparklesBtn.click()

    // Dialog should open with a textarea for prompt
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole('textbox').or(dialog.locator('textarea')),
    ).toBeVisible()
  })

  test('assistant dialog has textarea and generate button', async ({ page }) => {
    const main = page.locator('main')
    const sparklesBtn = main.getByRole('button', { name: /assistant|sparkles|generate/i })
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
