import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-03: Run a Crew', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/studio')
  })

  test('run button is visible in toolbar', async ({ page }) => {
    const main = page.locator('main')
    const runButton = main.getByRole('button', { name: /run/i })
    await expect(runButton).toBeVisible()
    await expect(runButton).toBeEnabled()
  })

  test('clicking run opens the RunDialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    // The dialog should appear with "Run Crew" as the title
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('Run Crew')).toBeVisible()
  })

  test('RunDialog has mode selector with Run, Train, Test options', async ({
    page,
  }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Mode selector should contain Run, Train, and Test radio buttons
    const modeGroup = dialog.getByRole('radiogroup', {
      name: /execution mode/i,
    })
    await expect(modeGroup).toBeVisible()

    await expect(
      modeGroup.getByRole('radio', { name: /run/i }),
    ).toBeVisible()
    await expect(
      modeGroup.getByRole('radio', { name: /train/i }),
    ).toBeVisible()
    await expect(
      modeGroup.getByRole('radio', { name: /test/i }),
    ).toBeVisible()
  })

  test('RunDialog Run mode is selected by default', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    const runRadio = dialog
      .getByRole('radiogroup', { name: /execution mode/i })
      .getByRole('radio', { name: /^Run$/i })

    await expect(runRadio).toHaveAttribute('aria-checked', 'true')
  })

  test('RunDialog shows JSON input textarea', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Crew Inputs (JSON) textarea should be visible
    await expect(dialog.locator('#run-dialog-inputs')).toBeVisible()

    // Default value should be valid JSON
    const value = await dialog.locator('#run-dialog-inputs').inputValue()
    expect(() => JSON.parse(value)).not.toThrow()
  })

  test('RunDialog shows submit and cancel buttons', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Run button inside the dialog
    await expect(
      dialog.getByRole('button', { name: /^run$/i }),
    ).toBeVisible()

    // Cancel button
    await expect(
      dialog.getByRole('button', { name: /cancel/i }),
    ).toBeVisible()
  })

  test('RunDialog cancel button closes the dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()

    // Dialog should be dismissed
    await expect(dialog).not.toBeVisible()
  })

  test('RunDialog close (X) button dismisses the dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Close button in the dialog header
    await dialog.getByRole('button', { name: /close/i }).click()

    await expect(dialog).not.toBeVisible()
  })

  test('RunDialog validates invalid JSON input', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    const textarea = dialog.locator('#run-dialog-inputs')

    // Clear and type invalid JSON
    await textarea.fill('{ invalid json }')
    // Blur to trigger validation
    await textarea.blur()

    // Error message should appear
    await expect(dialog.getByRole('alert')).toBeVisible()
    await expect(dialog.getByText(/invalid json/i)).toBeVisible()
  })

  test('RunDialog shows keyboard shortcut hint', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')

    // Should show the Cmd/Ctrl+Enter hint
    await expect(dialog.getByText(/enter to run/i)).toBeVisible()
  })

  test('RunDialog shows save preset button', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /run/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(
      dialog.getByRole('button', { name: /save current inputs as preset/i }),
    ).toBeVisible()
  })
})
