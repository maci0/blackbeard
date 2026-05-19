import { test, expect } from '@playwright/test'
import { login } from './helpers'

test.describe('Marketplace', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('navigate to marketplace page', async ({ page }) => {
    await page.goto('/marketplace')
    await expect(page).toHaveURL(/marketplace/)
  })

  test('shows import from URL section', async ({ page }) => {
    await page.goto('/marketplace')
    await expect(
      page.getByText(/import from url|import resources/i),
    ).toBeVisible()
  })

  test('shows research crew starter card', async ({ page }) => {
    await page.goto('/marketplace')
    await expect(
      page.getByText(/research crew/i),
    ).toBeVisible()
  })

  test('shows content pipeline as coming soon', async ({ page }) => {
    await page.goto('/marketplace')
    await expect(
      page.getByText(/content pipeline/i),
    ).toBeVisible()
    await expect(
      page.getByText(/coming soon/i),
    ).toBeVisible()
  })
})
