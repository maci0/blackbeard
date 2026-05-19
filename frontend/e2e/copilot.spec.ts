import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Copilot', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
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
})
