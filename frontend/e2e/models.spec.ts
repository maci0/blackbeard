import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Models page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/models')
  })

  test('page loads with header', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.locator('h1, h2, h3').filter({ hasText: 'Models' })).toBeVisible()
    await expect(main.getByText('LLM connections and providers')).toBeVisible()
  })

  test('ollama-qwen model card is visible', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByText('ollama-qwen', { exact: true }).first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('provider badge shows Ollama (local)', async ({ page }) => {
    const main = page.locator('main')
    await expect(main.getByText('Ollama (local)').first()).toBeVisible({ timeout: 10000 })
  })

  test('Add Connection button exists', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByRole('button', { name: /add connection/i }),
    ).toBeVisible()
  })

  test('clicking Add Connection opens dialog', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add connection/i }).click()

    const dialog = page.locator('[role="dialog"]')
    await expect(dialog.getByText(/add llm connection/i)).toBeVisible()
    await expect(dialog.getByLabel(/^name/i)).toBeVisible()
    await expect(dialog.getByLabel(/provider/i)).toBeVisible()
    await expect(dialog.getByLabel(/model/i).first()).toBeVisible()
  })

  test('Add Connection dialog can be closed', async ({ page }) => {
    const main = page.locator('main')
    await main.getByRole('button', { name: /add connection/i }).click()

    const dialogTitle = page.locator('[role="dialog"]').getByText(/add llm connection/i)
    await expect(dialogTitle).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(dialogTitle).not.toBeVisible()
  })

  test('test button visible on card hover', async ({ page }) => {
    const main = page.locator('main')
    const card = main.locator('.group').filter({ hasText: 'ollama-qwen' }).first()
    await card.hover()

    await expect(
      page.getByRole('button', { name: /test connection ollama-qwen/i }),
    ).toBeVisible()
  })

  test('Refresh button exists and is clickable', async ({ page }) => {
    const main = page.locator('main')
    const refreshBtn = main.getByRole('button', { name: /refresh/i })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
  })
})
