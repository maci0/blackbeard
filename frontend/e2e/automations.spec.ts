import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Automations', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/automations')
  })

  test('navigates to automations page', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Automations' })).toBeVisible()
  })

  test('shows empty state or table', async ({ page }) => {
    const main = page.locator('main')
    // Either empty state text or a table should be visible
    const emptyState = main.getByText(/no automations/i)
    const table = main.getByRole('table', { name: 'Automations' })
    await expect(emptyState.or(table)).toBeVisible()
  })

  test('create automation dialog opens', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /create automation/i }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('Create Automation')).toBeVisible()
  })

  test('create automation dialog has required fields', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /create automation/i }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel(/name/i)).toBeVisible()
    await expect(dialog.getByLabel(/target kind/i)).toBeVisible()
    await expect(dialog.getByLabel(/target name/i)).toBeVisible()
    await expect(dialog.getByLabel(/trigger type/i)).toBeVisible()
  })

  test('create automation dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /create automation/i }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /close/i }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })
})
