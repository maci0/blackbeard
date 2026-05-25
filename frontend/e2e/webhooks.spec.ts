import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Webhooks page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/webhooks')
  })

  test('page loads with title', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Webhooks' }),
    ).toBeVisible()
    await expect(
      page.getByText('HTTP endpoints that receive execution event notifications'),
    ).toBeVisible()
  })

  test('create webhook dialog opens', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()

    await expect(
      page.getByRole('heading', { name: 'Add Webhook' }),
    ).toBeVisible()
    await expect(page.getByLabel(/^URL/)).toBeVisible()
    await expect(
      page.getByText('Register a URL to receive execution event notifications'),
    ).toBeVisible()
  })

  test('URL field validation requires http or https', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()

    await page.getByLabel(/^URL/).fill('not-a-url')
    await page.getByRole('button', { name: /^add webhook$/i }).click()

    await expect(
      page.getByText(/URL must start with http:\/\/ or https:\/\//),
    ).toBeVisible()
  })

  test('event type checkboxes present in dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()

    const events = [
      'crew_started',
      'crew_completed',
      'task_started',
      'task_completed',
      'tool_started',
      'tool_finished',
      'llm_started',
      'llm_completed',
    ]

    for (const event of events) {
      await expect(page.getByText(event)).toBeVisible()
    }

    await expect(page.getByText(/select all/i)).toBeVisible()
  })

  test('dialog can be closed', async ({ page }) => {
    await page.getByRole('button', { name: /add webhook/i }).click()
    await expect(
      page.getByRole('heading', { name: 'Add Webhook' }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()
    await expect(
      page.getByRole('heading', { name: 'Add Webhook' }),
    ).not.toBeVisible()
  })
})
