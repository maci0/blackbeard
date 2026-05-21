import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Models page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: 'Models' }).click()
    await page.waitForURL('/models')
  })

  test('page loads with header', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Models' })).toBeVisible()
    await expect(page.getByText('LLM connections and providers')).toBeVisible()
  })

  test('ollama-qwen model card is visible', async ({ page }) => {
    await expect(
      page.getByLabel(/llm connection: ollama-qwen/i),
    ).toBeVisible()
  })

  test('provider badge shows Ollama (local)', async ({ page }) => {
    await expect(page.getByText('Ollama (local)')).toBeVisible()
  })

  test('Add Connection button exists', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /add connection/i }),
    ).toBeVisible()
  })

  test('clicking Add Connection opens dialog', async ({ page }) => {
    await page.getByRole('button', { name: /add connection/i }).click()

    await expect(
      page.getByRole('heading', { name: /add llm connection/i }),
    ).toBeVisible()
    await expect(page.getByLabel(/^name/i)).toBeVisible()
    await expect(page.getByLabel(/provider/i)).toBeVisible()
    await expect(page.getByLabel(/^model/i)).toBeVisible()
  })

  test('Add Connection dialog can be closed', async ({ page }) => {
    await page.getByRole('button', { name: /add connection/i }).click()

    await expect(
      page.getByRole('heading', { name: /add llm connection/i }),
    ).toBeVisible()

    await page.getByRole('button', { name: /close/i }).click()

    await expect(
      page.getByRole('heading', { name: /add llm connection/i }),
    ).not.toBeVisible()
  })

  test('test button visible on card hover', async ({ page }) => {
    const card = page.getByLabel(/llm connection: ollama-qwen/i)
    await card.hover()

    await expect(
      page.getByRole('button', { name: /test connection ollama-qwen/i }),
    ).toBeVisible()
  })

  test('Refresh button exists and is clickable', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh models/i })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
  })
})
