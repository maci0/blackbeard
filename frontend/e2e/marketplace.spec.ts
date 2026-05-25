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
    await expect(
      page.getByText(/import from url|import resources/i),
    ).toBeVisible()
  })

  test('shows research crew starter card', async ({ page }) => {
    await expect(
      page.getByText(/research crew/i),
    ).toBeVisible()
  })

  test('shows content pipeline as coming soon', async ({ page }) => {
    await expect(
      page.getByText(/content pipeline/i),
    ).toBeVisible()
    await expect(
      page.getByText(/coming soon/i),
    ).toBeVisible()
  })
})
