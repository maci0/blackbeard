import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Webhooks page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/webhooks')
  })

  test('page loads with title', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.locator('h1, h2, h3').filter({ hasText: 'Webhooks' }),
    ).toBeVisible()
    await expect(
      main.getByText('HTTP endpoints that receive execution event notifications'),
    ).toBeVisible()
  })

  test('create webhook dialog opens', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add webhook/i }).click()

    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Webhook' }),
    ).toBeVisible()
    await expect(page.getByLabel(/^URL/)).toBeVisible()
    await expect(
      page.getByText('Register a URL to receive execution event notifications'),
    ).toBeVisible()
  })

  test('URL field validation requires http or https', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add webhook/i }).click()

    await page.getByLabel(/^URL/).fill('not-a-url')
    await page.getByRole('button', { name: /^add webhook$/i }).click()

    await expect(
      page.getByText(/URL must start with http:\/\/ or https:\/\//),
    ).toBeVisible()
  })

  test('event type checkboxes present in dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add webhook/i }).click()

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
    const main = page.locator('main')
    await main.getByRole('button', { name: /add webhook/i }).click()
    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Webhook' }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()
    await expect(
      page.locator('h1, h2, h3').filter({ hasText: 'Add Webhook' }),
    ).not.toBeVisible()
  })
})
