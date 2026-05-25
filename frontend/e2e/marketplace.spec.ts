import { test, expect } from '@playwright/test'
import { loginAndNavigate } from './helpers'

test.describe('Marketplace', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndNavigate(page, '/marketplace')
  })

  test('navigate to marketplace page', async ({ page }) => {
    await expect(page).toHaveURL(/marketplace/)
  })

  test('shows import from URL section', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByText(/import from url|import resources/i),
    ).toBeVisible()
  })

  test('shows research crew starter card', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByText(/research crew/i),
    ).toBeVisible()
  })

  test('shows content pipeline as coming soon', async ({ page }) => {
    const main = page.locator('main')
    await expect(
      main.getByText(/content pipeline/i),
    ).toBeVisible()
    await expect(
      main.getByText(/coming soon/i),
    ).toBeVisible()
  })
})
