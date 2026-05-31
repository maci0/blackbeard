import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-14: Credential Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/credentials')
  })

  test('page renders with heading and description', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /credentials/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/manage secrets and api keys/i),
    ).toBeVisible()
  })

  test('add credential button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /add credential/i }),
    ).toBeVisible()
  })

  test('refresh button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /refresh credentials/i }),
    ).toBeVisible()
  })

  test('clicking add credential opens dialog with form fields', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /add credential/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole('heading', { name: /add credential/i }),
    ).toBeVisible()

    // Name field
    const nameInput = dialog.getByLabel(/^name/i)
    await expect(nameInput).toBeVisible()
    await expect(nameInput).toHaveAttribute('placeholder', 'my-api-key')

    // Type selector
    const typeSelect = dialog.getByLabel(/type/i)
    await expect(typeSelect).toBeVisible()

    // Secret value field
    const valueInput = dialog.getByLabel(/secret value/i)
    await expect(valueInput).toBeVisible()

    // Description field
    const descInput = dialog.getByLabel(/description/i)
    await expect(descInput).toBeVisible()
  })

  test('type selector has expected options', async ({ page }) => {
    await page.getByRole('button', { name: /add credential/i }).click()
    const dialog = page.getByRole('dialog')

    const typeSelect = dialog.getByLabel(/type/i)

    // Verify expected credential types
    await expect(typeSelect.getByRole('option', { name: /api key/i })).toBeVisible()
    await expect(typeSelect.getByRole('option', { name: /bearer token/i })).toBeVisible()
    await expect(typeSelect.getByRole('option', { name: /password/i })).toBeVisible()
    await expect(typeSelect.getByRole('option', { name: /oauth client/i })).toBeVisible()
    await expect(typeSelect.getByRole('option', { name: /custom secret/i })).toBeVisible()
  })

  test('secret value field has show/hide toggle', async ({ page }) => {
    await page.getByRole('button', { name: /add credential/i }).click()
    const dialog = page.getByRole('dialog')

    // The value input should default to password type (hidden)
    const valueInput = dialog.getByLabel(/secret value/i)
    await expect(valueInput).toHaveAttribute('type', 'password')

    // Click the show/hide toggle
    await dialog.getByRole('button', { name: /show value/i }).click()
    await expect(valueInput).toHaveAttribute('type', 'text')

    // Click again to hide
    await dialog.getByRole('button', { name: /hide value/i }).click()
    await expect(valueInput).toHaveAttribute('type', 'password')
  })

  test('cancel button closes the dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add credential/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('close button (X) closes the dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add credential/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /close/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('name field hint explains naming convention', async ({ page }) => {
    await page.getByRole('button', { name: /add credential/i }).click()
    const dialog = page.getByRole('dialog')

    await expect(
      dialog.getByText(/lowercase letters, numbers, and hyphens only/i),
    ).toBeVisible()
  })

  test('shows empty state or credential cards', async ({ page }) => {
    const emptyState = page.getByText(/no credentials yet/i)
    const grid = page.locator('.grid')

    await expect(emptyState.or(grid)).toBeVisible()
  })

  test('empty state has add credential action', async ({ page }) => {
    const emptyState = page.getByText(/no credentials yet/i)

    if (await emptyState.isVisible()) {
      await expect(
        page.getByText(
          /add api keys, tokens, and other secrets/i,
        ),
      ).toBeVisible()
    }
  })
})
