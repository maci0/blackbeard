import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('CUJ-11: Automation Setup', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/automations')
  })

  test('page renders with heading and description', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /automations/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/scheduled and triggered crew\/flow executions/i),
    ).toBeVisible()
  })

  test('create automation button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /create automation/i }),
    ).toBeVisible()
  })

  test('refresh button is visible', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /refresh automations/i }),
    ).toBeVisible()
  })

  test('clicking create automation opens dialog with form fields', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /create automation/i }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole('heading', { name: /create automation/i }),
    ).toBeVisible()

    // Name field
    await expect(dialog.getByLabel(/^name/i)).toBeVisible()

    // Target kind selector
    await expect(dialog.getByLabel(/target kind/i)).toBeVisible()

    // Target name field
    await expect(dialog.getByLabel(/target name/i)).toBeVisible()

    // Trigger type selector with cron/webhook/api options
    const triggerSelect = dialog.getByLabel(/trigger type/i)
    await expect(triggerSelect).toBeVisible()

    // Cron expression field (visible by default since cron is the default trigger)
    await expect(dialog.getByLabel(/cron expression/i)).toBeVisible()
  })

  test('trigger type controls conditional fields', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')

    // Default trigger type is cron, so cron field should be visible
    await expect(dialog.getByLabel(/cron expression/i)).toBeVisible()

    // Switch to webhook trigger
    await dialog.getByLabel(/trigger type/i).selectOption('webhook')
    await expect(dialog.getByLabel(/cron expression/i)).not.toBeVisible()
    await expect(
      dialog.getByText(/webhook url and secret will be generated/i),
    ).toBeVisible()

    // Switch to api trigger
    await dialog.getByLabel(/trigger type/i).selectOption('api')
    await expect(
      dialog.getByText(/trigger this automation via the api/i),
    ).toBeVisible()
  })

  test('default inputs field accepts JSON', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')

    const inputsField = dialog.getByLabel(/default inputs/i)
    await expect(inputsField).toBeVisible()
    await inputsField.fill('{"topic": "test"}')
  })

  test('enabled toggle is present and defaults to on', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')

    const toggle = dialog.getByRole('switch', {
      name: /enable automation on creation/i,
    })
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  test('cancel button closes dialog without changes', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('close button (X) closes dialog', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByRole('button', { name: /close/i }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('shows empty state or automation table', async ({ page }) => {
    const emptyState = page.getByText(/no automations yet/i)
    const table = page.getByRole('table', { name: /automations/i })

    await expect(emptyState.or(table)).toBeVisible()
  })
})
