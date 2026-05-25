import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Automations', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/automations')
  })

  test('navigates to automations page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Automations' })).toBeVisible()
  })

  test('shows empty state or table', async ({ page }) => {
    // Either empty state text or a table should be visible
    const emptyState = page.getByText(/no automations/i)
    const table = page.getByRole('table', { name: 'Automations' })
    await expect(emptyState.or(table)).toBeVisible()
  })

  test('create automation dialog opens', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('Create Automation')).toBeVisible()
  })

  test('create automation dialog has required fields', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel(/name/i)).toBeVisible()
    await expect(dialog.getByLabel(/target kind/i)).toBeVisible()
    await expect(dialog.getByLabel(/target name/i)).toBeVisible()
    await expect(dialog.getByLabel(/trigger type/i)).toBeVisible()
  })

  test('create automation dialog can be closed', async ({ page }) => {
    await page.getByRole('button', { name: /create automation/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /close/i }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })
})
