import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-12: Webhook Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/webhooks')
  })

  test('page renders with heading and description', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /webhooks/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/http endpoints that receive execution event notifications/i),
    ).toBeVisible()
  })

  test('add webhook button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /add webhook/i }),
    ).toBeVisible()
  })

  test('refresh button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /refresh webhooks/i }),
    ).toBeVisible()
  })

  test('clicking add webhook opens dialog with form', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole('heading', { name: /add webhook/i }),
    ).toBeVisible()

    // URL field is present and required
    const urlInput = dialog.getByLabel(/url/i)
    await expect(urlInput).toBeVisible()
    await expect(urlInput).toHaveAttribute('type', 'url')

    // Events section
    await expect(dialog.getByText(/events/i).first()).toBeVisible()
  })

  test('event checkboxes are present in the form', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')

    // Event checkboxes should be rendered in a group
    const eventGroup = dialog.getByRole('group', {
      name: /events/i,
    })
    await expect(eventGroup).toBeVisible()

    // Verify some known event checkboxes exist
    await expect(dialog.getByText(/crew started/i)).toBeVisible()
    await expect(dialog.getByText(/crew completed/i)).toBeVisible()
    await expect(dialog.getByText(/task started/i)).toBeVisible()

    // Select all / deselect all toggle
    await expect(dialog.getByText(/select all/i)).toBeVisible()
  })

  test('select all toggles all event checkboxes', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')

    // Click "Select all"
    await dialog.getByText(/select all/i).click()

    // After selecting all, the button text should change
    await expect(dialog.getByText(/deselect all/i)).toBeVisible()

    // Toggle back
    await dialog.getByText(/deselect all/i).click()
    await expect(dialog.getByText(/select all/i)).toBeVisible()
  })

  test('cancel button closes dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('close button (X) closes dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /close/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('shows empty state or webhook table', async ({ page }) => {
    const emptyState = page.getByText(/no webhooks registered/i)
    const table = page.getByRole('table', { name: /webhooks/i })

    await expect(emptyState.or(table)).toBeVisible()
  })

  test('empty state has add webhook action', async ({ page }) => {
    const emptyState = page.getByText(/no webhooks registered/i)
    const table = page.getByRole('table', { name: /webhooks/i })

    // Only test empty state action if we are in empty state
    if (await emptyState.isVisible()) {
      await expect(
        page.getByRole('button', { name: /add webhook/i }).or(
          page.getByRole('link', { name: /add webhook/i }),
        ),
      ).toBeVisible()
    } else {
      // Table headers should be present
      await expect(table.getByText('URL')).toBeVisible()
      await expect(table.getByText('Events')).toBeVisible()
      await expect(table.getByText('Status')).toBeVisible()
    }
  })
})
