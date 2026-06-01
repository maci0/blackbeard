import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-40: Webhook Events', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/webhooks')
  })

  test('page renders with heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /webhooks/i })).toBeVisible()
  })

  test('add webhook dialog has URL field', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const urlInput = dialog.getByLabel(/url/i)
    await expect(urlInput).toBeVisible()
    await expect(urlInput).toHaveAttribute('type', 'url')
  })

  test('event type checkboxes include expected events', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')

    // Event type names rendered in the dialog
    await expect(dialog.getByText(/crew started/i)).toBeVisible()
    await expect(dialog.getByText(/crew completed/i)).toBeVisible()
    await expect(dialog.getByText(/task started/i)).toBeVisible()
    await expect(dialog.getByText(/task completed/i)).toBeVisible()
  })

  test('select all toggles event checkboxes', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')

    await dialog.getByText(/select all/i).click()
    await expect(dialog.getByText(/deselect all/i)).toBeVisible()

    await dialog.getByText(/deselect all/i).click()
    await expect(dialog.getByText(/select all/i)).toBeVisible()
  })

  test('cancel closes the dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('shows empty state or webhook table', async ({ page }) => {
    const emptyState = page.getByText(/no webhooks registered/i)
    const table = page.getByRole('table', { name: /webhooks/i })

    await expect(emptyState.or(table)).toBeVisible()
  })
})
